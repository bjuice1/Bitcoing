"""BitcoinMonitor - Central orchestrator for fetching, storing, and analyzing."""
import logging
from datetime import datetime, timezone
from models.database import Database
from monitor.api import APIRegistry

logger = logging.getLogger("btcmonitor.monitor")


class BitcoinMonitor:
    def __init__(self, db, api, config=None):
        self.db = db
        self.api = api
        self.config = config or {}

    def fetch_and_store(self):
        """Fetch current metrics from all APIs and save to DB."""
        # Get recent prices for MVRV fallback
        price_history = self.db.get_price_history()
        prices = [r["price_usd"] for r in price_history[-200:]] if price_history else None

        snapshot = self.api.fetch_all_current(price_history_prices=prices)
        self.db.save_snapshot(snapshot)
        logger.info(
            f"Fetched: BTC ${snapshot.price.price_usd:,.0f} | "
            f"F&G: {snapshot.sentiment.fear_greed_value} | "
            f"MVRV: {snapshot.valuation.mvrv_ratio or 'N/A'}"
        )
        return snapshot

    def get_current_status(self):
        """Get latest snapshot, fetching fresh if DB is empty."""
        snapshot = self.db.get_latest_snapshot()
        if snapshot is None:
            logger.info("No data in DB, fetching fresh...")
            snapshot = self.fetch_and_store()
        return snapshot

    def get_metric_history(self, metric_name, days=30):
        """Get historical values for a metric from snapshots table."""
        return self.db.get_metric_history(metric_name, days)

    def get_price_change(self, period_days):
        """Calculate price change over a period from price_history."""
        history = self.db.get_price_history()
        if len(history) < 2:
            return None
        target_idx = max(0, len(history) - period_days)
        old_price = history[target_idx]["price_usd"]
        new_price = history[-1]["price_usd"]
        if old_price == 0:
            return None
        return ((new_price - old_price) / old_price) * 100

    def get_drawdown_from_ath(self):
        """Find ATH and compute current drawdown."""
        history = self.db.get_price_history()
        if not history:
            return {"ath_price": 0, "ath_date": "N/A", "current_price": 0, "drawdown_pct": 0}

        ath_record = max(history, key=lambda r: r["price_usd"])
        current = history[-1]

        drawdown = ((ath_record["price_usd"] - current["price_usd"]) / ath_record["price_usd"]) * 100
        return {
            "ath_price": ath_record["price_usd"],
            "ath_date": ath_record["date"],
            "current_price": current["price_usd"],
            "drawdown_pct": drawdown,
        }

    def get_key_metrics_summary(self):
        """Comprehensive summary dict for display."""
        snapshot = self.get_current_status()
        drawdown = self.get_drawdown_from_ath()

        from utils.constants import days_since_last_halving, days_until_next_halving, get_current_block_reward
        return {
            "price_usd": snapshot.price.price_usd,
            "change_24h_pct": snapshot.price.change_24h_pct,
            "market_cap": snapshot.price.market_cap,
            "volume_24h": snapshot.price.volume_24h,
            "hash_rate_th": snapshot.onchain.hash_rate_th,
            "difficulty": snapshot.onchain.difficulty,
            "block_time_avg": snapshot.onchain.block_time_avg,
            "difficulty_change_pct": snapshot.onchain.difficulty_change_pct,
            "supply_circulating": snapshot.onchain.supply_circulating,
            "fear_greed_value": snapshot.sentiment.fear_greed_value,
            "fear_greed_label": snapshot.sentiment.fear_greed_label,
            "btc_gold_ratio": snapshot.sentiment.btc_gold_ratio,
            "btc_dominance_pct": snapshot.sentiment.btc_dominance_pct,
            "mvrv_ratio": snapshot.valuation.mvrv_ratio,
            "mvrv_z_score": snapshot.valuation.mvrv_z_score,
            "mvrv_is_estimated": snapshot.valuation.mvrv_is_estimated,
            "ath_price": drawdown["ath_price"],
            "ath_date": drawdown["ath_date"],
            "drawdown_from_ath_pct": drawdown["drawdown_pct"],
            "days_since_halving": days_since_last_halving(),
            "days_until_halving": days_until_next_halving(),
            "block_reward": get_current_block_reward(),
            "timestamp": snapshot.timestamp,
        }

    def backfill_history(self, start_year=2015, progress_callback=None):
        """Backfill historical daily prices."""
        existing = self.db.get_price_date_range()
        logger.info(f"Existing data: {existing['min_date']} to {existing['max_date']}")
        count = self.api.backfill_prices(start_year, self.db)
        if progress_callback:
            progress_callback(count)
        return count
