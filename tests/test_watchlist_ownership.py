"""Watchlists and trades are private to their owner.

Ids reaching the server come from the browser — the dropdown value, ids saved
in sessionStorage, pattern-matching button indices, the pending-delete store —
so they are attacker-controlled. Every lookup is scoped to the signed-in user;
an id belonging to another account behaves exactly like one that doesn't exist.
Callbacks are driven over HTTP as a signed-in attacker.
"""

import json
from datetime import date

import pytest

from app.extensions import db
from app.models import Stock, Transaction, User, Watchlist
from frontend.data_sources import LiveSource
from tests.dash_client import DashClient, response_props


def make_user(name):
    user = User(username=name, email=f"{name}@example.com")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def owner(app):
    return make_user("owner")


@pytest.fixture
def victim_watchlist(owner):
    watchlist = Watchlist(name="Owner's picks", user_id=owner.id)
    stock = Stock(symbol="AAPL", name="Apple Inc.")
    db.session.add_all([watchlist, stock])
    db.session.commit()
    watchlist.stocks.append(stock)
    db.session.commit()
    return watchlist


@pytest.fixture
def victim_trade(owner, victim_watchlist):
    trade = Transaction(
        user_id=owner.id,
        stock_id=victim_watchlist.stocks[0].id,
        side="BUY",
        quantity=5,
        price=100,
        executed_at=date(2024, 1, 5),
    )
    db.session.add(trade)
    db.session.commit()
    return trade


@pytest.fixture
def attacker(app, client):
    user = make_user("attacker")
    own = Watchlist(name="Attacker's own", user_id=user.id)
    db.session.add(own)
    db.session.commit()
    client.post("/auth/login", data={"email": user.email, "password": "password123"})
    return user, own


@pytest.fixture
def dash(app, client):
    return DashClient(client, app.extensions["dash_apps"]["app"])


def symbols(watchlist_id):
    return {s.symbol for s in db.session.get(Watchlist, watchlist_id).stocks}


# --- the source ------------------------------------------------------------------


def test_source_returns_the_users_own_watchlist(app, owner, victim_watchlist):
    with app.test_request_context():
        from flask_login import login_user

        login_user(owner)
        view = LiveSource().watchlist(victim_watchlist.id)
    assert view is not None and [s.symbol for s in view.stocks] == ["AAPL"]


@pytest.mark.parametrize("bad_id", [None, 999999, "abc", True, {"id": 1}, "1; DROP TABLE"])
def test_source_treats_foreign_missing_and_malformed_ids_alike(app, victim_watchlist, bad_id):
    attacker = make_user("prober")
    with app.test_request_context():
        from flask_login import login_user

        login_user(attacker)
        source = LiveSource()
        assert source.watchlist(victim_watchlist.id) is None
        assert source.watchlist(bad_id) is None


# --- over HTTP, as a signed-in attacker -------------------------------------------


def test_rendering_refuses_to_show_another_users_watchlist(dash, attacker, victim_watchlist):
    response = dash.call(
        "render_watchlist",
        values={
            "watchlist-dropdown.value": victim_watchlist.id,
            "watchlist-version.data": 1,
            "stock-symbol-store.data": None,
        },
        triggered=["watchlist-dropdown.value"],
    )

    text = response.get_data(as_text=True)
    assert "AAPL" not in text
    assert "Owner's picks" not in text


def test_restore_validates_the_stored_watchlist_belongs_to_the_user(
    dash, attacker, victim_watchlist
):
    """A watchlist id saved in sessionStorage is client-controlled: restoring
    one that isn't the user's falls back to their own first watchlist."""
    _, own = attacker
    props = response_props(
        dash.call(
            "restore_watchlists",
            values={
                "restore-request.data": {"watchlist_id": victim_watchlist.id},
                "watchlist-version.data": 0,
            },
            triggered=["restore-request.data"],
        )
    )

    assert props["watchlist-dropdown"]["value"] == own.id
    assert props["watchlist-dropdown"]["options"] == [{"label": own.name, "value": own.id}]


