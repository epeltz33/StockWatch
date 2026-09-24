"""Provider requests an interaction costs on the signed-in dashboard.

Driven over HTTP against tests/fake_market's FakePolygonClient, which counts
calls. Once a view is loaded, period switches, re-selecting a ticker,
repricing the watchlist and portfolio, and a page reload all come from the
caches; only data not yet fetched (the intraday session) costs a request.
"""

from collections import Counter

import pytest

from app.extensions import db
from app.models import Stock, User, Watchlist
from app.services import stock_services
from tests.dash_client import DashClient, changed, response_props
from tests.fake_market import FakePolygonClient

PERIODS = ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "10Y", "MAX"]


@pytest.fixture
def fake(monkeypatch):
    client = FakePolygonClient()
    monkeypatch.setattr(stock_services, "polygon_client", client)
    return client


@pytest.fixture
def dash(app, client, fake):
    user = User(username="counter", email="counter@example.com")
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()
    watchlist = Watchlist(name="Core", user_id=user.id)
    stocks = [Stock(symbol=s, name=s) for s in ("AAPL", "MSFT", "NVDA")]
    db.session.add_all([watchlist, *stocks])
    db.session.flush()
    watchlist.stocks.extend(stocks)
    db.session.commit()
    client.post("/auth/login", data={"email": user.email, "password": "password123"})
    dash = DashClient(client, app.extensions["dash_apps"]["app"])
    dash.watchlist_id = watchlist.id
    return dash


def delta(fake, before):
    return {k: v for k, v in (fake.calls - before).items() if v}


def load(dash, symbol):
    return dash.call(
        "load_stock",
        values={"symbol-request.data": {"symbol": symbol, "origin": "click", "at": 1}},
        triggered=["symbol-request.data"],
    )


def pick_period(dash, symbol, period):
    buttons = [{"type": "period-btn", "index": p} for p in PERIODS]
    return dash.call(
        "update_chart_period",
        values={
            "period-btn.n_clicks": [int(b["index"] == period) for b in buttons],
            "period-btn.id": buttons,
            "stock-symbol-store.data": symbol,
        },
        components={"period-btn": buttons},
        triggered=[changed({"type": "period-btn", "index": period}, "n_clicks")],
    )


def render_watchlist(dash):
    return dash.call(
        "render_watchlist",
        values={"watchlist-dropdown.value": dash.watchlist_id, "watchlist-version.data": 1},
        triggered=["watchlist-dropdown.value"],
    )


def test_first_view_costs_one_request_per_kind_of_data(dash, fake):
    load(dash, "AAPL")
    render_watchlist(dash)

    # History, company details, and two whole-market sessions (latest and
    # prior close) — the watchlist reuses the sessions the chart fetched.
    assert dict(fake.calls) == {"aggs_day": 1, "details": 1, "grouped": 2}


def test_switching_daily_periods_makes_no_provider_requests(dash, fake):
    load(dash, "AAPL")
    before = Counter(fake.calls)

    for period in ("5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"):
        assert pick_period(dash, "AAPL", period).status_code == 200

    assert delta(fake, before) == {}


def test_the_intraday_session_is_fetched_once(dash, fake):
    load(dash, "AAPL")
    before = Counter(fake.calls)

    pick_period(dash, "AAPL", "1D")
    first = delta(fake, before)
    pick_period(dash, "AAPL", "1Y")
    pick_period(dash, "AAPL", "1D")

    assert sum(first.values()) >= 1
    assert delta(fake, before) == first


def test_reselecting_a_ticker_and_repricing_are_served_from_cache(dash, fake):
    load(dash, "AAPL")
    render_watchlist(dash)
    load(dash, "MSFT")
    before = Counter(fake.calls)

    load(dash, "AAPL")
    render_watchlist(dash)
    refresh = dash.call(
        "refresh_prices",
        values={
            "refresh-watchlist.n_clicks": 1,
            "watchlist-quote.id": [
                {"type": "watchlist-quote", "index": s} for s in ("AAPL", "MSFT", "NVDA")
            ],
            "stock-meta.data": {"symbol": "AAPL", "last_bar": None, "prev_bar": None},
        },
        components={
            "watchlist-quote": [
                {"type": "watchlist-quote", "index": s} for s in ("AAPL", "MSFT", "NVDA")
            ]
        },
        triggered=["refresh-watchlist.n_clicks"],
    )
    portfolio = dash.call(
        "render_portfolio",
        values={"portfolio-refresh.data": 0, "active-tab.data": "portfolio"},
        triggered=["active-tab.data"],
    )

    assert refresh.status_code == 200 and portfolio.status_code == 200
    assert delta(fake, before) == {}


def test_a_reload_restores_from_cache(dash, fake):
    restore = {"symbol": "MSFT", "period": "5Y", "watchlist_id": dash.watchlist_id}
    for _ in range(2):
        before = Counter(fake.calls)
        dash.call(
            "restore_watchlists",
            values={"restore-request.data": restore, "watchlist-version.data": 0},
            triggered=["restore-request.data"],
        )
        props = response_props(
            dash.call(
                "load_stock",
                values={"restore-request.data": restore},
                triggered=["restore-request.data"],
            )
        )
        render_watchlist(dash)
    assert props["chart-period-store"]["data"] == "5Y"
    assert delta(fake, before) == {}  # the second page load cost nothing
