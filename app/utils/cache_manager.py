import logging
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timedelta
from functools import wraps
from flask_caching import Cache
from flask import current_app

logger = logging.getLogger(__name__)

class StockCache:
    """Enhanced caching system for stock data with fallback mechanisms."""

    def __init__(self, cache: Cache):
        self.cache = cache
        self.timeouts = {
            'price': 300,        # 5 minutes
            'details': 86400,    # 24 hours
            'historical': 3600,  # 1 hour
            'fallback': 600      # 10 minutes (fallback data lifetime)
        }

    def _get_cache_key(self, symbol: str, data_type: str, **kwargs) -> str:
        """Generate a unique cache key with optional parameters."""
        base_key = f"stock:{symbol.upper()}:{data_type}"
        if kwargs:
            param_str = ':'.join(f"{k}={v}" for k, v in sorted(kwargs.items()))
            return f"{base_key}:{param_str}"
        return base_key

    def get_cached_data(self, symbol: str, data_type: str, **kwargs) -> Optional[Any]:
        """Retrieve data from cache with logging."""
        cache_key = self._get_cache_key(symbol, data_type, **kwargs)
        data = self.cache.get(cache_key)
        if data is not None:
            logger.info(f"Cache hit for {data_type} data: {symbol}")
            return data
        logger.info(f"Cache miss for {data_type} data: {symbol}")
        return None

    def set_cached_data(self, symbol: str, data_type: str, data: Any, **kwargs) -> None:
        """Store data in cache with appropriate timeout."""
        cache_key = self._get_cache_key(symbol, data_type, **kwargs)
        timeout = self.timeouts.get(data_type, self.timeouts['fallback'])
        self.cache.set(cache_key, data, timeout=timeout)
        logger.info(f"Cached {data_type} data for: {symbol}")

    def get_or_create(self, symbol: str, data_type: str, creator_func, **kwargs) -> Optional[Any]:
        """Get data from cache or create it using the provided function."""
        data = self.get_cached_data(symbol, data_type, **kwargs)
        if data is not None:
            return data

        try:
            data = creator_func()
            if data:
                self.set_cached_data(symbol, data_type, data, **kwargs)
            return data
        except Exception as e:
            logger.error(f"Error creating {data_type} data for {symbol}: {str(e)}")
            return self.get_fallback_data(symbol, data_type)

    def get_fallback_data(self, symbol: str, data_type: str) -> Optional[Any]:
        """Retrieve fallback data when primary data is unavailable."""
        fallback_key = self._get_cache_key(symbol, f"{data_type}_fallback")
        return self.cache.get(fallback_key)

    def set_fallback_data(self, symbol: str, data_type: str, data: Any) -> None:
        """Store fallback data with extended timeout."""
        fallback_key = self._get_cache_key(symbol, f"{data_type}_fallback")
        self.cache.set(fallback_key, data, timeout=self.timeouts['fallback'])

def create_cache_decorator(cache_instance: Cache):
    """Creates a decorator for caching stock data functions."""
    def cache_stock_data(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            stock_cache = StockCache(cache_instance)

            # Extract symbol and data_type from function call
            symbol = args[0] if args else kwargs.get('symbol')
            data_type = func.__name__.replace('get_', '')

            return stock_cache.get_or_create(
                symbol,
                data_type,
                lambda: func(*args, **kwargs),
                **kwargs
            )
        return wrapper
    return cache_stock_data