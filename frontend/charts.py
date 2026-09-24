"""Chart periods and the price figure.

Pure functions over OHLCV bars: which periods the loaded history can
honestly show, how each period slices it, and the Plotly figure, period
toolbar, and change readout built from the slice. Periods are measured back
from the newest bar, so a fixed dataset (the sample demo) and live data
behave the same way.
"""

from datetime import date, datetime, timedelta

import pandas as pd
import plotly.graph_objs as go
from dash import html
from plotly.subplots import make_subplots

from app.services.stock_services import EASTERN_TZ

# Figure palette only — UI chrome is styled by assets/custom.css classes.
# Gain/loss color is reserved for market data; accent is UI-interactive only.
COLORS = {
    "text": "#E8ECF4",
    "text_secondary": "#A9B2C3",
    "text_muted": "#8B97AE",
    "gain": "#2FBF71",
    "loss": "#F0544F",
    "flat": "#8B97AE",
    "accent": "#5B8DEF",
    "grid": "rgba(49, 64, 92, 0.35)",
    "spike": "rgba(121, 139, 169, 0.55)",
    "hover_bg": "rgba(18, 24, 38, 0.96)",
    "hover_border": "#31405C",
    "volume_flat": "rgba(119, 131, 155, 0.30)",
    "volume_up": "rgba(47, 191, 113, 0.35)",
    "volume_down": "rgba(240, 84, 79, 0.35)",
}

FONT_UI = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

FONT_DATA = "'IBM Plex Mono', 'SF Mono', Menlo, Consolas, monospace"

PERIODS = ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "10Y", "MAX"]

# "1D" rather than "Today": the intraday chart shows the latest regular
# session, which on weekends, holidays, before the open, and in the sample
# demo is not today. The readout names the session's date instead.
PERIOD_DISPLAY_LABELS: dict[str, str] = {}

PERIOD_LOOKBACK_DAYS = {
    "5D": 7,
    "1M": 30,
    "6M": 182,
    "1Y": 365,
    "5Y": 365 * 5,
    "10Y": 365 * 10,
}

# A period's first bar can land after the exact calendar cutoff (weekends,
# holidays) without making the period dishonest to display.
COVERAGE_TOLERANCE_DAYS = 10

PERIOD_BUTTON_TITLES = {
    "1D": "Intraday prices for the latest regular session (9:30 AM–4:00 PM ET)",
    "5D": "Daily bars for the last ~5 trading days",
    "1M": "Daily bars for the last month",
    "6M": "Daily bars for the last 6 months",
    "YTD": "Daily bars since January 1",
    "1Y": "Daily bars for the last year",
    "5Y": "Daily bars for the last 5 years",
    "10Y": "Daily bars for the last 10 years",
    "MAX": "All available daily history",
}

PERIOD_ARIA_LABELS = {
    "1D": "1 day, intraday",
    "5D": "5 days",
    "1M": "1 month",
    "6M": "6 months",
    "YTD": "Year to date",
    "1Y": "1 year",
    "5Y": "5 years",
    "10Y": "10 years",
    "MAX": "All available history",
}

GRAPH_CONFIG = {
    "displayModeBar": "hover",
    "responsive": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": [
        "lasso2d",
        "select2d",
        "autoScale2d",
        "toggleSpikelines",
        "hoverClosestCartesian",
        "hoverCompareCartesian",
    ],
}


def period_display_label(period):
    """Return the user-facing label for a chart period button."""
    return PERIOD_DISPLAY_LABELS.get(period, period)


def period_button_title(period):
    """Return hover text describing what each period button shows."""
    return PERIOD_BUTTON_TITLES.get(period, f"{period} chart")


def _period_anchor(df):
    """The day chart periods are measured back from: the newest bar.

    Anchoring to the data rather than the wall clock keeps a fixed dataset
    (the sample demo) honest — "1M" is the month ending at its last close —
    and for live data the newest bar is the latest completed session anyway.
    """
    if df is not None and not df.empty and "date" in df.columns:
        return date.fromisoformat(str(df["date"].max())[:10])
    return datetime.now().date()


def _period_cutoff(df, period):
    """First date ('YYYY-MM-DD') a daily period covers, or None for all data."""
    anchor = _period_anchor(df)
    if period == "YTD":
        return date(anchor.year, 1, 1)
    if period in PERIOD_LOOKBACK_DAYS:
        return anchor - timedelta(days=PERIOD_LOOKBACK_DAYS[period])
    return None


