from __future__ import annotations

from flask import current_app
from .cache_manager import StockCache
from app.extensions import cache


def test_cache_functionality(symbol: str) -> None:
    """Simple cache test utility used by CLI command."""
    stock_cache = StockCache(cache)
    # This is a placeholder demonstrating cache usage.
    if stock_cache.get_cached_data(symbol, "price") is None:
        stock_cache.set_cached_data(symbol, "price", {"tested": True})
        current_app.logger.info("Cached test data for %s", symbol)
    else:
        current_app.logger.info("Cache hit for %s", symbol)
