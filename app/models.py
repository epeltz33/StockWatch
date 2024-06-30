from app import db
from datetime import datetime


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    watchlists = db.relationship('Watchlist', backref='user', lazy='dynamic')


class Watchlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    stocks = db.relationship('Stock', secondary='watchlist_stocks')


class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10), unique=True)
    name = db.Column(db.String(100))


watchlist_stocks = db.Table('watchlist_stocks',
                            db.Column('watchlist_id', db.Integer, db.ForeignKey('watchlist.id')),
                            db.Column('stock_id', db.Integer, db.ForeignKey('stock.id'))
                            )
