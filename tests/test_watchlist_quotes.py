"""Watchlist rows carry closing price and day change.

The rows previously showed ticker and company name only, which made the
watchlist unable to answer the one question it exists for. Prices for the
whole list are fetched in a single batched call, and a missing price or
change reads as unavailable — never as $0.00 or a flat day.
"""

from types import SimpleNamespace

from app.services.stock_services import Quote, QuoteBatch
from frontend import watchlist_panel


def _stock(symbol, name, stock_id):
    return SimpleNamespace(symbol=symbol, name=name, id=stock_id)


def _watchlist(*stocks):
    return SimpleNamespace(name="Tech", id=1, stocks=list(stocks))


def _texts(component):
    """Flatten every string rendered anywhere in a Dash component tree."""
    if isinstance(component, str):
        return [component]
    if isinstance(component, (list, tuple)):
        return [text for child in component for text in _texts(child)]
    children = getattr(component, "children", None)
    return _texts(children) if children is not None else []


def _find(component, predicate):
    """Every component in the tree matching predicate."""
    found = []
    if isinstance(component, (list, tuple)):
        for child in component:
            found += _find(child, predicate)
        return found
    if component is None or isinstance(component, str):
        return found
    if predicate(component):
        found.append(component)
    return found + _find(getattr(component, "children", None), predicate)


class CountingSource:
    """Just enough of a data source for rendering, counting quote batches."""

    is_sample = False
    read_only = False

    def __init__(self, watchlist, quotes):
        self._watchlist = watchlist
        self._quotes = quotes
        self.batches = []

    def watchlist(self, watchlist_id):
        return self._watchlist if watchlist_id == self._watchlist.id else None

    def watchlists(self):
        return [self._watchlist]

    def quote_batch(self, symbols):
        self.batches.append(list(symbols))
        return QuoteBatch(quotes={s: q for s, q in self._quotes.items() if s in symbols})


def test_watchlist_row_shows_price_and_positive_day_change():
    quotes = {
        "AAPL": Quote(symbol="AAPL", price=150.0, prev_close=145.0, change=5.0, change_pct=3.4483)
    }

    rendered = _texts(
        watchlist_panel.create_watchlist_content(_watchlist(_stock("AAPL", "Apple", 1)), quotes)
    )

    assert "$150.00" in rendered
    assert "+5.00 (+3.45%)" in rendered


def test_watchlist_row_shows_negative_day_change():
    quotes = {
        "TSLA": Quote(symbol="TSLA", price=90.0, prev_close=100.0, change=-10.0, change_pct=-10.0)
    }

    rendered = _texts(
        watchlist_panel.create_watchlist_content(_watchlist(_stock("TSLA", "Tesla", 2)), quotes)
    )

    assert "$90.00" in rendered
    assert "-10.00 (-10.00%)" in rendered


def test_watchlist_row_renders_price_without_change_when_change_unavailable():
    quotes = {"AAPL": Quote(symbol="AAPL", price=150.0)}

    rendered = _texts(
        watchlist_panel.create_watchlist_content(_watchlist(_stock("AAPL", "Apple", 1)), quotes)
    )

    assert "$150.00" in rendered
    assert not any("%" in text for text in rendered)


def test_watchlist_row_degrades_when_no_quote_is_available():
    rendered = _texts(
        watchlist_panel.create_watchlist_content(_watchlist(_stock("AAPL", "Apple", 1)), {})
    )

    # Still renders the row; price reads as unavailable rather than as zero
    assert "AAPL" in rendered
    assert "$0.00" not in rendered
    assert "—" in rendered


def test_a_row_closing_on_a_different_session_is_dated():
    quotes = {
        "AAPL": Quote(symbol="AAPL", price=150.0, session_date="2026-09-18"),
        "MSFT": Quote(symbol="MSFT", price=400.0, session_date="2026-09-18"),
        "OTC": Quote(symbol="OTC", price=4.0, session_date="2026-09-17"),
    }
    watchlist = _watchlist(
        _stock("AAPL", "Apple", 1), _stock("MSFT", "Microsoft", 2), _stock("OTC", "Otc Co", 3)
    )

    rendered = _texts(watchlist_panel.create_watchlist_content(watchlist, quotes))

    assert rendered.count("Sep 17") == 1


def test_each_ticker_is_a_selection_control_marking_the_active_one():
    watchlist = _watchlist(_stock("AAPL", "Apple", 1), _stock("MSFT", "Microsoft", 2))

    content = watchlist_panel.create_watchlist_content(watchlist, {}, active_symbol="MSFT")
    buttons = _find(
        content,
        lambda c: (
            isinstance(getattr(c, "id", None), dict) and c.id.get("type") == "load-watchlist-stock"
        ),
    )

    assert [b.id["index"] for b in buttons] == ["AAPL", "MSFT"]
    active = [b for b in buttons if "watchlist-select--active" in b.className]
    assert [b.id["index"] for b in active] == ["MSFT"]
    assert active[0].to_plotly_json()["props"]["aria-current"] == "true"


def test_read_only_rows_have_no_edit_controls():
    watchlist = _watchlist(_stock("AAPL", "Apple", 1))

    content = watchlist_panel.create_watchlist_content(watchlist, {}, editable=False)
    editing = _find(
        content,
        lambda c: (
            isinstance(getattr(c, "id", None), dict)
            and c.id.get("type") in ("remove-from-watchlist", "delete-watchlist")
        ),
    )

    assert editing == []


def test_watchlist_prices_every_row_in_a_single_batched_call():
    watchlist = _watchlist(
        _stock("AAPL", "Apple", 1), _stock("MSFT", "Microsoft", 2), _stock("NVDA", "Nvidia", 3)
    )
    source = CountingSource(watchlist, {})

    watchlist_panel.render_watchlist_section(source, watchlist.id, None)

    assert len(source.batches) == 1
    assert set(source.batches[0]) == {"AAPL", "MSFT", "NVDA"}


def test_empty_watchlist_makes_no_quote_call():
    source = CountingSource(_watchlist(), {})

    watchlist_panel.render_watchlist_section(source, 1, None)

    assert source.batches == []
