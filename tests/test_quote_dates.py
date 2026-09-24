"""Quote dates are New York trading sessions, and missing sessions stay missing.

The old helper used the server clock (UTC on Render), returned Monday for a
Monday morning whose session had not closed, and returned the previous day
after the 4:00 PM close. A holiday either side of the latest session must be
stepped over or left unavailable — never turned into a zero change.
"""

import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app.extensions import cache
from app.services import stock_services
from app.services.stock_services import (
    get_most_recent_trading_day,
    get_quote_batch,
    get_quotes,
    get_stock_data,
)
from app.utils.cache_manager import StockCache

ET = ZoneInfo("America/New_York")


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Monday before the close: Monday's session is still open -> Friday
        (datetime(2026, 6, 29, 10, 0, tzinfo=ET), "2026-06-26"),
        # Monday at and after the close: Monday is complete
        (datetime(2026, 6, 29, 16, 0, tzinfo=ET), "2026-06-29"),
        (datetime(2026, 6, 29, 17, 30, tzinfo=ET), "2026-06-29"),
        # Tuesday before the open -> Monday
        (datetime(2026, 6, 30, 9, 0, tzinfo=ET), "2026-06-29"),
        # Friday evening -> Friday (not Thursday)
        (datetime(2026, 6, 26, 18, 0, tzinfo=ET), "2026-06-26"),
        # Weekends -> Friday
        (datetime(2026, 6, 27, 12, 0, tzinfo=ET), "2026-06-26"),
        (datetime(2026, 6, 28, 20, 0, tzinfo=ET), "2026-06-26"),
    ],
)
def test_most_recent_trading_day_in_new_york_time(now, expected):
    assert get_most_recent_trading_day(now) == expected


@pytest.mark.parametrize(
    ("utc_now", "expected"),
    [
        # 20:30 UTC Monday is 4:30 PM EDT: the session has closed
        (datetime(2026, 6, 29, 20, 30, tzinfo=UTC), "2026-06-29"),
        # 14:00 UTC Monday is 10:00 AM EDT: still Friday's close
        (datetime(2026, 6, 29, 14, 0, tzinfo=UTC), "2026-06-26"),
        # 01:30 UTC Tuesday is still Monday evening in New York
        (datetime(2026, 6, 30, 1, 30, tzinfo=UTC), "2026-06-29"),
        # Winter (EST, UTC-5): 20:30 UTC is 3:30 PM, before the close
        (datetime(2026, 1, 5, 20, 30, tzinfo=UTC), "2026-01-02"),
        (datetime(2026, 1, 5, 21, 30, tzinfo=UTC), "2026-01-05"),
    ],
)
def test_most_recent_trading_day_ignores_the_server_timezone(utc_now, expected):
    assert get_most_recent_trading_day(utc_now) == expected


def test_most_recent_trading_day_reads_the_clock_in_new_york():
    frozen = datetime(2026, 6, 29, 20, 30, tzinfo=UTC)  # 4:30 PM EDT Monday
    with patch.object(stock_services, "datetime") as mock_datetime:
        mock_datetime.now.side_effect = lambda tz=None: frozen.astimezone(tz)
        assert get_most_recent_trading_day() == "2026-06-29"
    mock_datetime.now.assert_called_once_with(stock_services.EASTERN_TZ)


# --- grouped sessions: holidays and metadata ---------------------------------

LATEST = "2026-06-30"  # Tuesday
PRIOR = "2026-06-29"  # Monday
FRIDAY = "2026-06-26"


def _grouped(ticker, close, timestamp=None):
    return SimpleNamespace(ticker=ticker, close=close, timestamp=timestamp)


def _by_date(day_map):
    def side_effect(date, *args, **kwargs):
        return day_map.get(date, [])

    return side_effect


@pytest.fixture
def polygon(app):
    with patch.object(stock_services, "get_most_recent_trading_day", return_value=LATEST):
        with patch.object(stock_services, "polygon_client") as client:
            yield client


def test_quote_carries_session_date_provider_timestamp_and_fetch_time(polygon):
    close_ms = int(datetime(2026, 6, 30, 16, 0, tzinfo=ET).timestamp() * 1000)
    polygon.get_grouped_daily_aggs.side_effect = _by_date(
        {LATEST: [_grouped("AAPL", 191.5, close_ms)], PRIOR: [_grouped("AAPL", 190.0)]}
    )

    quote = get_quotes(["AAPL"])["AAPL"]

    assert quote.session_date == LATEST
    assert quote.price_timestamp == "2026-06-30T16:00:00-04:00"
    fetched = datetime.fromisoformat(quote.fetched_at)
    assert fetched.tzinfo is not None
    assert abs((datetime.now(UTC) - fetched).total_seconds()) < 60


def test_cached_quote_keeps_its_original_fetch_time(polygon):
    polygon.get_grouped_daily_aggs.side_effect = _by_date(
        {LATEST: [_grouped("AAPL", 191.5)], PRIOR: [_grouped("AAPL", 190.0)]}
    )
    first = get_quotes(["AAPL"])["AAPL"]

    with patch.object(stock_services, "_utc_now_iso", return_value="2099-01-01T00:00:00+00:00"):
        again = get_quotes(["AAPL"])["AAPL"]

    assert again.fetched_at == first.fetched_at