def test_restore_keeps_a_stored_watchlist_the_user_owns(dash, attacker):
    user, own = attacker
    second = Watchlist(name="Second", user_id=user.id)
    db.session.add(second)
    db.session.commit()

    props = response_props(
        dash.call(
            "restore_watchlists",
            values={"restore-request.data": {"watchlist_id": second.id}},
            triggered=["restore-request.data"],
        )
    )

    assert props["watchlist-dropdown"]["value"] == second.id


def test_adding_a_stock_to_another_users_watchlist_is_refused(dash, attacker, victim_watchlist):
    response = dash.call(
        "add_to_watchlist",
        values={
            "add-to-watchlist.n_clicks": 1,
            "stock-symbol-store.data": "MSFT",
            "watchlist-dropdown.value": victim_watchlist.id,
            "watchlist-version.data": 1,
        },
        triggered=["add-to-watchlist.n_clicks"],
    )

    assert "Watchlist not found" in response.get_data(as_text=True)
    assert symbols(victim_watchlist.id) == {"AAPL"}


def test_removing_a_stock_from_another_users_watchlist_is_refused(dash, attacker, victim_watchlist):
    stock_id = victim_watchlist.stocks[0].id
    dash.call(
        "remove_from_watchlist",
        values={
            "remove-request.data": {"type": "remove-from-watchlist", "index": stock_id},
            "watchlist-dropdown.value": victim_watchlist.id,
            "watchlist-version.data": 1,
        },
        triggered=["remove-request.data"],
    )

    assert symbols(victim_watchlist.id) == {"AAPL"}


def test_confirming_another_users_watchlist_delete_is_refused(dash, attacker, victim_watchlist):
    prompt = dash.call(
        "ask_to_confirm",
        values={"delete-request.data": {"type": "delete-watchlist", "index": victim_watchlist.id}},
        triggered=["delete-request.data"],
    )
    assert prompt.status_code == 204  # no dialog for a list you don't own

    # Skip the dialog and send the confirmation directly
    dash.call(
        "confirm_delete",
        values={
            "confirm-accept.n_clicks": 1,
            "pending-action.data": {"kind": "watchlist", "id": victim_watchlist.id},
        },
        triggered=["confirm-accept.n_clicks"],
    )

    assert db.session.get(Watchlist, victim_watchlist.id) is not None


def test_deleting_another_users_transaction_is_refused(dash, attacker, victim_trade):
    prompt = dash.call(
        "ask_to_confirm",
        values={"delete-request.data": {"type": "delete-transaction", "index": victim_trade.id}},
        triggered=["delete-request.data"],
    )
    assert prompt.status_code == 204

    response = dash.call(
        "confirm_delete",
        values={
            "confirm-accept.n_clicks": 1,
            "pending-action.data": {"kind": "transaction", "id": victim_trade.id},
        },
        triggered=["confirm-accept.n_clicks"],
    )

    assert "Transaction not found" in json.dumps(response_props(response))
    assert db.session.get(Transaction, victim_trade.id) is not None


def test_the_owner_can_delete_after_confirming(app, client, owner, victim_watchlist):
    client.post("/auth/login", data={"email": owner.email, "password": "password123"})
    dash = DashClient(client, app.extensions["dash_apps"]["app"])

    prompt = response_props(
        dash.call(
            "ask_to_confirm",
            values={
                "delete-request.data": {"type": "delete-watchlist", "index": victim_watchlist.id}
            },
            triggered=["delete-request.data"],
        )
    )
    assert prompt["confirm-modal"]["is_open"] is True
    assert "Owner's picks" in json.dumps(prompt["confirm-title"])
    # Nothing is deleted until the dialog is confirmed
    assert db.session.get(Watchlist, victim_watchlist.id) is not None

    dash.call(
        "confirm_delete",
        values={
            "confirm-accept.n_clicks": 1,
            "pending-action.data": prompt["pending-action"]["data"],
        },
        triggered=["confirm-accept.n_clicks"],
    )

    assert db.session.get(Watchlist, victim_watchlist.id) is None
    # The list is gone; the shared stock row is not
    assert Stock.query.filter_by(symbol="AAPL").count() == 1
