import logging
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timedelta
from functools import wraps
from flask_caching import Cache
from flask import current_app

# Set up logging
logger = logging.getLogger(__name__)

class StockCache:
    """Enhanced caching system for stock data with fallback mechanisms."""

    def __init__(self, cache: Cache):
        self.cache = cache
        # Increase historical data cache timeout to 24 hours since it doesn't change frequently
        self.timeouts = {
            'price': 300,        # 5 minutes
            'details': 86400,    # 24 hours
            'historical': 86400, # 24 hours (increased from 3600)
            'stock_data': 86400, # 24 hours for get_stock_data function
            'fallback': 600      # 10 minutes (fallback data lifetime)
        }

    def _get_cache_key(self, symbol: str, data_type: str, **kwargs) -> str:
        """Generate a unique cache key with optional parameters."""
        base_key = f"stock:{symbol.upper()}:{data_type}"
        if kwargs:
            # Create a sorted, deterministic string from kwargs
            param_str = ':'.join(f"{k}={v}" for k, v in sorted(kwargs.items()))
            key = f"{base_key}:{param_str}"
            logger.debug(f"Generated cache key with params: {key}")
            return key
        logger.debug(f"Generated simple cache key: {base_key}")
        return base_key

    def get_cached_data(self, symbol: str, data_type: str, **kwargs) -> Optional[Any]:
        """Retrieve data from cache with logging."""
        cache_key = self._get_cache_key(symbol, data_type, **kwargs)
        data = self.cache.get(cache_key)
        if data is not None:
            logger.info(f"Cache hit for {data_type} data: {symbol} with params: {kwargs if kwargs else 'none'}")
            return data
        logger.info(f"Cache miss for {data_type} data: {symbol} with params: {kwargs if kwargs else 'none'}")
        return None

    def set_cached_data(self, symbol: str, data_type: str, data: Any, **kwargs) -> None:
        """Store data in cache with appropriate timeout."""
        cache_key = self._get_cache_key(symbol, data_type, **kwargs)
        timeout = self.timeouts.get(data_type, self.timeouts['fallback'])
        self.cache.set(cache_key, data, timeout=timeout)
        logger.info(f"Cached {data_type} data for: {symbol} with timeout: {timeout}s")

    def get_or_create(self, symbol: str, data_type: str, creator_func, **kwargs) -> Optional[Any]:
        """Get data from cache or create it using the provided function."""
        data = self.get_cached_data(symbol, data_type, **kwargs)
        if data is not None:
            return data

        try:
            logger.info(f"Creating new data for {symbol} ({data_type})")
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

    def clear_symbol_cache(self, symbol: str) -> None:
        """Clear all cached data for a specific stock symbol."""
        # This method would need to be improved for production to actually find and clear all keys
        # As implemented, it only warns that this isn't fully implemented
        logger.warning(f"clear_symbol_cache called for {symbol}, but full implementation requires iterating all cache keys")
        # For SimpleCache, we can't easily list and remove keys with a prefix

def create_cache_decorator(cache_instance: Cache):
    """Creates a decorator for caching stock data functions."""
    def cache_stock_data(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            stock_cache = StockCache(cache_instance)

            # Extract symbol
            symbol = args[0] if args else kwargs.get('symbol')
            if not symbol:
                logger.warning(f"No symbol provided to {func.__name__}, cannot cache")
                return func(*args, **kwargs)

            # Extract data_type from function name
            data_type = func.__name__.replace('get_', '')

            # Create cache_kwargs copy to avoid modifying the original kwargs
            cache_kwargs = kwargs.copy()

            # Special handling for get_stock_data function with date parameters
            if data_type == 'stock_data' and func.__name__ == 'get_stock_data':
                # Extract date parameters regardless of whether they're passed as args or kwargs
                from_date = kwargs.get('from_date')
                to_date = kwargs.get('to_date')

                if not from_date and len(args) > 1:
                    from_date = args[1]
                if not to_date and len(args) > 2:
                    to_date = args[2]

                # Add date params to cache_kwargs for caching only
                if from_date and to_date:
                    logger.debug(f"Caching {data_type} for {symbol} with date range: {from_date} to {to_date}")
                    cache_kwargs['from_date'] = from_date
                    cache_kwargs['to_date'] = to_date

            # Use cache_kwargs for caching but regular args/kwargs for function execution
            return stock_cache.get_or_create(
                symbol,
                data_type,
                lambda: func(*args, **kwargs),  # Original function call
                **cache_kwargs  # Use modified kwargs only for cache key
            )

        # Store cache instance on the wrapper function to allow direct access
        wrapper.cache_instance = StockCache(cache_instance)
        return wrapper
    return cache_stock_data