def test_latest_session_with_no_data_steps_back_to_the_last_real_session(polygon):
    # Tuesday has no bars yet (holiday, or close not yet published)
    polygon.get_grouped_daily_aggs.side_effect = _by_date(
        {
            LATEST: [],
            PRIOR: [_grouped("AAPL", 190.0)],
            FRIDAY: [_grouped("AAPL", 188.0)],
        }
    )

    quote = get_quotes(["AAPL"])["AAPL"]

    assert quote.session_date == PRIOR
    assert quote.price == 190.0
    assert quote.change == pytest.approx(2.0)


def test_holiday_before_the_latest_session_uses_the_real_prior_close(polygon):
    # Monday was a holiday: Tuesday's change is measured against Friday
    polygon.get_grouped_daily_aggs.side_effect = _by_date(
        {LATEST: [_grouped("AAPL", 191.5)], PRIOR: [], FRIDAY: [_grouped("AAPL", 190.0)]}
    )

    quote = get_quotes(["AAPL"])["AAPL"]

    assert quote.prev_close == 190.0
    assert quote.change == pytest.approx(1.5)


def test_missing_prior_sessions_leave_the_change_unavailable_not_zero(polygon):
    polygon.get_grouped_daily_aggs.side_effect = _by_date({LATEST: [_grouped("AAPL", 191.5)]})

    quote = get_quotes(["AAPL"])["AAPL"]

    assert quote.price == 191.5
    assert quote.prev_close is None
    assert quote.change is None
    assert quote.change_pct is None


def test_empty_sessions_are_not_cached(polygon):
    """A close published a few minutes after 4 PM must be picked up."""
    polygon.get_grouped_daily_aggs.side_effect = _by_date({PRIOR: [_grouped("AAPL", 190.0)]})
    get_quotes(["AAPL"])

    stock_cache = StockCache(cache)
    assert (
        stock_cache.get_cached_data(stock_services.MARKET_CACHE_KEY, "grouped", date=LATEST) is None
    )
    assert (
        stock_cache.get_cached_data(stock_services.MARKET_CACHE_KEY, "grouped", date=PRIOR)
        is not None
    )


# --- per-symbol fallback and failure classification --------------------------


class NotFound(Exception):
    pass


def test_per_symbol_fallback_steps_over_a_session_with_no_bar(polygon):
    polygon.get_grouped_daily_aggs.side_effect = Exception("NOT_AUTHORIZED for this plan")

    def open_close(symbol, date):
        if date == LATEST:
            raise NotFound('{"status":"NOT_FOUND","message":"Data not found."}')
        return SimpleNamespace(close=190.0, from_=date)

    polygon.get_daily_open_close_agg.side_effect = open_close

    batch = get_quote_batch(["AAPL"])

    assert batch.quotes["AAPL"].price == 190.0
    assert batch.quotes["AAPL"].session_date == PRIOR
    assert not batch.failed


def test_provider_failure_is_reported_separately_from_missing_data(polygon):
    polygon.get_grouped_daily_aggs.side_effect = Exception("connection reset")
    polygon.get_daily_open_close_agg.side_effect = Exception("429 too many requests")

    batch = get_quote_batch(["AAPL", "MSFT"])

    assert batch.quotes == {}
    assert batch.errors == {"AAPL", "MSFT"}
    assert batch.failed


def test_unknown_symbol_is_missing_data_not_a_failure(polygon):
    polygon.get_grouped_daily_aggs.side_effect = _by_date(
        {LATEST: [_grouped("AAPL", 191.5)], PRIOR: [_grouped("AAPL", 190.0)]}
    )
    polygon.get_daily_open_close_agg.side_effect = NotFound('{"status":"NOT_FOUND"}')

    batch = get_quote_batch(["AAPL", "NOSUCH"])

    assert set(batch.quotes) == {"AAPL"}
    assert not batch.failed


# --- daily bars ----------------------------------------------------------------


@pytest.fixture
def pacific_server_clock():
    """Run with the process in US/Pacific, where midnight New York is 9 PM the
    previous evening."""
    with patch.dict("os.environ", {"TZ": "America/Los_Angeles"}):
        time.tzset()
        yield
    time.tzset()


def test_daily_bars_are_dated_in_new_york_time(app, pacific_server_clock):
    midnight_et = int(datetime(2026, 6, 30, 0, 0, tzinfo=ET).timestamp() * 1000)
    bar = SimpleNamespace(timestamp=midnight_et, open=1.0, high=1.0, low=1.0, close=1.0, volume=10)
    with patch.object(stock_services, "polygon_client") as client:
        client.get_aggs.return_value = [bar]
        data = get_stock_data("AAPL", "2026-06-01", "2026-06-30")

    assert data[0]["date"] == "2026-06-30"
