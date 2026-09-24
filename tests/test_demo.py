"""The public demo at /demo/ is isolated from the provider, the database, and
every account, and refuses changes on the server — not just in the UI.

Callbacks are driven over HTTP (tests/dash_client.py), the same path a
hand-crafted request would take.
"""

import json

import pytest
from sqlalchemy import event

from app.extensions import db
from app.models import Stock, Transaction, User, Watchlist
from app.services import sample_data, stock_services
from tests.dash_client import DashClient, changed, response_props

SAMPLE = ["AAPL", "MSFT", "NVDA"]


def period_button(period):
    return {"type": "period-btn", "index": period}


def row(symbol):
    return {"type": "load-watchlist-stock", "index": symbol}


@pytest.fixture
def demo(app, client):
    return DashClient(client, app.extensions["dash_apps"]["demo"])


@pytest.fixture
def live(app, client):
    return DashClient(client, app.extensions["dash_apps"]["app"])


@pytest.fixture
def provider_calls(monkeypatch):
    """Records any market-data provider access. stock_services swallows
    provider exceptions, so raising alone could go unnoticed — the test
    asserts on this record instead."""
    calls = []

    def forbidden(*args, **_kwargs):
        calls.append(args)
        raise AssertionError("the demo called the market-data provider")

    monkeypatch.setattr(stock_services, "_get_client", forbidden)
    monkeypatch.setattr("app.blueprints.main.requests.get", forbidden)
    return calls


@pytest.fixture
def no_db_writes(app):
    """Any flush to the database fails the test."""
    flushes = []

    def record(session, *_args):
        flushes.append(list(session.new) + list(session.dirty) + list(session.deleted))

    event.listen(db.session, "before_flush", record)
    yield flushes
    event.remove(db.session, "before_flush", record)


@pytest.fixture
def alice(app, client):
    """A signed-in user with private watchlists and trades."""
    user = User(username="alice-private", email="alice@example.com")
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()
    stock = Stock(symbol="TSLA", name="Tesla, Inc.")
    watchlist = Watchlist(name="Secret list", user_id=user.id)
    db.session.add_all([stock, watchlist])
    db.session.flush()
    watchlist.stocks.append(stock)
    db.session.add(
        Transaction(
            user_id=user.id,
            stock_id=stock.id,
            side="BUY",
            quantity=3,
            price=99,
            executed_at=sample_data.AS_OF,
        )
    )
    db.session.commit()
    response = client.post(
        "/auth/login", data={"email": "alice@example.com", "password": "password123"}
    )
    assert response.status_code == 302
    return user, watchlist


def load(demo, symbol=None, restore=None):
    """Drive the demo's stock loader: a restore (page load) or a ticker click."""
    if symbol is None:
        return demo.call(
            "load_stock",
            values={"restore-request.data": restore or {}},
            triggered=["restore-request.data"],
        )
    return demo.call(
        "load_stock",
        values={"symbol-request.data": {"symbol": symbol, "origin": "click", "at": 1}},
        triggered=["symbol-request.data"],
    )


def pick_period(demo, symbol, period):
    buttons = [period_button(p) for p in ("1D", "5D", "1M", "1Y", "5Y", "MAX")]
    clicks = [1 if b["index"] == period else 0 for b in buttons]
    return demo.call(
        "update_chart_period",
        values={
            "period-btn.n_clicks": clicks,
            "period-btn.id": buttons,
            "stock-symbol-store.data": symbol,
        },
        components={"period-btn": buttons},
        triggered=[changed(period_button(period), "n_clicks")],
    )


def render_watchlist(demo, watchlist_id, active="AAPL"):
    return demo.call(
        "render_watchlist",
        values={
            "watchlist-dropdown.value": watchlist_id,
            "watchlist-version.data": 1,
            "stock-symbol-store.data": active,
        },
        triggered=["watchlist-dropdown.value"],
    )


def render_portfolio(demo):
    return demo.call(
        "render_portfolio",
        values={"portfolio-refresh.data": 0, "active-tab.data": "market"},
        triggered=[],
    )


