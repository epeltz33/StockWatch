"""Watchlist rows carry live price and day change.

The rows previously showed ticker and company name only, which made the
watchlist unable to answer the one question it exists for. Prices for the
whole list are fetched in a single batched call.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.services.stock_services import Quote
from frontend import dashboard


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


@pytest.fixture
def quotes():
    with patch.object(dashboard, "get_quotes") as batched:
        yield batched


def test_watchlist_row_shows_price_and_positive_day_change(quotes):
    quotes.return_value = {
        "AAPL": Quote(symbol="AAPL", price=150.0, prev_close=145.0, change=5.0, change_pct=3.4483)
    }

    rendered = _texts(dashboard.create_watchlist_content(_watchlist(_stock("AAPL", "Apple", 1))))

    assert "$150.00" in rendered
    assert "+5.00 (+3.45%)" in rendered


def test_watchlist_row_shows_negative_day_change(quotes):
    quotes.return_value = {
        "TSLA": Quote(symbol="TSLA", price=90.0, prev_close=100.0, change=-10.0, change_pct=-10.0)
    }

    rendered = _texts(dashboard.create_watchlist_content(_watchlist(_stock("TSLA", "Tesla", 2))))

    assert "$90.00" in rendered
    assert "-10.00 (-10.00%)" in rendered


def test_watchlist_row_renders_price_without_change_when_change_unavailable(quotes):
    quotes.return_value = {"AAPL": Quote(symbol="AAPL", price=150.0)}

    content = dashboard.create_watchlist_content(_watchlist(_stock("AAPL", "Apple", 1)))
    rendered = _texts(content)

    assert "$150.00" in rendered
    assert not any("%" in text for text in rendered)


def test_watchlist_row_degrades_when_no_quote_is_available(quotes):
    quotes.return_value = {}

    rendered = _texts(dashboard.create_watchlist_content(_watchlist(_stock("AAPL", "Apple", 1))))

    # Still renders the row; price reads as unavailable rather than as zero
    assert "AAPL" in rendered
    assert "$0.00" not in rendered
    assert "—" in rendered


def test_watchlist_prices_every_row_in_a_single_batched_call(quotes):
    quotes.return_value = {}
    watchlist = _watchlist(
        _stock("AAPL", "Apple", 1), _stock("MSFT", "Microsoft", 2), _stock("NVDA", "Nvidia", 3)
    )

    dashboard.create_watchlist_content(watchlist)

    assert quotes.call_count == 1
    assert set(quotes.call_args[0][0]) == {"AAPL", "MSFT", "NVDA"}


def test_empty_watchlist_makes_no_quote_call():
    with patch.object(dashboard, "get_quotes", Mock()) as batched:
        dashboard.create_watchlist_content(_watchlist())
        batched.assert_not_called()
