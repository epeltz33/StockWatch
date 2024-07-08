from app.models import Stock
from app import db
from sqlalchemy.exc import IntegrityError
from polygon import RESTClient
from datetime import datetime, timedelta
import pytz
import os

polygon_client = RESTClient(os.getenv('POLYGON_API_KEY'))

# Database-related functions


def get_all_stocks():
    return Stock.query.all()


def get_stock_by_symbol(symbol):
    return Stock.query.filter_by(symbol=symbol).first()


def create_stock(symbol, name):
    stock = Stock(symbol=symbol, name=name)
    db.session.add(stock)
    try:
        db.session.commit()
        return stock
    except IntegrityError:
        db.session.rollback()
        return None


def delete_stock(symbol):
    stock = get_stock_by_symbol(symbol)
    if stock:
        db.session.delete(stock)
        db.session.commit()
        return True
    return False

# Adjusted helper function


def get_most_recent_trading_day():
    now = datetime.now()
    market_close_time = now.replace(
        hour=16, minute=0, second=0, microsecond=0)  # Market close time is 4 PM

    # If it's before market close and today is a weekday, use yesterday's date if the market is closed today, otherwise use today's date
    if now <= market_close_time and now.weekday() < 5:
        most_recent_trading_day = now - \
            timedelta(days=1) if now.weekday() < 5 else now
    else:
        # If it's past market close or a weekend, move to the previous trading day
        if now.weekday() == 5:  # Saturday
            days_to_subtract = 1
        elif now.weekday() == 6:  # Sunday
            days_to_subtract = 2
        else:  # Past market close on a weekday
            days_to_subtract = 1
        most_recent_trading_day = now - timedelta(days=days_to_subtract)

    # Ensure that if today is Monday, we adjust to the previous Friday
    if most_recent_trading_day.weekday() == 5:  # Saturday
        most_recent_trading_day -= timedelta(days=1)
    elif most_recent_trading_day.weekday() == 6:  # Sunday
        most_recent_trading_day -= timedelta(days=2)

    return most_recent_trading_day.strftime('%Y-%m-%d')


# Polygon.io API-related functions


def get_stock_price(symbol):
    try:
        date = get_most_recent_trading_day()
        resp = polygon_client.get_daily_open_close_agg(symbol, date)
        if resp:
            return resp.close  # Use the closing price
    except Exception as e:
        print(f"Error fetching stock price: {e}")
        return None


def get_stock_data(symbol, from_date, to_date):
    try:
        resp = polygon_client.get_aggs(symbol, 1, "day", from_date, to_date)
        if resp and len(resp.results) > 0:
            return [{"date": datetime.fromtimestamp(item.t / 1000).strftime('%Y-%m-%d'),
                     "close": item.c,
                     "volume": item.v} for item in resp.results]
        else:
            return []
    except Exception as e:
        print(f"Error fetching stock data: {e}")
        return []


def get_company_details(symbol):
    try:
        resp = polygon_client.get_ticker_details(symbol)
        return {
            "name": resp.name,
            "market_cap": resp.market_cap,
            "primary_exchange": resp.primary_exchange,
            "description": resp.description
        }
    except Exception as e:
        print(f"Error fetching company details: {e}")
        return {}
