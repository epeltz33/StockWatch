from typing import Any, Dict
from flask_caching import Cache

DEFAULT_TIMEOUTS: Dict[str, int] = {
    'price': 300,       # 5 minutes
    'details': 86400,   # 24 hours
    'historical': 3600, # 1 hour
    'fallback': 600     # default/fallback timeout
}

class StockCache:
    """Simple wrapper around Flask-Caching for stock data."""

    def __init__(self, cache: Cache, timeouts: Dict[str, int] | None = None):
        self.cache = cache
        self.timeouts = timeouts or DEFAULT_TIMEOUTS

    def _get_cache_key(self, symbol: str, data_type: str, **kwargs: Any) -> str:
        key_parts = [f"stock:{symbol}:{data_type}"]
        if kwargs:
            for k, v in sorted(kwargs.items()):
                key_parts.append(f"{k}={v}")
        return ":".join(key_parts)

    def get_cached_data(self, symbol: str, data_type: str, **kwargs: Any) -> Any:
        key = self._get_cache_key(symbol, data_type, **kwargs)
        return self.cache.get(key)

    def set_cached_data(self, symbol: str, data_type: str, data: Any, **kwargs: Any) -> None:
        key = self._get_cache_key(symbol, data_type, **kwargs)
        timeout = self.timeouts.get(data_type, self.timeouts.get('fallback', 300))
        self.cache.set(key, data, timeout=timeout)
