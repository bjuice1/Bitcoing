"""CoinGecko API client for price, market, supply, and historical data."""
import logging
import time
from datetime import datetime, timezone
from utils.http_client import HTTPClient
from utils.rate_limiter import RateLimiter
from models.metrics import PriceMetrics

logger = logging.getLogger("btcmonitor.coingecko")


class CoinGeckoClient:
    def __init__(self, rate_limit=30, cache_ttl=300):
        self.client = HTTPClient(
            base_url="https://api.coingecko.com/api/v3",
            rate_limiter=RateLimiter(rate_limit),
            cache_ttl=cache_ttl,
        )

    def get_current_price(self):
        data = self.client.get("/simple/price", params={
            "ids": "bitcoin",
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        })
        btc = data.get("bitcoin", {})
        return PriceMetrics(
            price_usd=btc.get("usd", 0),
            market_cap=btc.get("usd_market_cap", 0),
            volume_24h=btc.get("usd_24h_vol", 0),
            change_24h_pct=btc.get("usd_24h_change", 0),
            timestamp=datetime.now(timezone.utc),
        )

    def get_btc_gold_ratio(self):
        data = self.client.get("/simple/price", params={
            "ids": "bitcoin",
            "vs_currencies": "xau",
        })
        return data.get("bitcoin", {}).get("xau", 0)

    def get_global_data(self):
        data = self.client.get("/global")
        gd = data.get("data", {})
        return {
            "btc_dominance_pct": gd.get("market_cap_percentage", {}).get("btc", 0),
            "total_market_cap_usd": gd.get("total_market_cap", {}).get("usd", 0),
        }

    def get_coin_data(self):
        data = self.client.get("/coins/bitcoin", params={
            "localization": "false",
            "tickers": "false",
            "community_data": "false",
            "developer_data": "false",
        })
        md = data.get("market_data", {})
        return {
            "circulating_supply": md.get("circulating_supply", 0),
            "max_supply": md.get("max_supply", 21000000),
            "ath": md.get("ath", {}).get("usd", 0),
            "ath_date": md.get("ath_date", {}).get("usd", ""),
        }

    def get_historical_prices(self, days=365):
        data = self.client.get("/coins/bitcoin/market_chart", params={
            "vs_currency": "usd",
            "days": str(days),
            "interval": "daily",
        })
        records = []
        prices = data.get("prices", [])
        market_caps = data.get("market_caps", [])
        volumes = data.get("total_volumes", [])

        for i, (ts, price) in enumerate(prices):
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            date_str = dt.strftime("%Y-%m-%d")
            mc = market_caps[i][1] if i < len(market_caps) else 0
            vol = volumes[i][1] if i < len(volumes) else 0
            records.append({
                "date": date_str,
                "price_usd": price,
                "market_cap": mc,
                "volume": vol,
            })

        # Deduplicate by date (keep last)
        seen = {}
        for r in records:
            seen[r["date"]] = r
        return list(seen.values())

    def get_historical_prices_range(self, start_ts, end_ts):
        data = self.client.get("/coins/bitcoin/market_chart/range", params={
            "vs_currency": "usd",
            "from": str(int(start_ts)),
            "to": str(int(end_ts)),
        })
        records = []
        for ts, price in data.get("prices", []):
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            records.append({
                "date": dt.strftime("%Y-%m-%d"),
                "price_usd": price,
                "market_cap": 0,
                "volume": 0,
            })
        seen = {}
        for r in records:
            seen[r["date"]] = r
        return list(seen.values())

    def get_full_history(self, start_year=2015):
        """Fetch daily prices using free-tier endpoint (max 365 days per call).

        The /market_chart?days=N endpoint works on CoinGecko free tier.
        The /market_chart/range endpoint requires a paid plan.
        We fetch in 365-day chunks going backwards from today.
        """
        all_records = {}
        now = datetime.now(timezone.utc)
        from datetime import timedelta

        # Calculate how many days back we need
        start_dt = datetime(start_year, 1, 1, tzinfo=timezone.utc)
        total_days = (now - start_dt).days

        # Free tier: max 365 days per request with daily interval
        # Fetch the max available first
        days_to_fetch = min(total_days, 365)
        logger.info(f"Fetching last {days_to_fetch} days of price history (free tier max: 365)...")

        try:
            records = self.get_historical_prices(days=days_to_fetch)
            for r in records:
                all_records[r["date"]] = r
            logger.info(f"Got {len(records)} daily price records")
        except Exception as e:
            logger.warning(f"Failed to fetch history: {e}")

        if total_days > 365:
            logger.info(f"Note: Free tier limits to 365 days. Requested {total_days} days from {start_year}. "
                       f"Upgrade to CoinGecko Pro for full history, or data will cover last ~1 year only.")

        result = sorted(all_records.values(), key=lambda r: r["date"])
        logger.info(f"Total historical records: {len(result)}")
        return result

    def close(self):
        self.client.close()
