"""The watchlist card: rows, price status, and in-place refreshes."""

from dash import html, no_update
from dash.exceptions import PreventUpdate

from frontend.charts import format_bar_date, format_fetch_time, format_short_date
from frontend.shell import empty_state
from frontend.stock_view import (
    build_quote_caption,
    build_quote_price,
    build_quote_stats,
    resolve_display_quote,
)

# Shown only after a failed refresh; see RETRY_SEARCH_ID in stock_view.
RETRY_PRICES_ID = {"type": "retry-prices", "index": 0}


def _majority_session(quotes):
    dates = [q.session_date for q in quotes if q is not None and q.session_date]
    return max(set(dates), key=dates.count) if dates else None


def _watchlist_quote_cell(quote, list_session=None):
    """Price and day change for one watchlist row.

    A missing quote renders as an em dash: showing $0.00 for a symbol whose
    price could not be fetched would read as a real, catastrophic price. A row
    whose close is from a different session than the rest is dated.
    """
    if quote is None:
        return html.Span(
            "—",
            className="watchlist-price watchlist-price--empty",
            title="Price unavailable",
        )

    children = [html.Span(f"${quote.price:,.2f}", className="watchlist-price")]

    # change is None when the prior session was unavailable — omit the chip
    # entirely rather than implying the stock was flat.
    if quote.change is not None and quote.change_pct is not None:
        if quote.change > 0:
            chip_class, arrow = "change-chip change-chip--sm change-chip--up", "▲"
        elif quote.change < 0:
            chip_class, arrow = "change-chip change-chip--sm change-chip--down", "▼"
        else:
            chip_class, arrow = "change-chip change-chip--sm change-chip--flat", ""

        children.append(
            html.Span(
                (
                    [html.Span(arrow, className="chip-arrow", **{"aria-hidden": "true"})]
                    if arrow
                    else []
                )
                + [f"{quote.change:+.2f} ({quote.change_pct:+.2f}%)"],
                className=chip_class,
            )
        )

    if list_session and quote.session_date and quote.session_date != list_session:
        children.append(
            html.Span(
                format_short_date(quote.session_date),
                className="row-date",
                title=f"Close from {format_bar_date(quote.session_date)}",
            )
        )

    return children


def _ticker_class(symbol, active_symbol):
    active = symbol == active_symbol
    return "watchlist-select watchlist-select--active" if active else "watchlist-select"


def create_watchlist_content(watchlist, quotes, active_symbol=None, editable=True):
    """Rows for one watchlist. Each row's ticker is the selection control."""
    stocks = list(watchlist.stocks)
    list_session = _majority_session([quotes.get(s.symbol) for s in stocks])

    rows = []
    for stock in stocks:
        name = stock.name or ""
        row = [
            html.Button(
                [
                    html.Span(
                        [
                            html.Span(stock.symbol, className="watchlist-ticker"),
                            html.Span(name, className="watchlist-company", title=name),
                        ],
                        className="watchlist-row-info",
                    ),
                    html.Span(
                        _watchlist_quote_cell(quotes.get(stock.symbol), list_session),
                        id={"type": "watchlist-quote", "index": stock.symbol},
                        className="watchlist-row-quote",
                    ),
                ],
                id={"type": "load-watchlist-stock", "index": stock.symbol},
                n_clicks=0,
                type="button",
                className=_ticker_class(stock.symbol, active_symbol),
                title=f"Show {stock.symbol} chart",
                **{"aria-current": "true" if stock.symbol == active_symbol else "false"},
            )
        ]
        if editable:
            row.append(
                html.Button(
                    "×",
                    id={"type": "remove-from-watchlist", "index": stock.id},
                    n_clicks=0,
                    type="button",
                    className="row-remove",
                    title=f"Remove {stock.symbol}",
                    **{"aria-label": f"Remove {stock.symbol} from {watchlist.name}"},
                )
            )
        rows.append(html.Li(row, className="watchlist-row"))

    header = [html.H3(watchlist.name, className="watchlist-name", title=watchlist.name)]
    if editable:
        header.append(
            html.Button(
                "Delete list",
                id={"type": "delete-watchlist", "index": watchlist.id},
                n_clicks=0,
                type="button",
                className="btn sw-btn--danger sw-btn--sm",
                **{"aria-label": f"Delete watchlist {watchlist.name}"},
            )
        )

    body = (
        html.Ul(rows, className="watchlist-rows")
        if rows
        else empty_state(
            "\U0001f4ca",
            "No stocks added yet",
            "Search for a ticker, then use ＋ Watchlist to add it here.",
        )
    )
    return html.Div(
        [html.Div(header, className="watchlist-panel-header"), body],
        className="watchlist-panel",
    )


