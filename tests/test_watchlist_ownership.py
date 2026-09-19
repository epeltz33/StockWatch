"""Watchlists are private to their owner.

The watchlist id reaching these handlers comes from the browser (the dropdown
value, or a pattern-matching button index), so it is attacker-controlled. Every
lookup must be scoped to the current user; otherwise a crafted id reads,
mutates, or deletes another account's watchlist.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.extensions import db
from app.models import Stock, User, Watchlist
from frontend import dashboard


@pytest.fixture
def users(app):
    owner = User(username="owner", email="owner@example.com")
    owner.set_password("password123")
    attacker = User(username="attacker", email="attacker@example.com")
    attacker.set_password("password123")
    db.session.add_all([owner, attacker])
    db.session.commit()
    return owner, attacker


@pytest.fixture
def victim_watchlist(users):
    owner, _ = users
    watchlist = Watchlist(name="Owner's picks", user_id=owner.id)
    stock = Stock(symbol="AAPL", name="Apple Inc.")
    db.session.add_all([watchlist, stock])
    db.session.commit()
    watchlist.stocks.append(stock)
    db.session.commit()
    return watchlist


def _as_user(user):
    """Stand in for the Flask-Login proxy without a request context."""
    return SimpleNamespace(
        id=user.id,
        is_authenticated=True,
        watchlists=SimpleNamespace(all=lambda: Watchlist.query.filter_by(user_id=user.id).all()),
    )


def _callback(dash_app):
    for key, entry in dash_app.callback_map.items():
        if "watchlist-section" in key:
            return entry["callback"].__wrapped__
    raise AssertionError("watchlist callback not registered")


@pytest.fixture
def dash_app(app):
    from flask import Flask

    with app.app_context():
        yield dashboard.create_dash_app(Flask(__name__))


def test_owned_watchlist_returns_the_users_own_watchlist(users, victim_watchlist):
    owner, _ = users
    with patch.object(dashboard, "current_user", _as_user(owner)):
        assert dashboard._owned_watchlist(victim_watchlist.id) is not None


def test_owned_watchlist_refuses_another_users_watchlist(users, victim_watchlist):
    _, attacker = users
    with patch.object(dashboard, "current_user", _as_user(attacker)):
        assert dashboard._owned_watchlist(victim_watchlist.id) is None


def test_owned_watchlist_handles_a_missing_id(users):
    owner, _ = users
    with patch.object(dashboard, "current_user", _as_user(owner)):
        assert dashboard._owned_watchlist(999999) is None
        assert dashboard._owned_watchlist(None) is None


def test_rendering_refuses_to_show_another_users_watchlist(users, victim_watchlist):
    _, attacker = users
    # The attacker needs a watchlist of their own: with none, the renderer
    # short-circuits to the empty state and the lookup is never reached.
    db.session.add(Watchlist(name="Attacker's own", user_id=attacker.id))
    db.session.commit()

    with patch.object(dashboard, "current_user", _as_user(attacker)):
        rendered = dashboard.update_watchlist_section(victim_watchlist.id)

    assert "AAPL" not in str(rendered)


def test_adding_a_stock_to_another_users_watchlist_is_refused(dash_app, users, victim_watchlist):
    _, attacker = users
    raw = _callback(dash_app)
    ctx = SimpleNamespace(
        triggered_id={"type": "add-to-watchlist", "index": "MSFT"},
        triggered=[{"prop_id": "x.n_clicks", "value": 1}],
    )
    add_ids = [{"type": "add-to-watchlist", "index": "MSFT"}]

    with patch.object(dashboard, "callback_context", ctx):
        with patch.object(dashboard, "current_user", _as_user(attacker)):
            with patch.object(dashboard, "update_watchlist_section", Mock()):
                raw(None, [1], [], [], victim_watchlist.id, 0, None, add_ids)

    symbols = {s.symbol for s in db.session.get(Watchlist, victim_watchlist.id).stocks}
    assert symbols == {"AAPL"}


def test_removing_a_stock_from_another_users_watchlist_is_refused(
    dash_app, users, victim_watchlist
):
    _, attacker = users
    stock_id = victim_watchlist.stocks[0].id
    raw = _callback(dash_app)
    ctx = SimpleNamespace(
        triggered_id={"type": "remove-from-watchlist", "index": stock_id},
        triggered=[{"prop_id": "x.n_clicks", "value": 1}],
    )

    with patch.object(dashboard, "callback_context", ctx):
        with patch.object(dashboard, "current_user", _as_user(attacker)):
            with patch.object(dashboard, "update_watchlist_section", Mock()):
                raw(None, [], [1], [], victim_watchlist.id, 0, None, [])

    symbols = {s.symbol for s in db.session.get(Watchlist, victim_watchlist.id).stocks}
    assert symbols == {"AAPL"}


def test_deleting_another_users_watchlist_is_refused(dash_app, users, victim_watchlist):
    _, attacker = users
    raw = _callback(dash_app)
    ctx = SimpleNamespace(
        triggered_id={"type": "delete-watchlist", "index": victim_watchlist.id},
        triggered=[{"prop_id": "x.n_clicks", "value": 1}],
    )

    with patch.object(dashboard, "callback_context", ctx):
        with patch.object(dashboard, "current_user", _as_user(attacker)):
            with patch.object(dashboard, "update_watchlist_section", Mock()):
                raw(None, [], [], [1], None, 0, None, [])

    assert db.session.get(Watchlist, victim_watchlist.id) is not None
