"""The stock view: chart card header, price, and details for one symbol.

Every price shown for a stock — the chart header, the details card, and (via
the watchlist) its row — comes from one Quote. When no quote is available
the last bar of the price history stands in, labelled as such.
"""

import logging
from dataclasses import dataclass

import pandas as pd
from dash import html
from dash.exceptions import PreventUpdate

from frontend.charts import (
    PERIODS,
    _change_chip,
    _period_btn_class,
    blank_figure,
    build_period_toolbar,
    calculate_fifty_two_week_range,
    chart_for_period,
    format_bar_date,
    format_fetch_time,
    initial_chart_period,
    is_period_available,
)
from frontend.shell import empty_state

logger = logging.getLogger(__name__)


ABOUT_TEXT_COLLAPSED_CLASS = "about-text about-text--collapsed"

ABOUT_TEXT_EXPANDED_CLASS = "about-text about-text--expanded"

DEMO_DEFAULT_SYMBOL = "AAPL"
# Pattern-matching id: the button exists only while a failure is showing, and
# Dash rejects plain-id inputs that are missing from the page.
RETRY_SEARCH_ID = {"type": "retry-search", "index": 0}


@dataclass
class DisplayQuote:
    """The one price a stock view shows, and where it came from.

    origin is "quote" (provider close), "sample" (demo data), or "history"
    (the last bar of the price history, used only when no quote is available
    and always labelled as such).
    """

    price: float
    session_date: str | None
    prev_close: float | None
    change: float | None
    change_pct: float | None
    fetched_at: str | None
    origin: str


def resolve_display_quote(quote, last_bar=None, prev_bar=None, is_sample=False):
    if quote is not None:
        return DisplayQuote(
            price=quote.price,
            session_date=quote.session_date,
            prev_close=quote.prev_close,
            change=quote.change,
            change_pct=quote.change_pct,
            fetched_at=quote.fetched_at,
            origin="sample" if is_sample else "quote",
        )
    if not last_bar:
        return None
    price = last_bar["close"]
    prev_close = prev_bar["close"] if prev_bar else None
    change = change_pct = None
    if prev_close:
        change = price - prev_close
        change_pct = change / prev_close * 100
    return DisplayQuote(
        price=price,
        session_date=last_bar.get("date"),
        prev_close=prev_close,
        change=change,
        change_pct=change_pct,
        fetched_at=None,
        origin="history",
    )


def build_quote_price(display):
    if display is None:
        return html.Span("—", className="price-lg price-lg--empty")
    return html.Span(f"${display.price:,.2f}", className="price-lg")


def build_quote_caption(display):
    """Which close the price is, and when it was retrieved. Never "live"."""
    if display is None:
        return html.Span("Price unavailable", className="caption-warn")
    when = format_bar_date(display.session_date) if display.session_date else "date unknown"
    if display.origin == "sample":
        return [html.Span("Sample close"), " · ", html.Span(when)]
    if display.origin == "history":
        return [
            html.Span("Last close in price history"),
            " · ",
            html.Span(when),
            " · ",
            html.Span("Quote unavailable", className="caption-warn"),
        ]
    parts = [html.Span("Close"), " · ", html.Span(when)]
    fetched = format_fetch_time(display.fetched_at)
    if fetched:
        parts += [" · ", html.Span(f"retrieved {fetched}", className="caption-muted")]
    return parts


def _stat_cell(label, value_children, large=False, title=None):
    value_class = "stat-value stat-value--lg" if large else "stat-value"
    return html.Div(
        [
            html.Div(label, className="stat-label"),
            html.Div(value_children, className=value_class, title=title),
        ],
        className="stat-cell",
    )


def build_quote_stats(display):
    """Last close + day change and previous close, from the same quote as the header."""
    if display is None:
        return [
            _stat_cell("Last close", "—", large=True),
            _stat_cell("Previous close", "—"),
        ]
    label = "Last close (price history)" if display.origin == "history" else "Last close"
    return [
        _stat_cell(
            label,
            [
                html.Span(f"${display.price:,.2f}", className="stat-price"),
                _change_chip(display.change, display.change_pct, small=True, money=False),
            ],
            large=True,
        ),
        _stat_cell(
            "Previous close",
            f"${display.prev_close:,.2f}" if display.prev_close else "—",
            title=None if display.prev_close else "The prior session's close isn't available",
        ),
    ]


def _format_market_cap(market_cap):
    """Compact terminal-style market cap: $3.45T / $12.30B / $450.00M."""
    if not isinstance(market_cap, (int, float)) or market_cap <= 0:
        return "N/A"
    if market_cap >= 1e12:
        return f"${market_cap / 1e12:,.2f}T"
    if market_cap >= 1e9:
        return f"${market_cap / 1e9:,.2f}B"
    if market_cap >= 1e6:
        return f"${market_cap / 1e6:,.2f}M"
    return f"${market_cap:,.2f}"


