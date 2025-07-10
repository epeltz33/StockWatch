from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import logging
import os
from dotenv import load_dotenv
from polygon import RESTClient
from app.extensions import db
from app.models import Stock
from sqlalchemy.exc import IntegrityError

load_dotenv()
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Polygon client
polygon_client = RESTClient(os.getenv('POLYGON_API_KEY'))


def get_stock_price(symbol: str) -> Optional[float]:
    """Get current stock price from Polygon API"""
    try:
        date = get_most_recent_trading_day()
        resp = polygon_client.get_daily_open_close_agg(symbol, date)
        return resp.close if resp else None
    except Exception as e:
        logger.error(f"Error fetching stock price for {symbol}: {str(e)}")
        return None


def get_stock_data(symbol: str, from_date: str, to_date: str) -> List[Dict[str, Any]]:
    """Get historical stock data from Polygon API"""
    try:
        resp = polygon_client.get_aggs(symbol, 1, "day", from_date, to_date)
        if resp and hasattr(resp, 'results') and len(resp.results) > 0:
            return [
                {
                    "date": datetime.fromtimestamp(item.t / 1000).strftime('%Y-%m-%d'),
                    "close": item.c,
                    "volume": item.v
                }
                for item in resp.results
            ]
        return []
    except Exception as e:
        logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
        return []


def get_company_details(symbol: str) -> Dict[str, Any]:
    """Get company details from Polygon API"""
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
    """Calculate the most recent trading day"""
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
    """Create a new stock entry in the database."""
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
    """Delete a stock from the database."""
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