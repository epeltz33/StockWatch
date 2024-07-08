from app.models import Stock
from app import db
from sqlalchemy.exc import IntegrityError
from polygon import RESTClient
from datetime import datetime, timedelta
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

# Polygon.io API-related functions


def get_stock_price(symbol):
    try:
        resp = polygon_client.get_last_trade(symbol)
        return resp.price
    except Exception as e:
        print(f"Error fetching stock price: {e}")
        return None


def get_stock_data(symbol, from_date, to_date):
    try:
        resp = polygon_client.get_aggs(symbol, 1, "day", from_date, to_date)
        return [{"date": datetime.fromtimestamp(item.timestamp/1000).strftime('%Y-%m-%d'),
                 "close": item.close,
                 "volume": item.volume} for item in resp]
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

# Utility function to get both price and details


def get_stock_info(symbol):
    price = get_stock_price(symbol)
    details = get_company_details(symbol)
    stock = get_stock_by_symbol(symbol)

    return {
        "symbol": symbol,
        "price": price,
        "details": details,
        "in_database": stock is not None
    }