def build_profile_stats(details, df, is_sample=False):
    details = details or {}
    website = details.get("website")
    website_value = (
        html.A(
            website.replace("https://", "").replace("http://", ""),
            href=website,
            target="_blank",
            rel="noopener noreferrer",
        )
        if website
        else "N/A"
    )
    market_cap = _format_market_cap(details.get("market_cap"))
    return [
        _stat_cell("52-week range", calculate_fifty_two_week_range(df)),
        _stat_cell(
            "Market cap",
            market_cap,
            title="Sample price × shares outstanding" if is_sample else None,
        ),
        _stat_cell("Exchange", details.get("exchange") or "N/A"),
        _stat_cell("Website", website_value),
    ]


def about_display_state(expanded=False):
    """Return render properties for the About description's current visibility."""
    if expanded:
        return ABOUT_TEXT_EXPANDED_CLASS, "Show less", "true"
    return ABOUT_TEXT_COLLAPSED_CLASS, "Show full description", "false"


def create_about_section(stock_symbol, description):
    """Render a two-line About preview with an accessible expand/collapse control."""
    text_class, toggle_label, aria_expanded = about_display_state()
    return html.Div(
        [
            html.H3("About", className="panel-title"),
            html.P(
                description,
                id={"type": "about-text", "index": stock_symbol},
                className=text_class,
            ),
            html.Button(
                toggle_label,
                id={"type": "about-toggle", "index": stock_symbol},
                className="about-toggle",
                n_clicks=0,
                type="button",
                **{"aria-expanded": aria_expanded},
            ),
        ],
        className="about-section",
    )


def build_stock_identity(symbol, company_name, logo_src):
    logo_content = (
        html.Img(src=logo_src, alt="")
        if logo_src
        else html.Span(symbol[0].upper(), className="logo-monogram", **{"aria-hidden": "true"})
    )
    return html.Div(
        [
            html.Div(logo_content, className="logo-frame"),
            html.Div(
                [
                    html.H2(symbol, className="chart-symbol"),
                    html.P(company_name, className="chart-company-name", title=company_name),
                ],
                className="chart-title-text",
            ),
        ],
        className="chart-title-group",
    )


@dataclass
class StockView:
    """Everything the page shows for one symbol, ready for the outputs."""

    symbol: str
    period: str
    identity: object
    price: object
    caption: object
    readout: object
    toolbar: object
    figure: object
    quote_stats: list
    profile_stats: list
    about: object
    meta: dict


def load_stock_view(source, symbol, period=None):
    """Build the stock view, or None when no price history came back."""
    history = source.history(symbol)
    df = pd.DataFrame(history)
    if df.empty or "close" not in df.columns or "date" not in df.columns:
        return None

    if period not in PERIODS or not is_period_available(df, period):
        period = initial_chart_period(df)
    intraday = source.intraday(symbol) if period == "1D" else None
    figure, readout = chart_for_period(symbol, period, df, intraday)

    details = source.details(symbol)
    company_name = (details or {}).get("name") or symbol
    quote = source.quote_batch([symbol]).quotes.get(symbol)
    last_bar = history[-1]
    prev_bar = history[-2] if len(history) > 1 else None
    display = resolve_display_quote(quote, last_bar, prev_bar, source.is_sample)
    description = (details or {}).get("description") or ""

    return StockView(
        symbol=symbol,
        period=period,
        identity=build_stock_identity(symbol, company_name, source.logo_src(symbol, details)),
        price=build_quote_price(display),
        caption=build_quote_caption(display),
        readout=readout,
        toolbar=build_period_toolbar(period, df=df),
        figure=figure,
        quote_stats=build_quote_stats(display),
        profile_stats=build_profile_stats(details, df, is_sample=source.is_sample),
        about=create_about_section(symbol, description) if description else None,
        # Small by design: refreshes re-derive the history fallback from this
        # rather than shipping the whole price history back and forth.
        meta={
            "symbol": symbol,
            "last_bar": {"date": last_bar["date"], "close": last_bar["close"]},
            "prev_bar": {"date": prev_bar["date"], "close": prev_bar["close"]}
            if prev_bar
            else None,
        },
    )


def _clean_symbol(raw):
    if not isinstance(raw, str):
        return None
    symbol = raw.strip().upper()
    if not symbol or len(symbol) > 10 or not symbol.replace(".", "").isalnum():
        return None
    return symbol


def search_error(message, retry=False):
    children = [html.Span("⚠", className="status-icon", **{"aria-hidden": "true"}), message]
    if retry:
        children.append(
            html.Button(
                "Retry",
                id=RETRY_SEARCH_ID,
                n_clicks=0,
                type="button",
                className="link-btn",
            )
        )
    return html.Div(children, className="status-line status-line--error")


def default_symbol(source):
    """What to show when nothing was saved: AAPL in the demo, otherwise the
    first ticker of the first watchlist (or nothing, for a new account)."""
    if source.is_sample:
        return DEMO_DEFAULT_SYMBOL
    for watchlist in source.watchlists():
        if watchlist.stocks:
            return watchlist.stocks[0].symbol
    return None