def filter_data_for_period(df, period):
    """Filter OHLCV dataframe to the selected time period.

    Period definitions (calendar-day based, using daily bars, measured back
    from the newest bar):
    - 1D: not used here; the chart loads dedicated intraday bars instead
    - 5D: last 7 calendar days (~5 trading days)
    - 1M: last 30 calendar days
    - 6M: last 182 calendar days
    - YTD: from January 1 of the newest bar's year
    - 1Y: last 365 calendar days
    - 5Y: last 1,825 calendar days
    - 10Y: last 3,650 calendar days
    - MAX: all available data

    Percent change formula used downstream:
        (last_close - first_close_in_range) / first_close_in_range * 100
    """
    if df.empty or period in ("1D", "MAX"):
        return df

    cutoff = _period_cutoff(df, period)
    if cutoff is None:
        return df

    filtered = df[df["date"] >= cutoff.isoformat()]
    # Degrade gracefully: if filtering yields fewer than 2 bars, show the last 2
    if len(filtered) < 2:
        return df.tail(2)
    return filtered


def data_start_date(df):
    """Earliest bar date ('YYYY-MM-DD') in the loaded history, or None."""
    if df is None or df.empty or "date" not in df.columns:
        return None
    return df["date"].min()


def format_bar_date(date_str):
    """'2024-07-17' -> 'Jul 17, 2024'."""
    try:
        day = date.fromisoformat(str(date_str)[:10])
    except (TypeError, ValueError):
        return date_str or ""
    return f"{day:%b} {day.day}, {day.year}"


def format_short_date(date_str):
    """'2024-07-17' -> 'Jul 17'."""
    try:
        day = date.fromisoformat(str(date_str)[:10])
    except (TypeError, ValueError):
        return date_str or ""
    return f"{day:%b} {day.day}"


def format_fetch_time(iso_value):
    """Provider fetch time in New York: '4:05 PM ET', with the date if not today."""
    try:
        moment = datetime.fromisoformat(iso_value).astimezone(EASTERN_TZ)
    except (TypeError, ValueError):
        return None
    clock = f"{moment:%I:%M %p}".lstrip("0")
    today = datetime.now(EASTERN_TZ).date()
    if moment.date() != today:
        return f"{format_short_date(moment.date().isoformat())}, {clock} ET"
    return f"{clock} ET"


def is_period_available(df, period):
    """True when the loaded history reaches back far enough to honestly show `period`.

    1D always applies (it uses separate intraday data) and MAX always applies
    (it means "all available history" by definition). Window periods require
    bars at/before their calendar cutoff; without that, the chart would silently
    render the same truncated range as a shorter period.
    """
    start = data_start_date(df)
    if start is None or period in ("1D", "MAX"):
        return True

    cutoff = _period_cutoff(df, period)
    if cutoff is None:
        return True

    tolerant_cutoff = (cutoff + timedelta(days=COVERAGE_TOLERANCE_DAYS)).isoformat()
    return start <= tolerant_cutoff


def initial_chart_period(df):
    """Default chart period: 1Y, or MAX when history is shorter than a year."""
    return "1Y" if is_period_available(df, "1Y") else "MAX"


def calculate_period_change(df):
    """(last_close - first_close) / first_close * 100 over the filtered range."""
    if df.empty or len(df) < 1:
        return 0.0
    first_close = df["close"].iloc[0]
    last_close = df["close"].iloc[-1]
    if first_close == 0:
        return 0.0
    return ((last_close - first_close) / first_close) * 100


def calculate_fifty_two_week_range(df):
    """Return formatted 52-week low/high from the last year of daily bars."""
    filtered = filter_data_for_period(df, "1Y")
    if filtered.empty or "close" not in filtered.columns:
        return "N/A"

    if "low" in filtered.columns and "high" in filtered.columns:
        low = filtered["low"].min()
        high = filtered["high"].max()
    else:
        low = filtered["close"].min()
        high = filtered["close"].max()

    return f"${low:.2f} - ${high:.2f}"


def calculate_intraday_period_change(df):
    """Return regular-session 1D performance from first bar open to latest close."""
    if df.empty or len(df) < 1 or "open" not in df.columns or "close" not in df.columns:
        return 0.0
    session_open = df["open"].iloc[0]
    latest_close = df["close"].iloc[-1]
    if session_open == 0:
        return 0.0
    return ((latest_close - session_open) / session_open) * 100


