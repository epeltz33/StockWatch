from app.models import Stock
from app import db
from app.extensions import db, cache  # Import cache from extensions
from sqlalchemy.exc import IntegrityError
from polygon import RESTClient
from datetime import datetime, timedelta
import pytz
import os
import json
from typing import Optional, Dict, List, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

polygon_client = RESTClient(os.getenv('POLYGON_API_KEY'))

# Cache timeouts (in seconds)
CACHE_TIMEOUT = {
    'price': 300,  # 5 minutes for current price
    'details': 86400,  # 24 hours for company details
    'historical': 3600,  # 1 hour for historical data
}


class StockDataCache:
    @staticmethod
    def get_cache_key(symbol: str, data_type: str, **kwargs) -> str:
        """Generate a unique cache key for different types of stock data."""
        base_key = f"stock:{symbol}:{data_type}"
        if kwargs:
            # Sort kwargs to ensure consistent cache keys
            param_str = ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
            return f"{base_key}:{param_str}"
        return base_key


def get_stock_price(symbol: str) -> Optional[float]:
    """Get current stock price with caching."""
    cache_key = StockDataCache.get_cache_key(symbol, 'price')

    # Try to get from cache first
    cached_price = cache.get(cache_key)
    if cached_price is not None:
        logger.info(f"Cache hit for price data: {symbol}")
        return cached_price

    try:
        date = get_most_recent_trading_day()
        resp = polygon_client.get_daily_open_close_agg(symbol, date)
        if resp:
            price = resp.close
            # Cache the price
            cache.set(cache_key, price, timeout=CACHE_TIMEOUT['price'])
            logger.info(f"Cached price data for: {symbol}")
            return price
    except Exception as e:
        logger.error(f"Error fetching stock price for {symbol}: {e}")
        return None


def get_stock_data(symbol: str, from_date: str, to_date: str) -> List[Dict[str, Any]]:
    """Get historical stock data with caching."""
    cache_key = StockDataCache.get_cache_key(
        symbol, 'historical',
        from_date=from_date,
        to_date=to_date
    )

    # Try to get from cache first
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        logger.info(f"Cache hit for historical data: {symbol}")
        return cached_data

    try:
        resp = polygon_client.get_aggs(symbol, 1, "day", from_date, to_date)
        if resp and len(resp.results) > 0:
            data = [{"date": datetime.fromtimestamp(item.t / 1000).strftime('%Y-%m-%d'),
                     "close": item.c,
                     "volume": item.v} for item in resp.results]

            # Cache the historical data
            cache.set(cache_key, data, timeout=CACHE_TIMEOUT['historical'])
            logger.info(f"Cached historical data for: {symbol}")
            return data
        return []
    except Exception as e:
        logger.error(f"Error fetching historical data for {symbol}: {e}")
        return []


def get_company_details(symbol: str) -> Dict[str, Any]:
    """Get company details with caching."""
    cache_key = StockDataCache.get_cache_key(symbol, 'details')

    # Try to get from cache first
    cached_details = cache.get(cache_key)
    if cached_details is not None:
        logger.info(f"Cache hit for company details: {symbol}")
        return cached_details

    try:
        resp = polygon_client.get_ticker_details(symbol)
        details = {
            "name": resp.name,
            "market_cap": resp.market_cap,
            "primary_exchange": resp.primary_exchange,
            "description": resp.description
        }

        # Cache the company details
        cache.set(cache_key, details, timeout=CACHE_TIMEOUT['details'])
        logger.info(f"Cached company details for: {symbol}")
        return details
    except Exception as e:
        logger.error(f"Error fetching company details for {symbol}: {e}")
        return {}

# Database-related functions


def get_all_stocks():
    return Stock.query.all()


def get_stock_by_symbol(symbol: str) -> Optional[Stock]:
    return Stock.query.filter_by(symbol=symbol).first()


def create_stock(symbol: str, name: str) -> Optional[Stock]:
    stock = Stock(symbol=symbol, name=name)
    db.session.add(stock)
    try:
        db.session.commit()
        return stock
    except IntegrityError:
        db.session.rollback()
        return None


def delete_stock(symbol: str) -> bool:
    stock = get_stock_by_symbol(symbol)
    if stock:
        db.session.delete(stock)
        db.session.commit()
        return True
    return False


def get_most_recent_trading_day() -> str:
    """Calculate the most recent trading day."""
    now = datetime.now()
    market_close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)

    if now <= market_close_time and now.weekday() < 5:
        most_recent_trading_day = now - \
            timedelta(days=1) if now.weekday() < 5 else now
    else:
        days_to_subtract = 1
        if now.weekday() == 5:  # Saturday
            days_to_subtract = 1
        elif now.weekday() == 6:  # Sunday
            days_to_subtract = 2
        most_recent_trading_day = now - timedelta(days=days_to_subtract)

    if most_recent_trading_day.weekday() == 5:
        most_recent_trading_day -= timedelta(days=1)
    elif most_recent_trading_day.weekday() == 6:
        most_recent_trading_day -= timedelta(days=2)

    return most_recent_trading_day.strftime('%Y-%m-%d')


def clear_stock_cache(symbol: str) -> None:
    """Clear all cached data for a specific stock."""
    cache_types = ['price', 'details', 'historical']
    for cache_type in cache_types:
        cache_key = StockDataCache.get_cache_key(symbol, cache_type)
        cache.delete(cache_key)
        logger.info(f"Cleared {cache_type} cache for: {symbol}")