def _requested_symbol(source, trigger, value, typed, restore):
    """(symbol, origin) for a load request, or (None, None) to ignore it."""
    if trigger in ("search-button", "stock-input"):
        if not value:
            return None, None
        symbol = typed.strip().upper() if isinstance(typed, str) and typed.strip() else None
        return symbol, "search"
    if trigger == "restore-request":
        # Saved state is client-controlled: anything that isn't a symbol this
        # source can show falls back to the default view, without an error.
        saved = _clean_symbol((restore or {}).get("symbol"))
        if saved and source.search_symbols is not None and saved not in source.search_symbols:
            saved = None
        return (saved or default_symbol(source)), "restore"
    if trigger == "symbol-request" and isinstance(value, dict) and value.get("symbol"):
        return value["symbol"], value.get("origin") or "click"
    return None, None


def _empty_view(source):
    values = {
        "stock-header.children": None,
        "stock-quote-price.children": None,
        "stock-quote-caption.children": None,
        "chart-change-readout.children": None,
        "period-toolbar.children": None,
        "stock-chart.figure": blank_figure(),
        "stock-quote-stats.children": [],
        "stock-profile-stats.children": [],
        "stock-about.children": empty_state(
            "\U0001f50d", "No stock selected", "Company details appear here."
        ),
        "chart-card.className": "sw-card chart-card chart-card--empty",
    }
    if not source.read_only:
        values["add-to-watchlist.disabled"] = True
    return values


def handle_stock_request(source, trigger, value, typed=None, period=None, shown=None, restore=None):
    """Outputs for a request to show a symbol, as {"id.prop": value}.

    A symbol that can't be loaded leaves the current chart exactly as it was
    — still labelled with its own symbol — and explains the failure next to
    the search box, with a retry where retrying could help.
    """
    symbol, origin = _requested_symbol(source, trigger, value, typed, restore)
    if origin is None:
        raise PreventUpdate
    if origin == "restore":
        saved_period = (restore or {}).get("period")
        period = saved_period if saved_period in PERIODS else None
    if symbol is None:
        return _empty_view(source) if origin == "restore" else {}

    keep_note = f" Still showing {shown}." if shown and shown != symbol else ""
    clean = _clean_symbol(symbol)
    if clean is None:
        return {
            "search-status.children": search_error(
                f"“{symbol[:12]}” isn't a ticker symbol.{keep_note}"
            ),
            "stock-input.invalid": True,
        }
    symbol = clean

    if source.search_symbols is not None and symbol not in source.search_symbols:
        sample = ", ".join(source.search_symbols)
        values = {
            "search-status.children": search_error(
                f"{symbol} isn't in the sample data. Try {sample} — or create an account "
                f"to search any ticker.{keep_note}"
            ),
            "stock-input.invalid": True,
        }
        if origin == "restore":
            values.update(_empty_view(source))
        return values

    try:
        view = load_stock_view(source, symbol, period)
    except Exception:
        logger.exception("Failed to load %s", symbol)
        view = None

    if view is None:
        values = {
            "search-status.children": search_error(
                f"Couldn't load {symbol}: no price history came back. Check the symbol, or "
                f"try again in a moment — the data provider may be busy.{keep_note}",
                retry=True,
            ),
            "failed-search.data": symbol,
            "stock-input.invalid": origin == "search",
        }
        if not shown:
            values.update(_empty_view(source))
        return values

    values = {
        "stock-header.children": view.identity,
        "stock-quote-price.children": view.price,
        "stock-quote-caption.children": view.caption,
        "chart-change-readout.children": view.readout,
        "period-toolbar.children": view.toolbar,
        "stock-chart.figure": view.figure,
        "stock-quote-stats.children": view.quote_stats,
        "stock-profile-stats.children": view.profile_stats,
        "stock-about.children": view.about,
        "chart-card.className": "sw-card chart-card",
        "stock-symbol-store.data": view.symbol,
        "chart-period-store.data": view.period,
        "stock-meta.data": view.meta,
        "search-status.children": None,
        "failed-search.data": None,
        "stock-input.invalid": False,
    }
    if origin == "search":
        values["stock-input.value"] = symbol
    if not source.read_only:
        values["add-to-watchlist.disabled"] = False
    return values


def change_period(source, symbol, period, btn_ids):
    """Outputs for a period click. History is re-read server-side (cached),
    never round-tripped through the browser."""
    if period not in PERIODS:
        raise PreventUpdate
    df = pd.DataFrame(source.history(symbol))
    if df.empty or "close" not in df.columns:
        raise PreventUpdate
    intraday = source.intraday(symbol) if period == "1D" else None
    figure, readout = chart_for_period(symbol, period, df, intraday)
    classes = [_period_btn_class(b["index"] == period) for b in btn_ids]
    pressed = ["true" if b["index"] == period else "false" for b in btn_ids]
    return figure, classes, pressed, readout, period
