from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    # Increase the length of the password hash
    password_hash = db.Column(db.String(256))
    watchlists = db.relationship(
        "Watchlist", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    transactions = db.relationship(
        "Transaction", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Watchlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    stocks = db.relationship(
        "Stock", secondary="watchlist_stocks", cascade="all, delete-orphan", single_parent=True
    )

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


class Transaction(db.Model):
    """A buy or sell in the user's portfolio, stored as an immutable ledger row.

    Positions, cost basis, and P/L are always derived by replaying a user's
    transactions in order (see app/services/portfolio_services.py) rather than
    stored, so the ledger stays the single source of truth. Each user has one
    implicit portfolio; a portfolio_id column can be added later if multiple
    portfolios per user are ever needed.

    Money columns use Numeric, never Float: binary floats can't represent
    amounts like 0.10 exactly and drift under accumulation.
    """

    # 'transaction' is a reserved word in PostgreSQL
    __tablename__ = "portfolio_transaction"
    __table_args__ = (
        db.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_transaction_side"),
        db.CheckConstraint("quantity > 0", name="ck_transaction_quantity_positive"),
        db.CheckConstraint("price >= 0", name="ck_transaction_price_non_negative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_id = db.Column(db.Integer, db.ForeignKey("stock.id"), nullable=False, index=True)
    side = db.Column(db.String(4), nullable=False)  # 'BUY' | 'SELL'
    quantity = db.Column(db.Numeric(18, 6), nullable=False)
    price = db.Column(db.Numeric(18, 4), nullable=False)  # per share
    executed_at = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    stock = db.relationship("Stock")


watchlist_stocks = db.Table(
    "watchlist_stocks",
    db.Column(
        "watchlist_id",
        db.Integer,
        db.ForeignKey("watchlist.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "stock_id", db.Integer, db.ForeignKey("stock.id", ondelete="CASCADE"), primary_key=True
    ),
)
