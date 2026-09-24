"""The stock view: loading a symbol, failing honestly, and labelling prices.

- A search that fails leaves the previous chart exactly as it was — still
  labelled with its own symbol — and names the failed symbol, with a retry.
- The header and details show the same quote. Without a quote, the last bar
  of the price history stands in and says so; a missing prior close is
  "unavailable", never a zero change.
- Restoring a saved view reloads its symbol and period.
"""

import json

import pytest
from dash.exceptions import PreventUpdate

from app.services import sample_data
from app.services.stock_services import Quote, QuoteBatch
from frontend import stock_view
from frontend.data_sources import SampleSource

HISTORY = [
    {"date": "2026-09-16", "open": 100, "high": 102, "low": 99, "close": 101.0, "volume": 10},
    {"date": "2026-09-17", "open": 101, "high": 104, "low": 100, "close": 103.0, "volume": 12},
    {"date": "2026-09-18", "open": 103, "high": 106, "low": 102, "close": 105.0, "volume": 15},
]


class FakeSource:
    """A live-style source with scripted histories and quotes."""

    mode = "app"
    is_sample = False
    read_only = False
    search_symbols = None

    def __init__(self, histories=None, quotes=None, failed=()):
        self.histories = histories or {}
        self.quotes = quotes or {}
        self.failed = set(failed)
        self.lists = []

    def history(self, symbol):
        return list(self.histories.get(symbol, []))

    def intraday(self, symbol):
        return []

    def details(self, symbol):
        return {"name": f"{symbol} Corp", "description": "", "market_cap": None}

    def logo_src(self, symbol, details):
        return None

    def quote_batch(self, symbols):
        return QuoteBatch(
            quotes={s: q for s, q in self.quotes.items() if s in symbols},
            errors={s for s in symbols if s in self.failed},
        )

    def watchlists(self):
        return self.lists


def search(source, typed, shown=None, period=None):
    return stock_view.handle_stock_request(
        source, "search-button", 1, typed=typed, shown=shown, period=period
    )


def text(value):
    return json.dumps(value, default=lambda c: c.to_plotly_json())


# --- failures keep the previous view ------------------------------------------------


def test_failed_search_leaves_the_previous_chart_untouched():
    source = FakeSource(histories={"AAPL": HISTORY})

    values = search(source, "zzzz", shown="AAPL")

    # Only the search status, the retry target, and the input change
    assert set(values) == {"search-status.children", "failed-search.data", "stock-input.invalid"}
    message = text(values["search-status.children"])
    assert "Couldn't load ZZZZ" in message
    assert "Still showing AAPL" in message
    assert "Retry" in message
    assert values["failed-search.data"] == "ZZZZ"
    assert values["stock-input.invalid"] is True


def test_retrying_a_failed_search_loads_the_symbol_once_it_works():
    source = FakeSource(histories={"AAPL": HISTORY})
    search(source, "msft", shown="AAPL")
    source.histories["MSFT"] = HISTORY

    values = stock_view.handle_stock_request(
        source,
        "symbol-request",
        {"symbol": "MSFT", "origin": "retry", "at": 1},
        shown="AAPL",
    )

    assert values["stock-symbol-store.data"] == "MSFT"
    assert values["search-status.children"] is None
    assert values["failed-search.data"] is None


def test_first_load_failure_clears_the_skeletons_instead_of_spinning_forever():
    source = FakeSource()

    values = stock_view.handle_stock_request(
        source, "restore-request", {"symbol": "AAPL"}, restore={"symbol": "AAPL"}
    )

    assert values["chart-card.className"].endswith("chart-card--empty")
    assert "Couldn't load AAPL" in text(values["search-status.children"])


def test_malformed_input_is_explained_not_searched():
    values = search(FakeSource(), "not a ticker!", shown="AAPL")

    assert "isn't a ticker symbol" in text(values["search-status.children"])
    assert "stock-chart.figure" not in values


