"""Token bucket rate limiter."""
import time
import threading


class RateLimiter:
    """Token bucket rate limiter, thread-safe."""

    def __init__(self, calls_per_minute):
        self.rate = calls_per_minute / 60.0  # tokens per second
        self.max_tokens = calls_per_minute
        self.tokens = float(calls_per_minute)
        self.last_time = time.monotonic()
        self._lock = threading.Lock()

    def wait(self):
        """Block until a token is available."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_time
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.rate)
            self.last_time = now

            if self.tokens < 1:
                sleep_time = (1 - self.tokens) / self.rate
                time.sleep(sleep_time)
                self.tokens = 0
            else:
                self.tokens -= 1
