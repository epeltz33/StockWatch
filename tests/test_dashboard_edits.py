"""Edits on the signed-in dashboard, driven over HTTP as the browser would.

Covers the happy paths and the mistakes a user can make: empty or overlong
names, duplicates, trades that would oversell, and future-dated trades.
"""

import json
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import Stock, Transaction, User, Watchlist
from app.services import stock_services
from tests.dash_client import DashClient, response_props
from tests.fake_market import FakePolygonClient


@pytest.fixture
def user(app, client, monkeypatch):
    monkeypatch.setattr(stock_services, "polygon_client", FakePolygonClient())
    user = User(username="editor", email="editor@example.com")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": user.email, "password": "password123"})
    return user


@pytest.fixture
def dash(app, client, user):
    return DashClient(client, app.extensions["dash_apps"]["app"])


def toast(response):
    return (response_props(response).get("toast-trigger") or {}).get("data") or {}


def create(dash, name):
    return dash.call(
        "create_watchlist",
        values={
            "create-watchlist-button.n_clicks": 1,
            "new-watchlist-input.value": name,
            "watchlist-version.data": 3,
        },
        triggered=["create-watchlist-button.n_clicks"],
    )


def add(dash, watchlist_id, symbol):
    return dash.call(
        "add_to_watchlist",
        values={
            "add-to-watchlist.n_clicks": 1,
            "stock-symbol-store.data": symbol,
            "watchlist-dropdown.value": watchlist_id,
            "watchlist-version.data": 1,
        },
        triggered=["add-to-watchlist.n_clicks"],
    )


def trade(dash, side="BUY", symbol="AAPL", quantity=10, price=150, when="2024-01-05"):
    return dash.call(
        "add_transaction",
        values={
            "txn-submit.n_clicks": 1,
            "txn-side.value": side,
            "txn-symbol.value": symbol,
            "txn-quantity.value": quantity,
            "txn-price.value": price,
            "txn-date.value": when,
            "portfolio-refresh.data": 0,
        },
        triggered=["txn-submit.n_clicks"],
    )


def test_creating_a_watchlist_selects_it_and_closes_the_form(dash, user):
    props = response_props(create(dash, "  Tech leaders  "))

    created = Watchlist.query.filter_by(user_id=user.id).one()
    assert created.name == "Tech leaders"
    assert props["watchlist-dropdown"]["value"] == created.id
    assert props["watchlist-dropdown"]["options"] == [
        {"label": "Tech leaders", "value": created.id}
    ]
    assert props["new-watchlist-collapse"]["is_open"] is False
    assert props["new-watchlist-input"]["value"] == ""


@pytest.mark.parametrize(
    ("name", "message"),
    [("   ", "cannot be empty"), ("x" * 65, "under 64 characters")],
)
def test_bad_watchlist_names_are_explained_and_nothing_is_created(dash, name, message):
    response = create(dash, name)

    assert message in toast(response)["message"]
    assert "watchlist-dropdown" not in response_props(response)
    assert Watchlist.query.count() == 0


def test_adding_a_new_ticker_creates_the_stock_with_its_company_name(dash, user):
    watchlist = Watchlist(name="Core", user_id=user.id)
    db.session.add(watchlist)
    db.session.commit()

    first = toast(add(dash, watchlist.id, "MSFT"))
    again = toast(add(dash, watchlist.id, "MSFT"))

    assert first["type"] == "success" and "Added MSFT" in first["message"]
    assert again["type"] == "info" and "already in" in again["message"]
    assert Stock.query.filter_by(symbol="MSFT").one().name == "Microsoft Corporation"
    assert [s.symbol for s in db.session.get(Watchlist, watchlist.id).stocks] == ["MSFT"]


def test_adding_without_a_watchlist_asks_for_one(dash):
    message = toast(add(dash, None, "AAPL"))
    assert message["type"] == "warning" and "watchlist first" in message["message"]


def test_removing_a_ticker_keeps_the_stock_for_others(dash, user):
    watchlist = Watchlist(name="Core", user_id=user.id)
    stock = Stock(symbol="AAPL", name="Apple Inc.")
    db.session.add_all([watchlist, stock])
    db.session.commit()
    watchlist.stocks.append(stock)
    db.session.commit()

    response = dash.call(
        "remove_from_watchlist",
        values={
            "remove-request.data": {"type": "remove-from-watchlist", "index": stock.id},
            "watchlist-dropdown.value": watchlist.id,
            "watchlist-version.data": 4,
        },
        triggered=["remove-request.data"],
    )

    assert response_props(response)["watchlist-version"]["data"] == 5
    assert "Removed AAPL" in toast(response)["message"]
    assert db.session.get(Watchlist, watchlist.id).stocks == []
    assert Stock.query.filter_by(symbol="AAPL").count() == 1


def test_recording_a_trade_updates_the_portfolio_and_clears_the_form(dash, user):
    props = response_props(trade(dash))

    assert props["portfolio-refresh"]["data"] == 1
    assert props["txn-symbol"]["value"] == ""
    assert "Recorded BUY 10 AAPL" in props["toast-trigger"]["data"]["message"]
    assert Transaction.query.filter_by(user_id=user.id).count() == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"side": "SELL"}, "Cannot sell 10 AAPL"),
        ({"quantity": None}, "Fill in ticker, quantity, price, and date"),
        ({"when": (date.today() + timedelta(days=3)).isoformat()}, "can't be in the future"),
        ({"when": "not-a-date"}, "YYYY-MM-DD"),
        ({"symbol": "BAD SYMBOL"}, "Invalid symbol"),
    ],
)
def test_bad_trades_are_explained_and_not_recorded(dash, kwargs, message):
    response = trade(dash, **kwargs)

    assert message in toast(response)["message"]
    assert Transaction.query.count() == 0


def test_deleting_a_trade_the_ledger_depends_on_is_refused_with_a_reason(dash, user):
    trade(dash, "BUY", "AAPL", 10, 150, "2024-01-05")
    trade(dash, "SELL", "AAPL", 4, 190, "2024-06-05")
    buy = Transaction.query.filter_by(side="BUY").one()

    response = dash.call(
        "confirm_delete",
        values={
            "confirm-accept.n_clicks": 1,
            "pending-action.data": {"kind": "transaction", "id": buy.id},
            "portfolio-refresh.data": 2,
        },
        triggered=["confirm-accept.n_clicks"],
    )

    message = json.dumps(toast(response))
    assert "Can't delete this trade" in message and "sale of 4 AAPL" in message
    assert Transaction.query.count() == 2
    # The dialog closes either way
    assert response_props(response)["confirm-modal"]["is_open"] is False
