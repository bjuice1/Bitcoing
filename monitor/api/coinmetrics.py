"""CoinMetrics Community API client for MVRV and realized cap."""
import logging
from datetime import datetime, timezone, timedelta
from utils.http_client import HTTPClient, APIError
from utils.rate_limiter import RateLimiter

logger = logging.getLogger("btcmonitor.coinmetrics")


class CoinMetricsClient:
    def __init__(self, rate_limit=100, cache_ttl=600):
        self.client = HTTPClient(
            base_url="https://community-api.coinmetrics.io",
            rate_limiter=RateLimiter(rate_limit),
            cache_ttl=cache_ttl,
        )

    def get_mvrv(self, lookback_days=7):
        """Get MVRV ratio. Free tier may lag recent dates, so try progressively older."""
        for days_back in range(0, lookback_days + 30, 7):
            target = datetime.now(timezone.utc) - timedelta(days=days_back)
            date_str = target.strftime("%Y-%m-%d")
            try:
                data = self.client.get("/v4/timeseries/asset-metrics", params={
                    "assets": "btc",
                    "metrics": "CapMVRVCur",
                    "frequency": "1d",
                    "start_time": date_str,
                    "limit_per_asset": "1",
                })
                series = data.get("data", [])
                if series:
                    val = series[-1].get("CapMVRVCur")
                    if val is not None:
                        return float(val)
            except APIError as e:
                if e.status_code == 403:
                    logger.debug(f"CoinMetrics 403 for {date_str}, trying older date")
                    continue
                raise
        logger.warning("CoinMetrics MVRV unavailable on free tier, using fallback")
        return None

    def get_realized_cap(self, lookback_days=7):
        """Get realized cap. Same fallback strategy as MVRV."""
        for days_back in range(0, lookback_days + 30, 7):
            target = datetime.now(timezone.utc) - timedelta(days=days_back)
            date_str = target.strftime("%Y-%m-%d")
            try:
                data = self.client.get("/v4/timeseries/asset-metrics", params={
                    "assets": "btc",
                    "metrics": "CapRealUSD",
                    "frequency": "1d",
                    "start_time": date_str,
                    "limit_per_asset": "1",
                })
                series = data.get("data", [])
                if series:
                    val = series[-1].get("CapRealUSD")
                    if val is not None:
                        return float(val)
            except APIError as e:
                if e.status_code == 403:
                    continue
                raise
        return None

    @staticmethod
    def estimate_mvrv(market_cap, price_history_prices):
        """Fallback MVRV estimation when CoinMetrics is unavailable.

        Uses 200-day SMA of market cap as rough realized cap proxy.
        This is an approximation - clearly flagged in output.
        """
        if not price_history_prices or market_cap <= 0:
            return None
        recent = price_history_prices[-200:] if len(price_history_prices) >= 200 else price_history_prices
        avg_price = sum(recent) / len(recent)
        # Rough realized cap = avg price * circulating supply (embedded in market_cap/current_price ratio)
        current_price = price_history_prices[-1] if price_history_prices else 1
        if current_price <= 0:
            return None
        supply_est = market_cap / current_price
        realized_cap_est = avg_price * supply_est
        if realized_cap_est <= 0:
            return None
        return market_cap / realized_cap_est

    def close(self):
        self.client.close()
