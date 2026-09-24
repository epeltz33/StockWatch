"""How watchlist and stock prices refresh.

The old dashboard rebuilt the watchlist on an unconditional 30-second timer.
Now it loads once, re-renders after edits, refreshes on demand, and polls
every five minutes only while the Market section is visible (never in the
demo). A refresh updates prices in place — keeping focus and the user's
selection — and a failed refresh leaves the last good prices on screen with
a retry instead of blanking them.
"""

from types import SimpleNamespace

import pytest
from dash import no_update

from app.services.stock_services import Quote, QuoteBatch
from frontend import dashboard, watchlist_panel
from tests.dash_client import DashClient


def _quote(symbol, price, fetched="2026-09-18T20:05:00+00:00"):
    return Quote(
        symbol=symbol,
        price=price,
        prev_close=price - 1,
        change=1.0,
        change_pct=1.0 / (price - 1) * 100,
        session_date="2026-09-18",
        fetched_at=fetched,
    )


class StubSource:
    is_sample = False
    read_only = False

    def __init__(self, batch):
        self.batch = batch
        self.requested = []

    def quote_batch(self, symbols):
        self.requested.append(list(symbols))
        return self.batch


STOCK_META = {
    "symbol": "AAPL",
    "last_bar": {"date": "2026-09-18", "close": 231.48},
    "prev_bar": {"date": "2026-09-17", "close": 231.98},
}


@pytest.fixture
def live(app, client):
    return app.extensions["dash_apps"]["app"]


def test_refresh_is_wired_to_the_interval_a_manual_button_and_retry(app, client):
    refresh = DashClient(client, app.extensions["dash_apps"]["app"])
    _, entry = refresh.find("refresh_prices")
    inputs = {i["id"] for i in entry["inputs"]}

    assert inputs == {"market-refresh-interval", "refresh-watchlist", "retry-request"}


def test_polling_is_every_five_minutes_and_only_while_market_is_visible(live):
    assert dashboard.REFRESH_INTERVAL_MS == 5 * 60 * 1000
    toggles = [
        entry
        for key, entry in live.callback_map.items()
        if key == "market-refresh-interval.disabled"
    ]
    assert toggles, "nothing enables/disables polling"
    assert [i["id"] for i in toggles[0]["inputs"]] == ["active-tab"]


def test_edits_and_selection_rerender_the_watchlist(live):
    _, entry = DashClient(SimpleNamespace(), live).find("render_watchlist")
    inputs = {(i["id"], i["property"]) for i in entry["inputs"]}

    assert inputs == {("watchlist-dropdown", "value"), ("watchlist-version", "data")}


def test_refresh_updates_rows_and_the_stock_view_from_one_batch():
    source = StubSource(
        QuoteBatch(quotes={"AAPL": _quote("AAPL", 231.48), "MSFT": _quote("MSFT", 441.96)})
    )

    cells, price, caption, stats, status, meta = watchlist_panel.refresh_market(
        source, ["AAPL", "MSFT"], STOCK_META, {"ok": True}
    )

    assert source.requested == [["AAPL", "MSFT"]]
    assert len(cells) == 2
    assert "$231.48" in str(price) and "$231.48" in str(stats)
    assert "Closes · Sep 18, 2026" in status
    assert meta == {"ok": True, "fetched_at": "2026-09-18T20:05:00+00:00"}


def test_refresh_includes_the_charted_symbol_when_it_is_not_a_row():
    source = StubSource(QuoteBatch(quotes={"AAPL": _quote("AAPL", 231.48)}))

    watchlist_panel.refresh_market(source, ["MSFT"], STOCK_META, None)

    assert source.requested == [["MSFT", "AAPL"]]


def test_failed_refresh_keeps_the_last_good_view_and_offers_retry():
    source = StubSource(QuoteBatch(quotes={}, errors={"AAPL", "MSFT"}))
    previous = {"ok": True, "fetched_at": "2026-09-18T20:05:00+00:00"}

    cells, price, caption, stats, status, meta = watchlist_panel.refresh_market(
        source, ["AAPL", "MSFT"], STOCK_META, previous
    )

    # Nothing on screen changes...
    assert cells == [no_update, no_update]
    assert price is no_update and caption is no_update and stats is no_update
    # ...and the status says so, when the kept prices are from, and offers retry
    text = str(status)
    assert "Couldn't refresh prices" in text
    assert "Showing prices retrieved" in text
    retry = status.children[-1]
    assert retry.id == watchlist_panel.RETRY_PRICES_ID
    assert meta["ok"] is False and meta["fetched_at"] == previous["fetched_at"]


def test_a_partial_failure_also_keeps_the_last_view():
    """Some quotes came back but others failed: showing a mix of fresh and
    blanked prices would be worse than keeping the complete last view."""
    source = StubSource(QuoteBatch(quotes={"AAPL": _quote("AAPL", 240.0)}, errors={"MSFT"}))

    cells, *_rest, status, meta = watchlist_panel.refresh_market(
        source, ["AAPL", "MSFT"], STOCK_META, {"ok": True}
    )

    assert cells == [no_update, no_update]
    assert meta["ok"] is False


def test_first_load_failure_shows_rows_and_a_retry():
    watchlist = SimpleNamespace(
        id=7, name="Tech", stocks=[SimpleNamespace(symbol="AAPL", name="Apple", id=1)]
    )
    source = StubSource(QuoteBatch(quotes={}, errors={"AAPL"}))
    source.watchlist = lambda wid: watchlist if wid == 7 else None
    source.watchlists = lambda: [watchlist]

    section, status, meta = watchlist_panel.render_watchlist_section(source, 7, None)

    assert "AAPL" in str(section)
    assert "Couldn't load prices" in str(status)
    assert meta == {"ok": False}
