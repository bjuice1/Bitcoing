"""Generic TTL cache."""
import time
import threading


class TTLCache:
    """Thread-safe key-value cache with per-key TTL."""

    def __init__(self):
        self._store = {}
        self._lock = threading.Lock()

    def get(self, key):
        """Get value if exists and not expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.time() > entry["expires"]:
                del self._store[key]
                return None
            return entry["value"]

    def set(self, key, value, ttl=300):
        """Set key with TTL in seconds."""
        with self._lock:
            self._store[key] = {
                "value": value,
                "expires": time.time() + ttl,
            }

    def invalidate(self, key):
        """Remove a specific key."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        """Remove all entries."""
        with self._lock:
            self._store.clear()