def watchlist_empty_state(editable):
    if not editable:
        return empty_state("★", "No watchlist to show")
    return empty_state(
        "\U0001f4cb",
        "No watchlists yet",
        "Create one to keep an eye on the tickers you follow.",
        action=html.Button(
            "Create a watchlist",
            id={"type": "open-create-watchlist", "index": 0},
            n_clicks=0,
            type="button",
            className="btn sw-btn--primary sw-btn--sm",
        ),
    )


def watchlist_options(watchlists):
    return [{"label": w.name, "value": w.id} for w in watchlists]


def _oldest_fetch(quotes):
    stamps = [q.fetched_at for q in quotes if q is not None and q.fetched_at]
    return min(stamps) if stamps else None


def market_status(quotes, is_sample):
    """One line under the watchlist: which session's closes, retrieved when."""
    quotes = [q for q in quotes if q is not None]
    if not quotes:
        return None
    session = _majority_session(quotes)
    when = format_bar_date(session) if session else "unknown date"
    if is_sample:
        return f"Sample closes · {when}"
    text = f"Closes · {when}"
    fetched = format_fetch_time(_oldest_fetch(quotes))
    return f"{text} · retrieved {fetched}" if fetched else text


def failed_refresh_status(last_ok_fetched=None, first_load=False):
    """Refresh failed: say so, say what's still on screen, offer a retry."""
    if first_load:
        message = "Couldn't load prices."
    else:
        message = "Couldn't refresh prices."
        fetched = format_fetch_time(last_ok_fetched)
        if fetched:
            message += f" Showing prices retrieved {fetched}."
        else:
            message += " Showing the last prices loaded."
    return html.Div(
        [
            html.Span("⚠", className="status-icon", **{"aria-hidden": "true"}),
            html.Span(message),
            html.Button(
                "Retry", id=RETRY_PRICES_ID, n_clicks=0, type="button", className="link-btn"
            ),
        ],
        className="status-line status-line--error",
    )


def choose_watchlist(source, saved_id):
    """The saved watchlist if it still exists and is the user's; else the first."""
    if saved_id is not None and source.watchlist(saved_id) is not None:
        return source.watchlist(saved_id).id
    watchlists = source.watchlists()
    return watchlists[0].id if watchlists else None


def render_watchlist_section(source, watchlist_id, active_symbol):
    """(section, status, meta) for the selected watchlist."""
    editable = not source.read_only
    watchlist = source.watchlist(watchlist_id) if watchlist_id is not None else None
    if watchlist is None:
        if source.watchlists():
            return (
                empty_state("★", "No watchlist selected", "Pick one from the list above."),
                None,
                None,
            )
        return watchlist_empty_state(editable), None, None

    symbols = [s.symbol for s in watchlist.stocks]
    batch = source.quote_batch(symbols) if symbols else None
    quotes = batch.quotes if batch else {}
    content = create_watchlist_content(watchlist, quotes, active_symbol, editable)
    if batch is not None and batch.failed:
        return content, failed_refresh_status(first_load=True), {"ok": False}
    ordered = [quotes.get(s) for s in symbols]
    return (
        content,
        market_status(ordered, source.is_sample),
        {"ok": True, "fetched_at": _oldest_fetch(ordered)},
    )


def refresh_market(source, row_symbols, stock_meta, meta):
    """Re-price the watchlist rows and the stock view from one quote batch.

    Rows and the stock header are updated in place (focus survives). If the
    provider fails, everything on screen stays exactly as it was and the
    status line offers a retry.
    """
    active = (stock_meta or {}).get("symbol")
    wanted = list(row_symbols) + ([active] if active and active not in row_symbols else [])
    if not wanted:
        raise PreventUpdate

    batch = source.quote_batch(wanted)
    if batch.failed:
        status = failed_refresh_status((meta or {}).get("fetched_at"))
        return (
            [no_update] * len(row_symbols),
            no_update,
            no_update,
            no_update,
            status,
            {**(meta or {}), "ok": False},
        )

    row_quotes = [batch.quotes.get(s) for s in row_symbols]
    list_session = _majority_session(row_quotes)
    cells = [_watchlist_quote_cell(q, list_session) for q in row_quotes]

    price = caption = stats = no_update
    if active:
        display = resolve_display_quote(
            batch.quotes.get(active),
            (stock_meta or {}).get("last_bar"),
            (stock_meta or {}).get("prev_bar"),
            source.is_sample,
        )
        price, caption, stats = (
            build_quote_price(display),
            build_quote_caption(display),
            build_quote_stats(display),
        )

    shown_quotes = row_quotes or [batch.quotes.get(active)]
    return (
        cells,
        price,
        caption,
        stats,
        market_status(shown_quotes, source.is_sample),
        {"ok": True, "fetched_at": _oldest_fetch(shown_quotes)},
    )
