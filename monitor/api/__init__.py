"""API client registry and orchestration."""
import logging
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from models.metrics import (
    PriceMetrics, OnchainMetrics, SentimentMetrics, ValuationMetrics, CombinedSnapshot
)
from monitor.api.coingecko import CoinGeckoClient
from monitor.api.blockchain_info import BlockchainInfoClient
from monitor.api.mempool import MempoolClient
from monitor.api.fear_greed import FearGreedClient
from monitor.api.coinmetrics import CoinMetricsClient

logger = logging.getLogger("btcmonitor.api")


class APIRegistry:
    def __init__(self, config=None):
        cfg = config or {}
        api_cfg = cfg.get("api", {})

        self.coingecko = CoinGeckoClient(
            rate_limit=api_cfg.get("coingecko", {}).get("rate_limit", 30),
            cache_ttl=api_cfg.get("coingecko", {}).get("cache_ttl", 300),
        )
        self.blockchain = BlockchainInfoClient(
            rate_limit=api_cfg.get("blockchain_info", {}).get("rate_limit", 30),
            cache_ttl=api_cfg.get("blockchain_info", {}).get("cache_ttl", 300),
        )
        self.mempool = MempoolClient(
            rate_limit=api_cfg.get("mempool", {}).get("rate_limit", 60),
            cache_ttl=api_cfg.get("mempool", {}).get("cache_ttl", 120),
        )
        self.fear_greed = FearGreedClient(
            rate_limit=api_cfg.get("fear_greed", {}).get("rate_limit", 30),
            cache_ttl=api_cfg.get("fear_greed", {}).get("cache_ttl", 600),
        )
        self.coinmetrics = CoinMetricsClient(
            rate_limit=api_cfg.get("coinmetrics", {}).get("rate_limit", 100),
            cache_ttl=api_cfg.get("coinmetrics", {}).get("cache_ttl", 600),
        )

    def fetch_price_metrics(self):
        return self.coingecko.get_current_price()

    def fetch_onchain_metrics(self):
        try:
            hr = self.blockchain.get_hash_rate("30days")
            diff = self.blockchain.get_difficulty("30days")
        except Exception as e:
            logger.warning(f"Blockchain.com failed: {e}")
            hr = {"current": 0}
            diff = {"current": 0}

        try:
            adj = self.mempool.get_difficulty_adjustment()
        except Exception as e:
            logger.warning(f"mempool.space failed: {e}")
            adj = {"avg_block_time": 600, "estimated_change_pct": 0}

        try:
            coin = self.coingecko.get_coin_data()
        except Exception as e:
            logger.warning(f"CoinGecko coin data failed: {e}")
            coin = {"circulating_supply": 0, "max_supply": 21000000}

        return OnchainMetrics(
            hash_rate_th=hr.get("current", 0),
            difficulty=diff.get("current", 0),
            block_time_avg=adj.get("avg_block_time", 600),
            difficulty_change_pct=adj.get("estimated_change_pct", 0),
            supply_circulating=coin.get("circulating_supply", 0),
            supply_max=coin.get("max_supply", 21000000),
        )

    def fetch_sentiment_metrics(self):
        try:
            fg = self.fear_greed.get_current()
        except Exception as e:
            logger.warning(f"Fear & Greed failed: {e}")
            fg = {"value": 50, "label": "Neutral"}

        try:
            gold = self.coingecko.get_btc_gold_ratio()
        except Exception as e:
            logger.warning(f"BTC/Gold ratio failed: {e}")
            gold = 0

        try:
            gd = self.coingecko.get_global_data()
        except Exception as e:
            logger.warning(f"Global data failed: {e}")
            gd = {"btc_dominance_pct": 0}

        return SentimentMetrics(
            fear_greed_value=fg["value"],
            fear_greed_label=fg["label"],
            btc_gold_ratio=gold,
            btc_dominance_pct=gd.get("btc_dominance_pct", 0),
        )

    def fetch_valuation_metrics(self, market_cap=0, price_history_prices=None):
        mvrv = None
        realized_cap = None
        is_estimated = False

        try:
            mvrv = self.coinmetrics.get_mvrv()
            realized_cap = self.coinmetrics.get_realized_cap()
        except Exception as e:
            logger.warning(f"CoinMetrics failed: {e}")

        if mvrv is None and market_cap > 0 and price_history_prices:
            mvrv = CoinMetricsClient.estimate_mvrv(market_cap, price_history_prices)
            is_estimated = True
            if mvrv:
                logger.info(f"Using estimated MVRV: {mvrv:.2f}")

        return ValuationMetrics(
            mvrv_ratio=mvrv,
            realized_cap_est=realized_cap,
            mvrv_is_estimated=is_estimated,
        )

    def fetch_all_current(self, price_history_prices=None):
        """Fetch all metrics concurrently, assembling a CombinedSnapshot."""
        results = {}

        def _fetch(name, func, kwargs=None):
            try:
                return name, func(**(kwargs or {}))
            except Exception as e:
                logger.error(f"Failed to fetch {name}: {e}")
                return name, None

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(_fetch, "price", self.fetch_price_metrics),
                executor.submit(_fetch, "onchain", self.fetch_onchain_metrics),
                executor.submit(_fetch, "sentiment", self.fetch_sentiment_metrics),
            ]
            for future in as_completed(futures):
                name, data = future.result()
                results[name] = data

        # Valuation depends on price result for fallback
        price = results.get("price") or PriceMetrics()
        results["valuation"] = self.fetch_valuation_metrics(
            market_cap=price.market_cap,
            price_history_prices=price_history_prices,
        )

        return CombinedSnapshot(
            price=results.get("price") or PriceMetrics(),
            onchain=results.get("onchain") or OnchainMetrics(),
            sentiment=results.get("sentiment") or SentimentMetrics(),
            valuation=results.get("valuation") or ValuationMetrics(),
            timestamp=datetime.now(timezone.utc),
            source="api",
        )

    def health_check(self):
        """Test connectivity to each API."""
        checks = {}

        def _check(name, func):
            start = time.monotonic()
            try:
                func()
                latency = int((time.monotonic() - start) * 1000)
                return name, True, latency
            except Exception:
                latency = int((time.monotonic() - start) * 1000)
                return name, False, latency

        apis = [
            ("CoinGecko", lambda: self.coingecko.get_current_price()),
            ("Blockchain.com", lambda: self.blockchain.get_hash_rate("1days")),
            ("mempool.space", lambda: self.mempool.get_difficulty_adjustment()),
            ("Fear & Greed", lambda: self.fear_greed.get_current()),
        ]

        for name, func in apis:
            _, reachable, latency = _check(name, func)
            checks[name] = {"reachable": reachable, "latency_ms": latency}

        return checks

    def backfill_prices(self, start_year, db):
        """Fetch full price history and save to DB."""
        records = self.coingecko.get_full_history(start_year)
        if records:
            db.save_price_history(records)
            logger.info(f"Backfilled {len(records)} price records from {start_year}")
        return len(records)

    @staticmethod
    def is_data_fresh(snapshot, max_age_seconds=1800):
        if snapshot is None:
            return False
        age = (datetime.now(timezone.utc) - snapshot.timestamp).total_seconds()
        return age < max_age_seconds

    def close(self):
        for client in [self.coingecko, self.blockchain, self.mempool, self.fear_greed, self.coinmetrics]:
            client.close()
