from app.extensions import db
from app.models import Stock
from sqlalchemy.exc import IntegrityError
from polygon import RESTClient
from datetime import datetime
import os

polygon_client = RESTClient(os.getenv('POLYGON_API_KEY'))


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


def get_stock_data(symbol, from_date, to_date):
    """Fetch stock data from Polygon.io"""
    aggs = polygon_client.get_aggs(symbol, 1, "day", from_date, to_date)
    return [{"date": datetime.fromtimestamp(a.timestamp / 1000).strftime('%Y-%m-%d'),
             "open": a.open,
             "high": a.high,
             "low": a.low,
             "close": a.close,
             "volume": a.volume} for a in aggs]


def get_current_price(symbol):
    """Get the current price of a stock from Polygon.io"""
    last_trade = polygon_client.get_last_trade(symbol)
    return last_trade.price

# Add more stock-related services as needed
