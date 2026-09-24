"""Where the dashboard's data comes from.

The Dash layer reads and writes only through one of these two sources:

* LiveSource — the signed-in user's watchlists and portfolio, with prices
  from the market-data provider. Mounted at /dash/ behind login.
* SampleSource — fixed synthetic data from app.services.sample_data for the
  public demo at /demo/. It never calls the provider, never touches the
  database, never reads the current user, and refuses every mutation.

Each Dash app is built with exactly one source, chosen on the server when the
app is mounted. Nothing a browser sends can move the demo onto live data or
account data: the demo app has no code path that reaches them.
"""

from dataclasses import dataclass
from datetime import date

from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Stock, Transaction, Watchlist
from app.services import portfolio_services, sample_data
from app.services.stock_services import (
    QuoteBatch,
    get_company_details,
    get_intraday_stock_data,
    get_most_recent_trading_day,
    get_quote_batch,
    get_stock_data,
)

# "MAX" asks the API for everything it has; plans with limited history simply
# return less, and period availability adapts to what actually came back.
MAX_HISTORY_START_DATE = "1970-01-01"
WATCHLIST_NAME_MAX = 64


class ReadOnlyDemoError(PermissionError):
    """Raised by SampleSource for every mutation: the demo is read-only."""


class WatchlistError(ValueError):
    """A watchlist edit the user can correct (shown as a toast)."""


@dataclass(frozen=True)
class StockRef:
    id: int
    symbol: str
    name: str


@dataclass(frozen=True)
class WatchlistView:
    id: int
    name: str
    stocks: tuple[StockRef, ...]


def _coerce_id(value) -> int | None:
    """Ids arrive from the browser; anything that isn't a clean int is no id."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _normalize_symbol(symbol) -> str | None:
    if not isinstance(symbol, str):
        return None
    symbol = symbol.strip().upper()
    if not symbol or len(symbol) > 10 or not symbol.replace(".", "").isalnum():
        return None
    return symbol


class LiveSource:
    """The signed-in user's account, priced by the market-data provider."""

    mode = "app"
    is_sample = False
    read_only = False
    # Any ticker can be searched
    search_symbols: tuple[str, ...] | None = None

    # --- market data -----------------------------------------------------

    def quote_batch(self, symbols) -> QuoteBatch:
        return get_quote_batch(symbols)

    def history(self, symbol: str) -> list[dict]:
        """All available daily bars through the latest completed session.

        Capping at that session keeps the chart's last point on the same close
        the quote reports, instead of a partial bar for a session still open.
        """
        return get_stock_data(symbol, MAX_HISTORY_START_DATE, get_most_recent_trading_day())

    def intraday(self, symbol: str) -> list[dict]:
        return get_intraday_stock_data(symbol)

    def details(self, symbol: str) -> dict | None:
        return get_company_details(symbol)

    def logo_src(self, symbol: str, details: dict | None) -> str | None:
        # Branding goes through the server-side /branding/ proxy so the API
        # key never appears in a client-visible URL.
        if details and (details.get("icon_url") or details.get("logo_url")):
            return f"/branding/{symbol}/icon"
        return None

    # --- account ---------------------------------------------------------

    def _user_id(self) -> int | None:
        return current_user.id if current_user.is_authenticated else None

    def account_label(self) -> str | None:
        return current_user.username if current_user.is_authenticated else None

    def account_key(self) -> str | None:
        """Tags saved browser state with its owner, so a different user
        signing in on the same tab starts fresh."""
        return str(current_user.id) if current_user.is_authenticated else None

    def _owned(self, watchlist_id) -> Watchlist | None:
        """The current user's watchlist with this id, or None.

        Watchlist ids reach the handlers from the browser — the dropdown value,
        stored session state, and pattern-matching button indices are all
        client-controlled — so every lookup is scoped to the owner. An id
        belonging to another account is treated exactly like one that does
        not exist, so callers cannot use the difference to probe for other
        users' watchlists.
        """
        user_id = self._user_id()
        watchlist_id = _coerce_id(watchlist_id)
        if user_id is None or watchlist_id is None:
            return None
        return Watchlist.query.filter_by(id=watchlist_id, user_id=user_id).first()

    @staticmethod
    def _view(watchlist: Watchlist) -> WatchlistView:
        return WatchlistView(
            id=watchlist.id,
            name=watchlist.name,
            stocks=tuple(
                StockRef(id=s.id, symbol=s.symbol, name=s.name or "") for s in watchlist.stocks
            ),
        )

    def watchlists(self) -> list[WatchlistView]:
        """The user's watchlists, oldest first (the first is the default)."""
        user_id = self._user_id()
        if user_id is None:
            return []
        rows = Watchlist.query.filter_by(user_id=user_id).order_by(Watchlist.id).all()
        return [self._view(w) for w in rows]

    def watchlist(self, watchlist_id) -> WatchlistView | None:
        watchlist = self._owned(watchlist_id)
        return self._view(watchlist) if watchlist else None

    def create_watchlist(self, name) -> WatchlistView:
        user_id = self._user_id()
        if user_id is None:
            raise WatchlistError("Log in to create a watchlist.")
        name = (name or "").strip() if isinstance(name, str) else ""
        if not name:
            raise WatchlistError("Watchlist name cannot be empty.")
        if len(name) > WATCHLIST_NAME_MAX:
            raise WatchlistError(f"Keep the name under {WATCHLIST_NAME_MAX} characters.")
        watchlist = Watchlist(name=name, user_id=user_id)
        db.session.add(watchlist)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        return self._view(watchlist)

    def add_to_watchlist(self, watchlist_id, symbol) -> tuple[bool, WatchlistView]:
        """Add a ticker; returns (added, view). added is False if already there."""
        watchlist = self._owned(watchlist_id)
        if watchlist is None:
            raise WatchlistError("Watchlist not found.")
        symbol = _normalize_symbol(symbol)
        if symbol is None:
            raise WatchlistError("That isn't a valid ticker.")

        stock = Stock.query.filter_by(symbol=symbol).first()
        if stock is not None and stock in watchlist.stocks:
            return False, self._view(watchlist)
        try:
            if stock is None:
                details = get_company_details(symbol)
                name = details.get("name", symbol) if details else symbol
                stock = Stock(symbol=symbol, name=name)
                db.session.add(stock)
            watchlist.stocks.append(stock)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        return True, self._view(watchlist)

    def remove_from_watchlist(self, watchlist_id, stock_id) -> str | None:
        """Remove one membership; returns the removed symbol, or None."""
        watchlist = self._owned(watchlist_id)
        stock_id = _coerce_id(stock_id)
        if watchlist is None or stock_id is None:
            return None
        stock = next((s for s in watchlist.stocks if s.id == stock_id), None)
        if stock is None:
            return None
        watchlist.stocks.remove(stock)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        return stock.symbol

    def delete_watchlist(self, watchlist_id) -> str | None:
        """Delete the list (never its stocks); returns its name, or None."""
        watchlist = self._owned(watchlist_id)
        if watchlist is None:
            return None
        name = watchlist.name
        db.session.delete(watchlist)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        return name

    # --- portfolio -------------------------------------------------------

    def portfolio_summary(self) -> dict | None:
        user_id = self._user_id()
        if user_id is None:
            return None
        return portfolio_services.get_portfolio_summary(user_id)

    def transactions(self, limit: int = 25) -> list:
        user_id = self._user_id()
        if user_id is None:
            return []
        return portfolio_services.list_transactions(user_id, limit=limit)

    def transaction(self, transaction_id):
        user_id = self._user_id()
        transaction_id = _coerce_id(transaction_id)
        if user_id is None or transaction_id is None:
            return None
        return Transaction.query.filter_by(id=transaction_id, user_id=user_id).first()

    def record_transaction(self, symbol, side, quantity, price, executed_at: date):
        user_id = self._user_id()
        if user_id is None:
            raise portfolio_services.PortfolioError("Log in to record trades.")
        return portfolio_services.record_transaction(
            user_id, symbol, side, quantity, price, executed_at
        )

    def delete_transaction(self, transaction_id) -> bool:
        user_id = self._user_id()
        transaction_id = _coerce_id(transaction_id)
        if user_id is None or transaction_id is None:
            return False
        return portfolio_services.delete_transaction(user_id, transaction_id)