def period_price_change(df, is_intraday=False):
    """Return (absolute $ change, % change) over the filtered range.

    Daily ranges compare first close to last close; intraday compares the
    session open to the latest close (same base as calculate_intraday_period_change).
    """
    if df.empty or "close" not in df.columns:
        return 0.0, 0.0
    if is_intraday:
        if "open" not in df.columns:
            return 0.0, 0.0
        base = df["open"].iloc[0]
    else:
        base = df["close"].iloc[0]
    last = df["close"].iloc[-1]
    if base == 0:
        return 0.0, 0.0
    return last - base, ((last - base) / base) * 100


def _price_axis_range(df):
    """Return a padded price range so chart movement is readable."""
    price_columns = [col for col in ["low", "high", "close"] if col in df.columns]
    if not price_columns:
        return None

    prices = pd.concat([pd.to_numeric(df[col], errors="coerce") for col in price_columns]).dropna()
    if prices.empty:
        return None

    min_price = prices.min()
    max_price = prices.max()
    price_span = max_price - min_price
    if price_span == 0:
        padding = max(abs(max_price) * 0.005, 0.5)
    else:
        padding = max(price_span * 0.15, 0.25)
    lower_bound = min_price - padding
    if min_price > 0:
        lower_bound = max(lower_bound, min_price * 0.9)
    return [lower_bound, max_price + padding]


def _price_tick_format(price_range):
    """Use cents for tight ranges and whole dollars for wider ranges."""
    if not price_range:
        return ",.0f"
    return ",.2f" if (price_range[1] - price_range[0]) < 20 else ",.0f"


def _date_axis_tick_format(period, span_days=None):
    """Return a readable date tick format for each daily chart period."""
    if period in ("5D", "1M"):
        return "%b %-d"
    if period in ("5Y", "10Y", "MAX"):
        return "%Y"
    if span_days and span_days > 200:
        # Paired with every-other-month ticks: the year on a second line
        # keeps labels narrow enough to sit level on a phone
        return "%b\n%Y"
    return "%b %Y"


def _date_axis_tick_spacing(period, span_days=None):
    """Return a stable date tick spacing for each daily chart period.

    Month-labelled ranges longer than ~6.5 months (1Y, and YTD late in the
    year) step every other month, so a phone-width chart gets six level labels
    instead of twelve slanted ones. Very long histories step five years.
    """
    if period == "5D":
        return 24 * 60 * 60 * 1000
    if period == "1M":
        return 7 * 24 * 60 * 60 * 1000
    if period in ("5Y", "10Y", "MAX"):
        return "M60" if span_days and span_days > 365 * 12 else "M12"
    if span_days and span_days > 200:
        return "M2"
    return "M1"


def _span_days(df):
    if df.empty or "date" not in df.columns:
        return None
    try:
        first = date.fromisoformat(str(df["date"].min())[:10])
        last = date.fromisoformat(str(df["date"].max())[:10])
    except ValueError:
        return None
    return (last - first).days


