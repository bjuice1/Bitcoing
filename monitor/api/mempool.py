"""mempool.space API client for difficulty adjustment and mining data."""
import logging
from utils.http_client import HTTPClient
from utils.rate_limiter import RateLimiter

logger = logging.getLogger("btcmonitor.mempool")


class MempoolClient:
    def __init__(self, rate_limit=60, cache_ttl=120):
        self.client = HTTPClient(
            base_url="https://mempool.space/api",
            rate_limiter=RateLimiter(rate_limit),
            cache_ttl=cache_ttl,
        )

    def get_difficulty_adjustment(self):
        data = self.client.get("/v1/difficulty-adjustment")
        return {
            "progress_pct": data.get("progressPercent", 0),
            "estimated_change_pct": data.get("difficultyChange", 0),
            "remaining_blocks": data.get("remainingBlocks", 0),
            "remaining_time_ms": data.get("remainingTime", 0),
            "avg_block_time": data.get("timeAvg", 600000) / 1000,  # ms to seconds
        }

    def get_hashrate_history(self, period="1m"):
        data = self.client.get(f"/v1/mining/hashrate/{period}")
        hashrates = data.get("hashrates", [])
        difficulty = data.get("difficulty", [])
        current_hashrate = data.get("currentHashrate", 0)
        current_difficulty = data.get("currentDifficulty", 0)
        return {
            "current_hashrate": current_hashrate,
            "current_difficulty": current_difficulty,
            "hashrate_history": hashrates,
            "difficulty_history": difficulty,
        }

    def close(self):
        self.client.close()