_SAMPLE_WATCHLIST = WatchlistView(
    id=sample_data.WATCHLIST_ID,
    name=sample_data.WATCHLIST_NAME,
    stocks=tuple(StockRef(id=s.id, symbol=s.symbol, name=s.name) for s in sample_data.STOCKS),
)


class SampleSource:
    """Fixed sample data for the public demo. Read-only by construction."""

    mode = "demo"
    is_sample = True
    read_only = True
    search_symbols: tuple[str, ...] | None = sample_data.SYMBOLS

    def quote_batch(self, symbols) -> QuoteBatch:
        return QuoteBatch(quotes=sample_data.quotes(symbols))

    def history(self, symbol: str) -> list[dict]:
        return sample_data.history(symbol)

    def intraday(self, symbol: str) -> list[dict]:
        return sample_data.intraday(symbol)

    def details(self, symbol: str) -> dict | None:
        return sample_data.details(symbol)

    def logo_src(self, symbol: str, details: dict | None) -> str | None:
        # The branding proxy calls the provider; the demo shows monograms
        return None

    def account_label(self) -> str | None:
        return None

    def account_key(self) -> str | None:
        return None

    def watchlists(self) -> list[WatchlistView]:
        return [_SAMPLE_WATCHLIST]

    def watchlist(self, watchlist_id) -> WatchlistView | None:
        return _SAMPLE_WATCHLIST if _coerce_id(watchlist_id) == _SAMPLE_WATCHLIST.id else None

    def portfolio_summary(self) -> dict:
        return portfolio_services.summarize_transactions(
            sample_data.TRANSACTIONS, quote_fn=sample_data.quotes
        )

    def transactions(self, limit: int = 25) -> list:
        ordered = sorted(
            sample_data.TRANSACTIONS, key=lambda t: (t.executed_at, t.id), reverse=True
        )
        return ordered[:limit]

    def transaction(self, transaction_id):
        transaction_id = _coerce_id(transaction_id)
        return next((t for t in sample_data.TRANSACTIONS if t.id == transaction_id), None)

    def _refuse(self, *_args, **_kwargs):
        raise ReadOnlyDemoError("The demo is read-only. Create an account to make changes.")

    create_watchlist = _refuse
    add_to_watchlist = _refuse
    remove_from_watchlist = _refuse
    delete_watchlist = _refuse
    record_transaction = _refuse
    delete_transaction = _refuse
