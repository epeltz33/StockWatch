from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import logging
import os
from polygon import RESTClient
from app.extensions import db, cache
from app.models import Stock
from sqlalchemy.exc import IntegrityError
from app.utils.cache_manager import create_cache_decorator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Polygon client
polygon_client = RESTClient(os.getenv('POLYGON_API_KEY'))

# Create cache decorator instance
cache_stock_data = create_cache_decorator(cache)

@cache_stock_data
def get_stock_price(symbol: str) -> Optional[float]:
    """
    Get current stock price with caching.

    Args:
        symbol (str): Stock symbol (e.g., 'AAPL')

    Returns:
        Optional[float]: Current stock price or None if unavailable
    """
    try:
        date = get_most_recent_trading_day()
        resp = polygon_client.get_daily_open_close_agg(symbol, date)
        return resp.close if resp else None
    except Exception as e:
        logger.error(f"Error fetching stock price for {symbol}: {str(e)}")
        return None

@cache_stock_data
def get_stock_data(symbol: str, from_date: str, to_date: str) -> List[Dict[str, Any]]:
    """
    Get historical stock data with caching.

    Args:
        symbol (str): Stock symbol (e.g., 'AAPL')
        from_date (str): Start date in 'YYYY-MM-DD' format
        to_date (str): End date in 'YYYY-MM-DD' format

    Returns:
        List[Dict[str, Any]]: List of historical stock data points
    """
    try:
        resp = polygon_client.get_aggs(symbol, 1, "day", from_date, to_date)
        if resp:
            return [
                {
                    "date": datetime.fromtimestamp(result.timestamp/1000).strftime('%Y-%m-%d'),
                    "close": result.close,
                    "volume": result.volume,
                    "open": result.open,
                    "high": result.high,
                    "low": result.low,
                    "transactions": result.transactions
                }
                for result in resp
            ]
        return []
    except Exception as e:
        logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
        return []

@cache_stock_data
def get_company_details(symbol: str) -> Dict[str, Any]:
    """
    Get company details with caching.

    Args:
        symbol (str): Stock symbol (e.g., 'AAPL')

    Returns:
        Dict[str, Any]: Company details including name, market cap, etc.
    """
    try:
        resp = polygon_client.get_ticker_details(symbol)
        if resp:
            return {
                "name": resp.name,
                "market_cap": resp.market_cap,
                "primary_exchange": resp.primary_exchange,
                "description": resp.description,
                "sector": getattr(resp, 'sector', 'N/A'),
                "industry": getattr(resp, 'industry', 'N/A'),
                "website": getattr(resp, 'url', 'N/A')
            }
        return {}
    except Exception as e:
        logger.error(f"Error fetching company details for {symbol}: {str(e)}")
        return {}

def get_most_recent_trading_day() -> str:
    """
    Calculate the most recent trading day, accounting for weekends and market hours.

    Returns:
        str: Date string in 'YYYY-MM-DD' format
    """
    now = datetime.now()
    market_close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)

    if now <= market_close_time and now.weekday() < 5:
        most_recent_trading_day = now - timedelta(days=1) if now.weekday() > 0 else now
    else:
        days_to_subtract = 1
        if now.weekday() == 5:  # Saturday
            days_to_subtract = 1
        elif now.weekday() == 6:  # Sunday
            days_to_subtract = 2
        most_recent_trading_day = now - timedelta(days=days_to_subtract)

    if most_recent_trading_day.weekday() == 5:  # If it's Saturday
        most_recent_trading_day -= timedelta(days=1)
    elif most_recent_trading_day.weekday() == 6:  # If it's Sunday
        most_recent_trading_day -= timedelta(days=2)

    return most_recent_trading_day.strftime('%Y-%m-%d')

# Database-related functions
def get_all_stocks() -> List[Stock]:
    """Get all stocks from the database."""
    return Stock.query.all()

def get_stock_by_symbol(symbol: str) -> Optional[Stock]:
    """Get a stock by its symbol from the database."""
    return Stock.query.filter_by(symbol=symbol).first()

def create_stock(symbol: str, name: str) -> Optional[Stock]:
    """
    Create a new stock entry in the database.

    Args:
        symbol (str): Stock symbol
        name (str): Company name

    Returns:
        Optional[Stock]: Created stock object or None if creation failed
    """
    stock = Stock(symbol=symbol, name=name)
    db.session.add(stock)
    try:
        db.session.commit()
        return stock
    except IntegrityError:
        db.session.rollback()
        logger.error(f"Failed to create stock {symbol}: IntegrityError")
        return None

def delete_stock(symbol: str) -> bool:
    """
    Delete a stock from the database.

    Args:
        symbol (str): Stock symbol to delete

    Returns:
        bool: True if deletion was successful, False otherwise
    """
    stock = get_stock_by_symbol(symbol)
    if stock:
        try:
            db.session.delete(stock)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete stock {symbol}: {str(e)}")
            return False
    return False

def clear_stock_cache(symbol: str) -> None:
    """
    Clear all cached data for a specific stock.

    Args:
        symbol (str): Stock symbol to clear cache for
    """
    try:
        # Get the cache instance through the decorator
        stock_cache = cache_stock_data.cache_instance
        stock_cache.clear_symbol_cache(symbol)
        logger.info(f"Successfully cleared cache for stock {symbol}")
    except Exception as e:
        logger.error(f"Error clearing cache for stock {symbol}: {str(e)}")