"""Tests for formatters, rate limiter, cache."""
import pytest
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.formatters import format_usd, format_pct, format_hashrate, format_btc, format_compact, time_ago
from utils.rate_limiter import RateLimiter
from utils.cache import TTLCache


def test_format_usd():
    assert format_usd(67543.21) == "$67,543.21"
    assert format_usd(0) == "$0.00"
    assert format_usd(None) == "N/A"


def test_format_usd_compact():
    assert "B" in format_usd(1_234_567_890)
    assert "T" in format_usd(1_234_567_890_000)


def test_format_pct():
    assert format_pct(5.4) == "+5.40%"
    assert format_pct(-12.5) == "-12.50%"
    assert format_pct(0) == "+0.00%"
    assert format_pct(None) == "N/A"


def test_format_pct_colored():
    result = format_pct(5.0, with_color=True)
    assert "green" in result
    result = format_pct(-5.0, with_color=True)
    assert "red" in result


def test_format_hashrate():
    assert "EH/s" in format_hashrate(9.13e17)
    assert "TH/s" in format_hashrate(1e12)
    assert format_hashrate(None) == "N/A"


def test_format_btc():
    assert format_btc(0.0054321) == "0.00543210 BTC"
    assert format_btc(None) == "N/A"


def test_format_compact():
    assert format_compact(1_200_000) == "1.2M"
    assert format_compact(340_000) == "340.0K"
    assert format_compact(500) == "500"


def test_time_ago():
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    assert "s ago" in time_ago(now - timedelta(seconds=30))
    assert "m ago" in time_ago(now - timedelta(minutes=5))
    assert "h ago" in time_ago(now - timedelta(hours=2))
    assert "d ago" in time_ago(now - timedelta(days=3))


def test_rate_limiter():
    rl = RateLimiter(600)  # 10/sec
    start = time.monotonic()
    for _ in range(5):
        rl.wait()
    elapsed = time.monotonic() - start
    assert elapsed < 2  # Should be fast at 10/sec


def test_ttl_cache():
    cache = TTLCache()
    cache.set("key1", "value1", ttl=10)
    assert cache.get("key1") == "value1"

    cache.invalidate("key1")
    assert cache.get("key1") is None


def test_ttl_cache_expiry():
    cache = TTLCache()
    cache.set("key1", "value1", ttl=0.1)
    assert cache.get("key1") == "value1"
    time.sleep(0.2)
    assert cache.get("key1") is None
