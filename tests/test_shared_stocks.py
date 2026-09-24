"""Stock rows are shared: watchlist edits must never delete them.

Watchlist.stocks used to cascade "all, delete-orphan" over a many-to-many
link, so removing a ticker from one list — or deleting the list — deleted the
Stock row itself. That silently emptied the same ticker out of every other
user's watchlist (watchlist_stocks cascades on stock delete) and orphaned or
blocked portfolio transactions that reference the stock.
"""

from datetime import date

import pytest
from sqlalchemy import event

from app.extensions import db
from app.models import Stock, Transaction, User, Watchlist, watchlist_stocks


@pytest.fixture
def enforce_foreign_keys(app):
    """SQLite ignores foreign keys unless asked; production PostgreSQL doesn't."""

    def on_connect(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    engine = db.engine
    event.listen(engine, "connect", on_connect)
    engine.dispose()
    db.create_all()
    yield
    event.remove(engine, "connect", on_connect)


@pytest.fixture
def two_users(app, enforce_foreign_keys):
    alice = User(username="alice", email="alice@example.com")
    bob = User(username="bob", email="bob@example.com")
    for user in (alice, bob):
        user.set_password("password123")
    db.session.add_all([alice, bob])
    db.session.commit()
    return alice, bob


@pytest.fixture
def shared(two_users):
    """Alice and Bob both watch AAPL; Alice also holds it in her portfolio."""
    alice, bob = two_users
    aapl = Stock(symbol="AAPL", name="Apple Inc.")
    msft = Stock(symbol="MSFT", name="Microsoft Corporation")
    alice_list = Watchlist(name="Alice's list", user_id=alice.id)
    bob_list = Watchlist(name="Bob's list", user_id=bob.id)
    db.session.add_all([aapl, msft, alice_list, bob_list])
    db.session.flush()
    alice_list.stocks.extend([aapl, msft])
    bob_list.stocks.append(aapl)
    db.session.add(
        Transaction(
            user_id=alice.id,
            stock_id=aapl.id,
            side="BUY",
            quantity=10,
            price=150,
            executed_at=date(2024, 1, 5),
        )
    )
    db.session.commit()
    return {"aapl": aapl, "alice_list": alice_list, "bob_list": bob_list}


def _symbols(watchlist_id):
    return {s.symbol for s in db.session.get(Watchlist, watchlist_id).stocks}


def test_the_same_stock_can_be_on_several_watchlists(shared):
    assert _symbols(shared["alice_list"].id) == {"AAPL", "MSFT"}
    assert _symbols(shared["bob_list"].id) == {"AAPL"}


def test_removing_a_ticker_from_one_watchlist_keeps_the_stock(shared):
    alice_list, aapl = shared["alice_list"], shared["aapl"]

    alice_list.stocks.remove(aapl)
    db.session.commit()

    assert Stock.query.filter_by(symbol="AAPL").count() == 1
    assert _symbols(alice_list.id) == {"MSFT"}
    # Bob's list and Alice's portfolio still see the same stock row
    assert _symbols(shared["bob_list"].id) == {"AAPL"}
    assert Transaction.query.one().stock.symbol == "AAPL"


def test_deleting_a_watchlist_keeps_its_stocks_and_other_references(shared):
    alice_list = shared["alice_list"]
    alice_list_id = alice_list.id

    db.session.delete(alice_list)
    db.session.commit()

    assert db.session.get(Watchlist, alice_list_id) is None
    assert {s.symbol for s in Stock.query.all()} == {"AAPL", "MSFT"}
    assert _symbols(shared["bob_list"].id) == {"AAPL"}
    assert Transaction.query.one().stock.symbol == "AAPL"
    # Only the deleted list's membership rows are gone
    remaining = db.session.execute(db.select(watchlist_stocks.c.watchlist_id)).scalars().all()
    assert set(remaining) == {shared["bob_list"].id}