# --- mounting and layout -------------------------------------------------------


def test_demo_is_public_while_the_dashboard_requires_login(client):
    assert client.get("/demo/").status_code == 200
    assert client.get("/demo/_dash-layout").status_code == 200
    assert client.get("/dash/").status_code == 302


def test_demo_layout_labels_sample_data_and_omits_editing_controls(client):
    layout = json.dumps(client.get("/demo/_dash-layout").get_json(), ensure_ascii=False)

    assert "Sample data · Not live prices" in layout
    for editing_id in (
        "add-to-watchlist",
        "new-watchlist-toggle",
        "create-watchlist-button",
        "confirm-modal",
        "txn-submit",
        "refresh-watchlist",
    ):
        assert f'"{editing_id}"' not in layout, editing_id


def test_demo_polling_is_disabled(app, client):
    layout = client.get("/demo/_dash-layout").get_json()
    intervals = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "Interval":
                intervals.append(node["props"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(layout)
    assert intervals and all(props["disabled"] is True for props in intervals)
    assert not DashClient(client, app.extensions["dash_apps"]["demo"]).has("refresh_prices")


def test_demo_registers_no_callback_that_can_change_anything(demo, live):
    mutating = [
        "create_watchlist",
        "add_to_watchlist",
        "remove_from_watchlist",
        "ask_to_confirm",
        "confirm_delete",
        "add_transaction",
    ]
    for name in mutating:
        assert live.has(name), name
        assert not demo.has(name), name


# --- blocked mutations ----------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["create_watchlist", "add_to_watchlist", "confirm_delete", "add_transaction"]
)
def test_crafted_mutation_requests_to_the_demo_are_rejected(demo, live, name, no_db_writes):
    """Replay the signed-in app's own mutation request against /demo/."""
    body = live.body(
        name,
        values={
            "create-watchlist-button.n_clicks": 1,
            "new-watchlist-input.value": "Injected",
            "add-to-watchlist.n_clicks": 1,
            "stock-symbol-store.data": "AAPL",
            "watchlist-dropdown.value": 1,
            "confirm-accept.n_clicks": 1,
            "pending-action.data": {"kind": "watchlist", "id": 1},
            "txn-submit.n_clicks": 1,
            "txn-symbol.value": "AAPL",
            "txn-side.value": "BUY",
            "txn-quantity.value": 1,
            "txn-price.value": 1,
            "txn-date.value": "2026-01-02",
        },
        triggered=["create-watchlist-button.n_clicks"],
    )

    response = demo.post(body)

    assert response.status_code == 403
    assert response.get_json() == {"error": "The demo is read-only."}
    assert no_db_writes == []
    assert Watchlist.query.count() == 0
    assert Transaction.query.count() == 0


def test_malformed_demo_callback_requests_are_rejected(demo):
    assert demo.post({"output": "nope.children"}).status_code == 403
    response = demo.client.post(demo.url, data="not json", content_type="application/json")
    assert response.status_code == 403


def test_sample_source_refuses_every_mutation():
    from frontend.data_sources import ReadOnlyDemoError, SampleSource

    source = SampleSource()
    for attempt in (
        lambda: source.create_watchlist("x"),
        lambda: source.add_to_watchlist(1, "AAPL"),
        lambda: source.remove_from_watchlist(1, 1),
        lambda: source.delete_watchlist(1),
        lambda: source.record_transaction("AAPL", "BUY", "1", "1", sample_data.AS_OF),
        lambda: source.delete_transaction(1),
    ):
        with pytest.raises(ReadOnlyDemoError):
            attempt()


# --- isolation: provider, database, accounts --------------------------------------


def test_exploring_the_demo_never_calls_the_provider_or_writes(demo, provider_calls, no_db_writes):
    responses = [
        demo.call(
            "restore_watchlists",
            values={"restore-request.data": {}, "watchlist-version.data": 0},
            triggered=["restore-request.data"],
        ),
        load(demo),
        render_watchlist(demo, sample_data.WATCHLIST_ID),
        load(demo, "MSFT"),
        pick_period(demo, "MSFT", "5Y"),
        pick_period(demo, "MSFT", "1D"),
        pick_period(demo, "MSFT", "MAX"),
        load(demo, "NVDA"),
        render_portfolio(demo),
    ]

    assert [r.status_code for r in responses] == [200] * len(responses)
    assert provider_calls == []
    assert no_db_writes == []


def test_demo_works_with_provider_access_disabled(demo, monkeypatch):
    """No API key and no client at all: the demo doesn't notice."""
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.setattr(stock_services, "polygon_client", None)

    props = response_props(load(demo))

    assert props["stock-symbol-store"]["data"] == "AAPL"
    assert "$231.48" in json.dumps(props["stock-quote-price"])


def test_signed_in_visitors_see_only_sample_data_in_the_demo(demo, client, alice):
    user, secret = alice

    layout = client.get("/demo/_dash-layout").get_data(as_text=True)
    restored = demo.call(
        "restore_watchlists",
        values={"restore-request.data": {"watchlist_id": secret.id}, "watchlist-version.data": 0},
        triggered=["restore-request.data"],
    )
    rendered = render_watchlist(demo, secret.id)
    portfolio = render_portfolio(demo)

    for response_text in (
        layout,
        restored.get_data(as_text=True),
        rendered.get_data(as_text=True),
        portfolio.get_data(as_text=True),
    ):
        assert "Secret list" not in response_text
        assert "alice-private" not in response_text
        assert "TSLA" not in response_text
    options = response_props(restored)["watchlist-dropdown"]["options"]
    assert options == [{"label": sample_data.WATCHLIST_NAME, "value": sample_data.WATCHLIST_ID}]


# --- what the demo shows ----------------------------------------------------------


def test_demo_opens_on_aapl_with_the_sample_watchlist(demo):
    restored = response_props(
        demo.call(
            "restore_watchlists",
            values={"restore-request.data": {}, "watchlist-version.data": 0},
            triggered=["restore-request.data"],
        )
    )
    stock = response_props(load(demo))

    assert restored["watchlist-dropdown"]["value"] == sample_data.WATCHLIST_ID
    assert stock["stock-symbol-store"]["data"] == "AAPL"
    assert stock["chart-card"]["className"] == "sw-card chart-card"
    assert stock["stock-chart"]["figure"]["data"], "chart has no traces"


def test_demo_search_is_limited_to_the_sample_tickers(demo):
    props = response_props(
        demo.call(
            "load_stock",
            values={"search-button.n_clicks": 1, "stock-input.value": "tsla"},
            triggered=["search-button.n_clicks"],
        )
    )

    message = json.dumps(props["search-status"])
    assert "TSLA isn't in the sample data" in message
    assert all(symbol in message for symbol in SAMPLE)
    # The chart and everything labelled with its symbol stay as they were
    assert "stock-chart" not in props
    assert "stock-symbol-store" not in props


def test_demo_portfolio_is_ready_before_the_section_is_opened(demo):
    initial = response_props(render_portfolio(demo))
    summary = json.dumps(initial["portfolio-summary"])
    assert "All 3 holdings priced" in summary

    switched = demo.call(
        "render_portfolio",
        values={"portfolio-refresh.data": 0, "active-tab.data": "portfolio"},
        triggered=["active-tab.data"],
    )
    assert switched.status_code == 204  # already rendered; nothing to redo


def test_every_view_prices_a_stock_from_the_same_sample_quote(demo):
    rows = response_props(render_watchlist(demo, sample_data.WATCHLIST_ID))
    rows_text = json.dumps(rows["watchlist-section"])
    portfolio_text = json.dumps(response_props(render_portfolio(demo))["portfolio-positions"])

    for symbol in SAMPLE:
        price = f"${sample_data.QUOTES[symbol].price:,.2f}"
        stock = response_props(load(demo, symbol))
        assert price in json.dumps(stock["stock-quote-price"])
        assert price in json.dumps(stock["stock-quote-stats"])
        assert price in rows_text
        assert price in portfolio_text
        assert "Sample close" in json.dumps(stock["stock-quote-caption"])
