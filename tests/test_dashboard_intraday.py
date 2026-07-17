from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from app.services import stock_services
from frontend import dashboard


def _agg(timestamp, open_, high, low, close, volume):
    return SimpleNamespace(
        timestamp=int(timestamp.timestamp() * 1000),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_filter_data_for_period_leaves_1d_daily_data_unsliced():
    df = pd.DataFrame(
        {
            "date": ["2026-05-14", "2026-05-15", "2026-05-18"],
            "close": [100.0, 102.0, 101.0],
        }
    )

    filtered = dashboard.filter_data_for_period(df, "1D")

    pd.testing.assert_frame_equal(filtered, df)


@pytest.mark.parametrize(
    ("period", "expected_dates"),
    [
        ("5D", ["2026-05-12", "2026-05-18"]),
        ("1M", ["2026-04-20", "2026-05-12", "2026-05-18"]),
        ("6M", ["2026-01-02", "2026-04-20", "2026-05-12", "2026-05-18"]),
        ("YTD", ["2026-01-02", "2026-04-20", "2026-05-12", "2026-05-18"]),
        ("10Y", ["2020-01-02", "2026-01-02", "2026-04-20", "2026-05-12", "2026-05-18"]),
        (
            "MAX",
            ["2015-01-02", "2020-01-02", "2026-01-02", "2026-04-20", "2026-05-12", "2026-05-18"],
        ),
    ],
)
def test_filter_data_for_period_returns_expected_daily_slices(period, expected_dates):
    df = pd.DataFrame(
        {
            "date": [
                "2015-01-02",
                "2020-01-02",
                "2026-01-02",
                "2026-04-20",
                "2026-05-12",
                "2026-05-18",
            ],
            "close": [50.0, 100.0, 200.0, 250.0, 290.0, 300.0],
        }
    )

    with patch.object(dashboard, "datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2026, 5, 18, 12, 0)
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        filtered = dashboard.filter_data_for_period(df, period)

    assert filtered["date"].tolist() == expected_dates


def test_calculate_intraday_period_change_uses_session_open():
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "close": [101.0, 102.0, 105.0],
        }
    )

    assert dashboard.calculate_intraday_period_change(df) == 5.0


def test_create_stock_chart_figure_uses_intraday_datetimes_for_1d():
    df = pd.DataFrame(
        {
            "datetime": [
                "2026-05-18T09:30:00-04:00",
                "2026-05-18T09:35:00-04:00",
                "2026-05-18T09:40:00-04:00",
            ],
            "open": [100.0, 101.0, 102.0],
            "close": [101.0, 102.0, 103.0],
            "volume": [1000, 1200, 1100],
        }
    )

    fig = dashboard.create_stock_chart_figure(df, "AAPL", period="1D")

    assert list(fig.data[0].x) == df["datetime"].tolist()
    assert fig.layout.xaxis2.tickformat == "%I:%M %p"
    assert fig.layout.xaxis2.type == "date"
    assert fig.data[0].hovertemplate.startswith("<b>%{x|%I:%M %p}</b>")


def test_create_stock_chart_figure_uses_tight_intraday_y_axis_range():
    df = pd.DataFrame(
        {
            "datetime": [
                "2026-05-18T09:30:00-04:00",
                "2026-05-18T10:30:00-04:00",
                "2026-05-18T11:30:00-04:00",
            ],
            "open": [300.0, 300.5, 300.2],
            "close": [300.2, 301.0, 300.6],
            "volume": [1000, 1200, 1100],
        }
    )

    fig = dashboard.create_stock_chart_figure(df, "AAPL", period="1D")

    y_range = fig.layout.yaxis.range
    assert y_range[0] > 295
    assert y_range[1] < 306


@pytest.mark.parametrize("period", ["5D", "1M", "6M", "YTD", "10Y", "MAX"])
def test_create_stock_chart_figure_uses_readable_daily_y_axis_range(period):
    df = pd.DataFrame(
        {
            "date": ["2026-05-14", "2026-05-15", "2026-05-18"],
            "low": [298.0, 299.5, 300.0],
            "high": [301.0, 302.0, 303.0],
            "close": [300.2, 301.0, 300.6],
            "volume": [1000, 1200, 1100],
        }
    )

    fig = dashboard.create_stock_chart_figure(df, "AAPL", period=period)

    y_range = fig.layout.yaxis.range
    assert y_range[0] > 290
    assert y_range[1] < 310


@pytest.mark.parametrize(
    ("period", "tickformat", "dtick"),
    [
        ("5D", "%b %-d", 86400000),
        ("1M", "%b %-d", 604800000),
        ("6M", "%b %Y", "M1"),
        ("YTD", "%b %Y", "M1"),
        ("10Y", "%Y", "M12"),
        ("MAX", "%Y", "M12"),
    ],
)
def test_create_stock_chart_figure_formats_daily_x_axis_by_period(period, tickformat, dtick):
    df = pd.DataFrame(
        {
            "date": ["2026-05-14", "2026-05-15", "2026-05-18"],
            "low": [298.0, 299.5, 300.0],
            "high": [301.0, 302.0, 303.0],
            "close": [300.2, 301.0, 300.6],
            "volume": [1000, 1200, 1100],
        }
    )

    fig = dashboard.create_stock_chart_figure(df, "AAPL", period=period)

    assert fig.layout.xaxis2.type == "date"
    assert fig.layout.xaxis2.tickformat == tickformat
    assert fig.layout.xaxis2.dtick == dtick
    assert fig.data[0].hovertemplate.startswith("<b>%{x|%b %d, %Y}</b>")