def _hex_to_rgba(hex_color, alpha):
    """'#RRGGBB' -> 'rgba(r, g, b, a)'."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def _direction_color(df, is_intraday):
    """Gain green when the period is up, loss red when down, muted when flat."""
    abs_change, _ = period_price_change(df, is_intraday=is_intraday)
    if abs_change > 0:
        return COLORS["gain"]
    if abs_change < 0:
        return COLORS["loss"]
    return COLORS["flat"]


def _base_layout():
    # No fixed height: the graph fills its container, whose height the
    # stylesheet sets per breakpoint so details stay within reach below it.
    return dict(
        title=None,
        template="plotly_dark",
        margin=dict(l=10, r=55, t=10, b=25),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLORS["text"], family=FONT_UI),
        autosize=True,
        showlegend=False,
    )


def blank_figure():
    """Placeholder figure for the graph before any symbol has loaded."""
    fig = go.Figure()
    fig.update_layout(**_base_layout())
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def create_stock_chart_figure(df, symbol, period=None):
    """Price line + gradient band (top) and volume bars (bottom), shared x-axis.

    The line, gradient, and volume tints take the period's gain/loss color so
    the chart itself reads direction. Y-axes sit on the right; the custom Dash
    period buttons are the sole period control (no Plotly rangeselector).
    """
    is_intraday = period == "1D"

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.85, 0.15],
    )

    if df.empty:
        message = (
            f"No intraday data available for {symbol}"
            if is_intraday
            else f"No chart data available for {symbol}"
        )
        fig.add_annotation(
            text=message,
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=14, color=COLORS["text_muted"]),
        )
        fig.update_layout(**_base_layout())
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return fig

    x_col = "datetime" if is_intraday and "datetime" in df.columns else "date"
    price_hovertemplate = (
        "<b>%{x|%I:%M %p}</b><br>$%{y:.2f}<extra></extra>"
        if is_intraday
        else "<b>%{x|%b %d, %Y}</b><br>$%{y:.2f}<extra></extra>"
    )

    line_color = _direction_color(df, is_intraday)
    price_range = _price_axis_range(df)

    # --- price line (kept as fig.data[0]) ---
    fig.add_trace(
        go.Scatter(
            x=df[x_col],
            y=df["close"],
            mode="lines",
            line=dict(color=line_color, width=2, shape="spline"),
            name="Price",
            hovertemplate=price_hovertemplate,
        ),
        row=1,
        col=1,
    )

    # --- gradient band between the visible lower bound and the price line ---
    # Plotly's fill gradient spans the fill's bounding box, so an invisible
    # baseline at the clamped axis floor keeps the fade inside the visible band
    # instead of stretching down to zero.
    if len(df) >= 2:
        baseline_y = price_range[0] if price_range else float(df["close"].min())
        fig.add_trace(
            go.Scatter(
                x=df[x_col],
                y=[baseline_y] * len(df),
                mode="lines",
                line=dict(width=0),
                hoverinfo="skip",
                showlegend=False,
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df[x_col],
                y=df["close"],
                mode="lines",
                line=dict(width=0, shape="spline"),
                fill="tonexty",
                fillgradient=dict(
                    type="vertical",
                    colorscale=[
                        [0.0, _hex_to_rgba(line_color, 0.0)],
                        [1.0, _hex_to_rgba(line_color, 0.22)],
                    ],
                ),
                hoverinfo="skip",
                showlegend=False,
            ),
            row=1,
            col=1,
        )

    # --- volume bars (subtle, no axis labels) ---
    if "volume" in df.columns and df["volume"].notna().any():
        colors = [
            COLORS["volume_flat"]
            if i == 0
            else COLORS["volume_up"]
            if df["close"].iloc[i] >= df["close"].iloc[i - 1]
            else COLORS["volume_down"]
            for i in range(len(df))
        ]

        fig.add_trace(
            go.Bar(
                x=df[x_col],
                y=df["volume"],
                marker_color=colors,
                name="Volume",
                hovertemplate=(
                    "<b>%{x|%I:%M %p}</b><br>Vol: %{y:,.0f}<extra></extra>"
                    if is_intraday
                    else "Vol: %{y:,.0f}<extra></extra>"
                ),
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        **_base_layout(),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=COLORS["hover_bg"],
            font_size=13,
            font_family=FONT_DATA,
            bordercolor=COLORS["hover_border"],
            font_color=COLORS["text"],
        ),
        bargap=0.3,
    )

    price_yaxis_options = dict(
        showgrid=True,
        gridwidth=1,
        gridcolor=COLORS["grid"],
        showline=False,
        tickfont=dict(size=11, color=COLORS["text_muted"], family=FONT_DATA),
        tickprefix="$",
        tickformat=",.0f",
        side="right",
        row=1,
        col=1,
    )
    if price_range:
        price_yaxis_options.update(range=price_range, tickformat=_price_tick_format(price_range))
    # price y-axis (right)
    fig.update_yaxes(**price_yaxis_options)
    # volume y-axis — hidden tick labels, just the bars for visual context
    fig.update_yaxes(
        showgrid=False,
        showline=False,
        showticklabels=False,
        row=2,
        col=1,
    )

    spike_options = dict(
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikethickness=1,
        spikedash="dot",
        spikecolor=COLORS["spike"],
    )
    # price x-axis — hide ticks (shared with volume below), crosshair spike on
    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor=COLORS["grid"],
        showline=False,
        showticklabels=False,
        row=1,
        col=1,
        **spike_options,
    )
    # volume x-axis — show date ticks here only
    xaxis_options = dict(
        showgrid=False,
        showline=False,
        tickfont=dict(size=10, color=COLORS["text_muted"], family=FONT_DATA),
        row=2,
        col=1,
        **spike_options,
    )
    if is_intraday:
        xaxis_options.update(type="date", tickformat="%I:%M %p")
    else:
        xaxis_options.update(
            type="date",
            tickformat=_date_axis_tick_format(period, _span_days(df)),
            dtick=_date_axis_tick_spacing(period, _span_days(df)),
        )
    fig.update_xaxes(**xaxis_options)

    return fig


def _period_btn_class(is_active):
    """Return the CSS class string for a period button."""
    return "period-btn period-btn--active" if is_active else "period-btn"


def build_period_toolbar(active_period, df=None):
    """Build the segmented period-selector control.

    Periods reaching further back than the loaded history are disabled with a
    tooltip naming the first available bar, instead of silently rendering the
    same truncated chart as shorter periods.
    """
    start = data_start_date(df)
    buttons = []
    for period in PERIODS:
        available = is_period_available(df, period)
        title = (
            period_button_title(period)
            if available
            else f"Unavailable — price history begins {format_bar_date(start)}"
        )
        buttons.append(
            html.Button(
                period_display_label(period),
                id={"type": "period-btn", "index": period},
                n_clicks=0,
                type="button",
                title=title,
                disabled=not available,
                className=_period_btn_class(period == active_period),
                **{
                    "aria-pressed": "true" if period == active_period else "false",
                    "aria-label": PERIOD_ARIA_LABELS.get(period, period),
                },
            )
        )
    return html.Div(buttons, className="period-seg", role="group", **{"aria-label": "Chart period"})


def _change_chip(change, change_pct, small=False, money=True):
    """Direction-colored change chip; None renders as unavailable, never zero."""
    size = " change-chip--sm" if small else ""
    if change is None or change_pct is None:
        return html.Span(
            "Change unavailable",
            className=f"change-chip{size} change-chip--na",
            title="The prior session's close isn't available",
        )
    if change > 0:
        chip_class, arrow = f"change-chip{size} change-chip--up", "▲"
    elif change < 0:
        chip_class, arrow = f"change-chip{size} change-chip--down", "▼"
    else:
        chip_class, arrow = f"change-chip{size} change-chip--flat", ""
    if money:
        sign = "+" if change > 0 else "-" if change < 0 else ""
        label = f"{sign}${abs(change):,.2f} ({change_pct:+.2f}%)"
    else:
        label = f"{change:+.2f} ({change_pct:+.2f}%)"
    arrow_children = [html.Span(arrow, className="chip-arrow", **{"aria-hidden": "true"})]
    return html.Span((arrow_children if arrow else []) + [label], className=chip_class)


def build_change_readout(abs_change, pct_change, period, since_date=None, session_date=None):
    """Chip + period tag shown next to the price, colored by direction.

    For MAX, the tag shows the actual start of the available history
    ("Since Jul 17, 2024") so a plan-limited or recently listed dataset
    doesn't masquerade as all-time performance. For 1D it names the session
    the intraday bars belong to. A change of None (no bars) reads as
    unavailable rather than as a flat 0.00%.
    """
    if period == "MAX" and since_date:
        period_label = f"Since {format_bar_date(since_date)}"
    elif period == "1D" and session_date:
        period_label = f"{format_short_date(session_date)} session"
    else:
        period_label = period_display_label(period)

    return [
        _change_chip(abs_change, pct_change),
        html.Span(period_label, className="readout-period"),
    ]


def chart_for_period(symbol, period, history_df, intraday_records=None):
    """(figure, readout) for one period from already-loaded bars."""
    if period == "1D":
        frame = pd.DataFrame(intraday_records or [])
        session = frame["date"].iloc[-1] if not frame.empty and "date" in frame else None
        if frame.empty:
            readout = build_change_readout(None, None, "1D")
        else:
            abs_change, pct_change = period_price_change(frame, is_intraday=True)
            readout = build_change_readout(abs_change, pct_change, "1D", session_date=session)
    else:
        frame = filter_data_for_period(history_df, period)
        abs_change, pct_change = period_price_change(frame)
        readout = build_change_readout(
            abs_change, pct_change, period, since_date=data_start_date(history_df)
        )
    return create_stock_chart_figure(frame, symbol, period=period), readout
