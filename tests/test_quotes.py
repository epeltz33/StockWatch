"""Batched quote fetching: one grouped API call instead of one call per symbol.

The per-symbol path (get_daily_open_close_agg) burns one HTTP request per
ticker, which trips the market-data provider's rate limit on portfolios and
watchlists of more than a handful of symbols. These tests pin the batching
contract and the degradation path when the grouped endpoint is unavailable.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.extensions import cache
from app.services import stock_services
from app.services.stock_services import get_quotes, get_stock_price
from app.utils.cache_manager import StockCache

TODAY = "2026-05-18"
PREV = "2026-05-15"


def _grouped(ticker, close, open_=None):
    return SimpleNamespace(
        ticker=ticker,
        open=open_ if open_ is not None else close,
        high=close,
        low=close,
        close=close,
        volume=1_000_000,
    )


@pytest.fixture
def fixed_trading_days():
    """Pin the calendar so grouped-call assertions are date-independent."""
    with patch.object(stock_services, "get_most_recent_trading_day", return_value=TODAY):
        yield


@pytest.fixture
def polygon(app, fixed_trading_days):
    with app.app_context():
        with patch.object(stock_services, "polygon_client") as client:
            yield client


def _grouped_by_date(day_map):
    """Build a get_grouped_daily_aggs side effect from {date: [aggs]}."""

    def side_effect(date, *args, **kwargs):
        if date not in day_map:
            raise AssertionError(f"unexpected grouped call for {date}")
        return day_map[date]

    return side_effect


def test_get_quotes_fetches_every_symbol_in_one_grouped_call(polygon):
    polygon.get_grouped_daily_aggs.side_effect = _grouped_by_date(
        {
            TODAY: [_grouped("AAPL", 150.0), _grouped("MSFT", 400.0), _grouped("NVDA", 900.0)],
            PREV: [_grouped("AAPL", 145.0), _grouped("MSFT", 410.0), _grouped("NVDA", 900.0)],
        }
    )

    quotes = get_quotes(["AAPL", "MSFT", "NVDA"])

    assert set(quotes) == {"AAPL", "MSFT", "NVDA"}
    assert quotes["AAPL"].price == 150.0
    assert quotes["MSFT"].price == 400.0
    assert quotes["NVDA"].price == 900.0
    # Two grouped calls (latest session + prior session), not one per symbol
    assert polygon.get_grouped_daily_aggs.call_count == 2
    polygon.get_daily_open_close_agg.assert_not_called()


def test_get_quotes_computes_day_change_against_previous_close(polygon):
    polygon.get_grouped_daily_aggs.side_effect = _grouped_by_date(
        {
            TODAY: [_grouped("AAPL", 110.0)],
            PREV: [_grouped("AAPL", 100.0)],
        }
    )

    quote = get_quotes(["AAPL"])["AAPL"]

    assert quote.prev_close == 100.0
    assert quote.change == pytest.approx(10.0)
    assert quote.change_pct == pytest.approx(10.0)


def test_get_quotes_reports_negative_day_change(polygon):
    polygon.get_grouped_daily_aggs.side_effect = _grouped_by_date(
        {
            TODAY: [_grouped("AAPL", 90.0)],
            PREV: [_grouped("AAPL", 100.0)],
        }
    )

    quote = get_quotes(["AAPL"])["AAPL"]

    assert quote.change == pytest.approx(-10.0)
    assert quote.change_pct == pytest.approx(-10.0)


def test_get_quotes_leaves_change_unset_when_previous_session_unavailable(polygon):
    def side_effect(date, *args, **kwargs):
        if date == TODAY:
            return [_grouped("AAPL", 150.0)]
        raise Exception("prior session not available on this plan")

    polygon.get_grouped_daily_aggs.side_effect = side_effect

    quote = get_quotes(["AAPL"])["AAPL"]

    assert quote.price == 150.0
    assert quote.prev_close is None
    assert quote.change is None
    assert quote.change_pct is None


def test_get_quotes_serves_cached_symbols_without_touching_the_api(polygon):
    polygon.get_grouped_daily_aggs.side_effect = _grouped_by_date(
        {TODAY: [_grouped("AAPL", 150.0)], PREV: [_grouped("AAPL", 145.0)]}
    )
    get_quotes(["AAPL"])
    polygon.reset_mock()

    quotes = get_quotes(["AAPL"])

    assert quotes["AAPL"].price == 150.0
    polygon.get_grouped_daily_aggs.assert_not_called()
    polygon.get_daily_open_close_agg.assert_not_called()


def _evict_cached_sessions():
    """Drop the whole-market session entries, leaving per-symbol quotes cached."""
    stock_cache = StockCache(cache)
    for date in (TODAY, PREV):
        cache.delete(
            stock_cache._get_cache_key(stock_services.MARKET_CACHE_KEY, "grouped", date=date)
        )


def test_get_quotes_merges_cached_and_freshly_fetched_symbols(polygon):
    polygon.get_grouped_daily_aggs.side_effect = _grouped_by_date(
        {TODAY: [_grouped("AAPL", 150.0)], PREV: [_grouped("AAPL", 145.0)]}
    )
    get_quotes(["AAPL"])
    # A cached session answers for every ticker in it, so force a fresh
    # grouped fetch to show that MSFT is fetched while AAPL stays cached.
    _evict_cached_sessions()

    polygon.get_grouped_daily_aggs.side_effect = _grouped_by_date(
        {
            TODAY: [_grouped("AAPL", 999.0), _grouped("MSFT", 400.0)],
            PREV: [_grouped("AAPL", 999.0), _grouped("MSFT", 390.0)],
        }
    )
    quotes = get_quotes(["AAPL", "MSFT"])

    # AAPL comes from cache (150.0, not the fresh 999.0); MSFT from the API
    assert quotes["AAPL"].price == 150.0
    assert quotes["MSFT"].price == 400.0


def test_symbols_priced_later_reuse_the_cached_session_without_another_call(polygon):
    """The chart, watchlist, and portfolio each ask for different symbols a
    moment apart; the second batch must not download the whole market again."""
    polygon.get_grouped_daily_aggs.side_effect = _grouped_by_date(
        {
            TODAY: [_grouped("AAPL", 150.0), _grouped("MSFT", 400.0)],
            PREV: [_grouped("AAPL", 145.0), _grouped("MSFT", 390.0)],
        }
    )
    get_quotes(["AAPL"])
    polygon.reset_mock()

    quote = get_quotes(["MSFT"])["MSFT"]

    assert quote.price == 400.0
    assert quote.change == pytest.approx(10.0)
    polygon.get_grouped_daily_aggs.assert_not_called()
    polygon.get_daily_open_close_agg.assert_not_called()


def test_get_quotes_does_not_cache_symbols_nobody_asked_for(polygon):
    """The grouped endpoint returns the whole market; caching all of it would
    evict every other entry out of the bounded in-process cache."""
    polygon.get_grouped_daily_aggs.side_effect = _grouped_by_date(
        {
            TODAY: [_grouped("AAPL", 150.0), _grouped("ZZZZ", 1.0)],
            PREV: [_grouped("AAPL", 145.0), _grouped("ZZZZ", 1.0)],
        }
    )

    get_quotes(["AAPL"])

    stock_cache = StockCache(cache)
    assert stock_cache.get_cached_data("AAPL", "quote") is not None
    assert stock_cache.get_cached_data("ZZZZ", "quote") is None


def test_get_quotes_falls_back_to_per_symbol_when_grouped_is_unavailable(polygon):
    polygon.get_grouped_daily_aggs.side_effect = Exception("not available on this plan")
    polygon.get_daily_open_close_agg.return_value = SimpleNamespace(close=150.0, open=149.0)

    quotes = get_quotes(["AAPL", "MSFT"])

    assert quotes["AAPL"].price == 150.0
    assert quotes["MSFT"].price == 150.0
    assert quotes["AAPL"].change is None
    assert polygon.get_daily_open_close_agg.call_count == 2


def test_get_quotes_omits_symbols_the_provider_has_no_data_for(polygon):
    polygon.get_grouped_daily_aggs.side_effect = _grouped_by_date(
        {TODAY: [_grouped("AAPL", 150.0)], PREV: [_grouped("AAPL", 145.0)]}
    )
    polygon.get_daily_open_close_agg.return_value = None

    quotes = get_quotes(["AAPL", "NOSUCH"])

    assert "AAPL" in quotes
    assert "NOSUCH" not in quotes


def test_get_quotes_normalises_and_deduplicates_symbols(polygon):
    polygon.get_grouped_daily_aggs.side_effect = _grouped_by_date(
        {TODAY: [_grouped("AAPL", 150.0)], PREV: [_grouped("AAPL", 145.0)]}
    )

    quotes = get_quotes(["aapl", "AAPL", " aapl "])

    assert set(quotes) == {"AAPL"}


def test_get_quotes_returns_empty_without_calling_the_api_for_no_symbols(polygon):
    assert get_quotes([]) == {}
    polygon.get_grouped_daily_aggs.assert_not_called()


def test_get_stock_price_reads_through_the_batched_quote_path(polygon):
    polygon.get_grouped_daily_aggs.side_effect = _grouped_by_date(
        {TODAY: [_grouped("AAPL", 150.0)], PREV: [_grouped("AAPL", 145.0)]}
    )

    assert get_stock_price("AAPL") == 150.0
    polygon.get_daily_open_close_agg.assert_not_called()
