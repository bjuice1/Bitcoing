"""Blockchain.com API client for network HR and difficulty."""
import logging
from utils.http_client import HTTPClient
from utils.rate_limiter import RateLimiter

logger = logging.getLogger("btcmonitor.blockchain")


class BlockchainInfoClient:
    def __init__(self, rate_limit=30, cache_ttl=300):
        self.client = HTTPClient(
            base_url="https://api.blockchain.info",
            rate_limiter=RateLimiter(rate_limit),
            cache_ttl=cache_ttl,
        )

    def get_hash_rate(self, timespan="30days"):
        data = self.client.get("/charts/hash-rate", params={
            "timespan": timespan,
            "format": "json",
        })
        values = data.get("values", [])
        if not values:
            return {"current": 0, "history": []}

        # Values are in TH/s (scientific notation)
        history = []
        for v in values:
            th_per_sec = float(v.get("y", 0))
            history.append({
                "timestamp": v.get("x", 0),
                "hash_rate_th": th_per_sec,
            })

        current = history[-1]["hash_rate_th"] if history else 0
        return {"current": current, "history": history}

    def get_difficulty(self, timespan="30days"):
        data = self.client.get("/charts/difficulty", params={
            "timespan": timespan,
            "format": "json",
        })
        values = data.get("values", [])
        if not values:
            return {"current": 0, "history": []}

        history = [{"timestamp": v.get("x", 0), "difficulty": float(v.get("y", 0))}
                   for v in values]
        current = history[-1]["difficulty"] if history else 0
        return {"current": current, "history": history}

    def get_hash_rate_change(self, period_days=30):
        result = self.get_hash_rate(timespan=f"{period_days}days")
        history = result.get("history", [])
        if len(history) < 2:
            return 0.0
        start_val = history[0]["hash_rate_th"]
        end_val = history[-1]["hash_rate_th"]
        if start_val == 0:
            return 0.0
        return ((end_val - start_val) / start_val) * 100

    def close(self):
        self.client.close()
