from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    # Increase the length of the password hash
    password_hash = db.Column(db.String(256))
    watchlists = db.relationship(
        'Watchlist', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Watchlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stocks = db.relationship('Stock', secondary='watchlist_stocks',
                            cascade='all, delete-orphan', single_parent=True)

    def __init__(self, name, user_id):
        self.name = name
        self.user_id = user_id


class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(100))

    def __init__(self, symbol, name):
        self.symbol = symbol
        self.name = name


watchlist_stocks = db.Table('watchlist_stocks',
                            db.Column('watchlist_id', db.Integer, db.ForeignKey(
                                'watchlist.id', ondelete='CASCADE'), primary_key=True),
                            db.Column('stock_id', db.Integer, db.ForeignKey(
                                'stock.id', ondelete='CASCADE'), primary_key=True)
                            )
