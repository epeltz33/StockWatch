from app.models import Stock
from app import db
from sqlalchemy.exc import IntegrityError
from polygon import RESTClient
from datetime import datetime, timedelta
import os

polygon_client = RESTClient(os.getenv('POLYGON_API_KEY'))

# Existing database-related functions


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

# New Polygon.io API-related functions


def get_stock_price(symbol):
    try:
        resp = polygon_client.get_last_trade(symbol)
        return resp.price
    except Exception as e:
        # Handle the exception here
        print(f"Error fetching stock price: {e}")
        return None
