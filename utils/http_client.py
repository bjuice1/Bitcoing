"""HTTP client with retries, caching, and rate limiting."""
import time
import logging
import hashlib
import requests

logger = logging.getLogger("btcmonitor.http")


class APIError(Exception):
    """API request error with status code and response body."""
    def __init__(self, message, status_code=None, response_body=None, source=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.source = source


class HTTPClient:
    """HTTP client with retry logic, rate limiting, and response caching."""

    RETRYABLE_STATUS = {429, 500, 502, 503, 504}
    NON_RETRYABLE_STATUS = {400, 401, 403, 404}

    def __init__(self, base_url, rate_limiter=None, timeout=30, max_retries=3, cache_ttl=0):
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache_ttl = cache_ttl
        self._cache = {}
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BTCMonitor/1.0"})

    def get(self, path="", params=None):
        """Make a GET request with retry and caching."""
        return self._request("GET", path, params)

    def _cache_key(self, method, path, params):
        raw = f"{method}:{self.base_url}{path}:{sorted((params or {}).items())}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _request(self, method, path, params=None):
        url = f"{self.base_url}/{path.lstrip('/')}" if path else self.base_url

        # Check cache
        if self.cache_ttl > 0:
            key = self._cache_key(method, path, params)
            cached = self._cache.get(key)
            if cached and time.time() - cached["time"] < self.cache_ttl:
                return cached["data"]

        last_error = None
        for attempt in range(self.max_retries + 1):
            if self.rate_limiter:
                self.rate_limiter.wait()

            try:
                start = time.time()
                resp = self.session.request(method, url, params=params, timeout=self.timeout)
                latency = int((time.time() - start) * 1000)
                logger.debug(f"{method} {url} → {resp.status_code} ({latency}ms)")

                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except ValueError:
                        data = resp.text

                    if self.cache_ttl > 0:
                        self._cache[self._cache_key(method, path, params)] = {
                            "data": data, "time": time.time()
                        }
                    return data

                if resp.status_code in self.NON_RETRYABLE_STATUS:
                    raise APIError(
                        f"HTTP {resp.status_code} from {url}",
                        status_code=resp.status_code,
                        response_body=resp.text,
                    )

                if resp.status_code in self.RETRYABLE_STATUS:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else min(2 ** attempt * 2, 60)
                    logger.warning(f"Retryable {resp.status_code} from {url}, waiting {wait:.1f}s (attempt {attempt + 1})")
                    last_error = APIError(f"HTTP {resp.status_code}", status_code=resp.status_code)
                    time.sleep(wait)
                    continue

                raise APIError(f"Unexpected HTTP {resp.status_code}", status_code=resp.status_code)

            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error for {url}: {e} (attempt {attempt + 1})")
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt * 2, 60))

        raise last_error or APIError(f"Max retries exceeded for {url}")
