"""Alternative.me Fear & Greed Index client."""
import logging
from datetime import datetime, timezone
from utils.http_client import HTTPClient
from utils.rate_limiter import RateLimiter

logger = logging.getLogger("btcmonitor.feargreed")


class FearGreedClient:
    def __init__(self, rate_limit=30, cache_ttl=600):
        self.client = HTTPClient(
            base_url="https://api.alternative.me/fng",
            rate_limiter=RateLimiter(rate_limit),
            cache_ttl=cache_ttl,
        )

    def get_current(self):
        data = self.client.get("/", params={"limit": "1"})
        entries = data.get("data", [])
        if not entries:
            return {"value": 50, "label": "Neutral"}
        entry = entries[0]
        return {
            "value": int(entry.get("value", 50)),
            "label": entry.get("value_classification", "Neutral"),
        }

    def get_history(self, days=365):
        data = self.client.get("/", params={"limit": str(days)})
        entries = data.get("data", [])
        result = []
        for entry in entries:
            ts = int(entry.get("timestamp", 0))
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            result.append({
                "date": dt.strftime("%Y-%m-%d"),
                "value": int(entry.get("value", 50)),
                "label": entry.get("value_classification", "Neutral"),
            })
        return list(reversed(result))  # Oldest first

    def close(self):
        self.client.close()