def test_create_stock_chart_figure_handles_empty_intraday_data():
    fig = dashboard.create_stock_chart_figure(pd.DataFrame(), "AAPL", period="1D")

    assert len(fig.data) == 0
    assert fig.layout.annotations[0].text == "No intraday data available for AAPL"


def test_get_intraday_stock_data_falls_back_to_previous_weekday_and_filters_regular_hours():
    today_empty = []
    previous_session = [
        _agg(
            datetime(2026, 5, 15, 9, 29, tzinfo=stock_services.EASTERN_TZ),
            99.0,
            99.0,
            99.0,
            99.0,
            100,
        ),
        _agg(
            datetime(2026, 5, 15, 9, 30, tzinfo=stock_services.EASTERN_TZ),
            100.0,
            101.0,
            99.0,
            100.5,
            1000,
        ),
        _agg(
            datetime(2026, 5, 15, 16, 0, tzinfo=stock_services.EASTERN_TZ),
            102.0,
            103.0,
            101.0,
            102.5,
            2000,
        ),
        _agg(
            datetime(2026, 5, 15, 16, 1, tzinfo=stock_services.EASTERN_TZ),
            103.0,
            103.0,
            103.0,
            103.0,
            300,
        ),
    ]

    with patch.object(stock_services, "_get_client") as get_client:
        get_client.return_value.get_aggs.side_effect = [today_empty, previous_session]
        with patch.object(stock_services, "datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(
                2026, 5, 18, 12, 0, tzinfo=stock_services.EASTERN_TZ
            )
            mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp
            mock_datetime.combine.side_effect = datetime.combine
            mock_datetime.min = datetime.min
            with patch.object(stock_services.StockCache, "get_cached_data", return_value=None):
                with patch.object(stock_services.StockCache, "set_cached_data"):
                    data = stock_services.get_intraday_stock_data(
                        "AAPL",
                        max_lookback_days=2,
                        aggregate_configs=((1, "minute"),),
                    )

    assert get_client.return_value.get_aggs.call_count == 2
    assert [record["time"] for record in data] == ["09:30", "16:00"]
    assert all(record["resolution"] == "intraday" for record in data)
    assert data[0]["date"] == "2026-05-15"


def test_get_intraday_stock_data_returns_empty_list_on_api_error():
    with patch.object(stock_services, "_get_client") as get_client:
        get_client.return_value.get_aggs.side_effect = Exception("API Error")
        with patch.object(stock_services.StockCache, "get_cached_data", return_value=None):
            data = stock_services.get_intraday_stock_data("BAD", max_lookback_days=1)

    assert data == []


def test_get_intraday_stock_data_falls_back_to_5_minute_bars_when_1_minute_unavailable():
    five_minute_session = [
        _agg(
            datetime(2026, 5, 18, 9, 30, tzinfo=stock_services.EASTERN_TZ),
            100.0,
            101.0,
            99.0,
            100.5,
            1000,
        ),
        _agg(
            datetime(2026, 5, 18, 9, 35, tzinfo=stock_services.EASTERN_TZ),
            100.5,
            102.0,
            100.0,
            101.5,
            1200,
        ),
    ]

    with patch.object(stock_services, "_get_client") as get_client:
        get_client.return_value.get_aggs.side_effect = [
            Exception("Not entitled"),
            five_minute_session,
        ]
        with patch.object(stock_services, "datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(
                2026, 5, 18, 12, 0, tzinfo=stock_services.EASTERN_TZ
            )
            mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp
            with patch.object(stock_services.StockCache, "get_cached_data", return_value=None):
                with patch.object(stock_services.StockCache, "set_cached_data"):
                    data = stock_services.get_intraday_stock_data("AAPL", max_lookback_days=1)

    assert get_client.return_value.get_aggs.call_count == 2
    assert [record["interval"] for record in data] == ["5-minute", "5-minute"]
    assert [record["time"] for record in data] == ["09:30", "09:35"]


def test_calculate_fifty_two_week_range_uses_last_year_not_full_history():
    df = pd.DataFrame(
        {
            "date": ["2015-01-02", "2020-01-02", "2025-06-01", "2026-05-15", "2026-05-18"],
            "open": [10.0, 50.0, 90.0, 100.0, 102.0],
            "high": [12.0, 55.0, 110.0, 105.0, 108.0],
            "low": [9.0, 45.0, 85.0, 98.0, 99.0],
            "close": [11.0, 52.0, 100.0, 102.0, 101.0],
        }
    )

    with patch.object(dashboard, "datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2026, 5, 18)
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        result = dashboard.calculate_fifty_two_week_range(df)

    assert result == "$85.00 - $110.00"
    assert result != "$9.00 - $110.00"


def test_period_display_label_clarifies_intraday_button():
    assert dashboard.period_display_label("1D") == "Today"
    assert dashboard.period_display_label("1Y") == "1Y"
    assert "Intraday" in dashboard.period_button_title("1D")
    assert "Daily bars" in dashboard.period_button_title("1Y")
