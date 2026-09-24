from datetime import datetime
from unittest.mock import patch

import pandas as pd

from frontend import charts, data_sources


def _frozen_now(when):
    """Patch charts.datetime so 'now' is deterministic in period math."""
    mock = patch.object(charts, "datetime")
    started = mock.start()
    started.now.return_value = when
    started.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
    started.strptime.side_effect = datetime.strptime
    return mock


def _two_year_df():
    """Daily history resembling a free-tier Polygon response: ~2 years deep."""
    return pd.DataFrame(
        {
            "date": ["2024-07-17", "2025-01-02", "2025-07-01", "2026-01-02", "2026-05-18"],
            "close": [228.88, 240.0, 260.0, 300.0, 333.26],
        }
    )


def test_five_and_ten_year_periods_unavailable_with_two_years_of_data():
    df = _two_year_df()
    mock = _frozen_now(datetime(2026, 5, 18, 12, 0))
    try:
        assert charts.is_period_available(df, "1D") is True
        assert charts.is_period_available(df, "5D") is True
        assert charts.is_period_available(df, "1M") is True
        assert charts.is_period_available(df, "6M") is True
        assert charts.is_period_available(df, "YTD") is True
        assert charts.is_period_available(df, "1Y") is True
        assert charts.is_period_available(df, "5Y") is False
        assert charts.is_period_available(df, "10Y") is False
        assert charts.is_period_available(df, "MAX") is True
    finally:
        mock.stop()


def test_year_periods_unavailable_for_recent_ipo():
    df = pd.DataFrame(
        {
            "date": ["2026-03-02", "2026-04-15", "2026-05-18"],
            "close": [20.0, 22.0, 25.0],
        }
    )
    mock = _frozen_now(datetime(2026, 5, 18, 12, 0))
    try:
        assert charts.is_period_available(df, "1M") is True
        assert charts.is_period_available(df, "6M") is False
        assert charts.is_period_available(df, "YTD") is False
        assert charts.is_period_available(df, "1Y") is False
        assert charts.is_period_available(df, "MAX") is True
    finally:
        mock.stop()


def test_period_availability_tolerates_first_trading_day_offset():
    # First bar lands a few days after the exact cutoff (weekend/holiday gap):
    # the period must still count as available.
    now = datetime(2026, 5, 18, 12, 0)
    first_bar = "2016-05-23"  # 10y cutoff is 2016-05-20 (365*10 days back)
    df = pd.DataFrame(
        {
            "date": [first_bar, "2021-05-18", "2026-05-18"],
            "close": [25.0, 125.0, 333.0],
        }
    )
    mock = _frozen_now(now)
    try:
        assert charts.is_period_available(df, "10Y") is True
    finally:
        mock.stop()


def test_period_availability_true_for_empty_df():
    assert charts.is_period_available(pd.DataFrame(), "5Y") is True


def test_initial_chart_period_defaults_to_1y_with_enough_history():
    mock = _frozen_now(datetime(2026, 5, 18, 12, 0))
    try:
        assert charts.initial_chart_period(_two_year_df()) == "1Y"
    finally:
        mock.stop()


def test_initial_chart_period_falls_back_to_max_for_short_history():
    df = pd.DataFrame(
        {
            "date": ["2026-03-02", "2026-05-18"],
            "close": [20.0, 25.0],
        }
    )
    mock = _frozen_now(datetime(2026, 5, 18, 12, 0))
    try:
        assert charts.initial_chart_period(df) == "MAX"
    finally:
        mock.stop()


def _toolbar_buttons(toolbar):
    return {button.id["index"]: button for button in toolbar.children}


def test_build_period_toolbar_disables_periods_beyond_coverage():
    mock = _frozen_now(datetime(2026, 5, 18, 12, 0))
    try:
        toolbar = charts.build_period_toolbar("1Y", df=_two_year_df())
    finally:
        mock.stop()
    buttons = _toolbar_buttons(toolbar)

    assert buttons["5Y"].disabled is True
    assert buttons["10Y"].disabled is True
    assert "Jul 17, 2024" in buttons["5Y"].title
    assert not getattr(buttons["1Y"], "disabled", False)
    assert not getattr(buttons["MAX"], "disabled", False)
    assert "Daily bars" in buttons["1Y"].title


def test_build_period_toolbar_without_df_enables_everything():
    toolbar = charts.build_period_toolbar("1Y")
    buttons = _toolbar_buttons(toolbar)
    assert all(not getattr(b, "disabled", False) for b in buttons.values())


def test_build_change_readout_max_shows_since_date():
    readout = charts.build_change_readout(104.38, 45.60, "MAX", since_date="2024-07-17")
    period_tag = readout[-1]
    assert period_tag.children == "Since Jul 17, 2024"


def test_build_change_readout_max_without_since_date_keeps_plain_label():
    readout = charts.build_change_readout(104.38, 45.60, "MAX")
    assert readout[-1].children == "MAX"


def test_build_change_readout_non_max_ignores_since_date():
    readout = charts.build_change_readout(1.0, 2.0, "1Y", since_date="2024-07-17")
    assert readout[-1].children == "1Y"


def test_fetch_requests_full_history_not_ten_year_window():
    """The live source asks for all history (MAX) through the latest completed
    session, so the chart's last bar is the close the quote reports."""
    history = [
        {
            "date": "2024-07-17",
            "open": 228.0,
            "high": 230.0,
            "low": 227.0,
            "close": 228.88,
            "volume": 1000,
        },
    ]
    with (
        patch.object(data_sources, "get_stock_data", return_value=history) as mock_get,
        patch.object(data_sources, "get_most_recent_trading_day", return_value="2026-05-15"),
    ):
        bars = data_sources.LiveSource().history("AAPL")

    assert data_sources.MAX_HISTORY_START_DATE == "1970-01-01"
    mock_get.assert_called_once_with("AAPL", data_sources.MAX_HISTORY_START_DATE, "2026-05-15")
    assert bars == history
