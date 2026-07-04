# cache.py — simple TTL cache for user preferences
import time

CACHE_TTL = 300  # 5 seconds (adjust as needed)

class TTLCache:
    def __init__(self, ttl=CACHE_TTL):
        self._cache = {}
        self._ttl = ttl

    def get(self, key):
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return value
            else:
                del self._cache[key]
        return None

    def set(self, key, value):
        self._cache[key] = (value, time.time())

    def invalidate(self, key):
        if key in self._cache:
            del self._cache[key]

prefs_cache = TTLCache()