def test_zero_click_triggers_are_ignored():
    with pytest.raises(PreventUpdate):
        stock_view.handle_stock_request(FakeSource(), "search-button", 0, typed="AAPL")
    with pytest.raises(PreventUpdate):
        stock_view.handle_stock_request(FakeSource(), "symbol-request", None)


# --- one price, labelled -------------------------------------------------------------


def test_header_and_details_show_the_same_quote_with_its_session_date():
    quote = Quote(
        symbol="AAPL",
        price=105.0,
        prev_close=103.0,
        change=2.0,
        change_pct=1.94,
        session_date="2026-09-18",
        fetched_at="2026-09-18T20:05:00+00:00",
    )
    values = search(FakeSource(histories={"AAPL": HISTORY}, quotes={"AAPL": quote}), "AAPL")

    assert "$105.00" in text(values["stock-quote-price.children"])
    assert "$105.00" in text(values["stock-quote-stats.children"])
    caption = text(values["stock-quote-caption.children"])
    assert "Close" in caption and "Sep 18, 2026" in caption and "retrieved" in caption
    assert "live" not in caption.lower()


def test_without_a_quote_the_history_close_is_labelled_as_a_fallback():
    source = FakeSource(histories={"AAPL": HISTORY}, failed={"AAPL"})

    values = search(source, "AAPL")

    caption = text(values["stock-quote-caption.children"])
    assert "Last close in price history" in caption
    assert "Quote unavailable" in caption
    assert "Sep 18, 2026" in caption
    stats = text(values["stock-quote-stats.children"])
    assert "Last close (price history)" in stats
    assert "$105.00" in stats


def test_a_missing_prior_close_is_unavailable_not_a_zero_change():
    quote = Quote(symbol="AAPL", price=105.0, session_date="2026-09-18")

    values = search(FakeSource(histories={"AAPL": HISTORY}, quotes={"AAPL": quote}), "AAPL")

    stats = text(values["stock-quote-stats.children"])
    assert "Change unavailable" in stats
    assert "+0.00" not in stats and "0.00%" not in stats


# --- restoring a saved view ----------------------------------------------------------


def test_restore_reloads_the_saved_symbol_and_period():
    long_history = sample_data.history("MSFT")
    source = FakeSource(histories={"MSFT": long_history})

    values = stock_view.handle_stock_request(
        source,
        "restore-request",
        {"symbol": "MSFT", "period": "5Y"},
        restore={"symbol": "MSFT", "period": "5Y"},
    )

    assert values["stock-symbol-store.data"] == "MSFT"
    assert values["chart-period-store.data"] == "5Y"


def test_restore_falls_back_to_a_period_the_history_can_show():
    source = FakeSource(histories={"AAPL": HISTORY})  # three days of bars

    values = stock_view.handle_stock_request(
        source, "restore-request", {}, restore={"symbol": "AAPL", "period": "10Y"}
    )

    assert values["chart-period-store.data"] == "MAX"


def test_with_nothing_saved_the_first_watchlist_ticker_is_shown():
    source = FakeSource(histories={"NVDA": HISTORY})
    source.lists = [
        type("W", (), {"stocks": ()})(),
        type("W", (), {"stocks": (type("S", (), {"symbol": "NVDA"})(),)})(),
    ]

    values = stock_view.handle_stock_request(source, "restore-request", {}, restore={})

    assert values["stock-symbol-store.data"] == "NVDA"


def test_a_new_account_starts_on_the_search_prompt():
    values = stock_view.handle_stock_request(FakeSource(), "restore-request", {}, restore={})

    assert values["chart-card.className"].endswith("chart-card--empty")
    assert "search-status.children" not in values


def test_the_demo_always_opens_on_aapl():
    values = stock_view.handle_stock_request(SampleSource(), "restore-request", {}, restore={})

    assert values["stock-symbol-store.data"] == "AAPL"
    assert "Sample close" in text(values["stock-quote-caption.children"])
