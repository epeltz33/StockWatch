"""Portfolio section: positions, P/L, allocation, and the trade ledger.

Kept separate from dashboard.py so the main module stays focused on the
market/chart experience. Everything is read through the dashboard's data
source — the signed-in user's ledger at /dash/, the fixed sample ledger in
the demo — and both go through the same average-cost accounting in
app.services.portfolio_services.
"""

import logging
from datetime import date

import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from dash import Input, Output, State, callback_context, dcc, html, no_update
from dash.exceptions import PreventUpdate

from app.services.portfolio_services import PortfolioError
from frontend.data_sources import ReadOnlyDemoError
from frontend.shell import list_skeleton, loading, stat_skeleton

logger = logging.getLogger(__name__)

# Mirrors the figure palette in dashboard.py / custom.css tokens
GAIN = "#2FBF71"
LOSS = "#F0544F"
TEXT = "#E8ECF4"
TEXT_MUTED = "#8B97AE"
SURFACE = "#121826"
PIE_PALETTE = ["#5B8DEF", "#2FBF71", "#E0B84C", "#B57BEE", "#4CC3E0", "#F0885E", "#7CA5F5"]
UNAVAILABLE = "Unavailable"


def _money(value, signed=False):
    if value is None:
        return "N/A"
    sign = "+" if signed and value > 0 else ""
    return f"{sign}${value:,.2f}" if value >= 0 else f"-${abs(value):,.2f}"


def format_quantity(value):
    """Share counts without padding: 10.000000 -> '10', 2.5 -> '2.5'.

    Only a fractional part is trimmed — Decimal('10') formats as '10' with
    no point, and stripping zeros from that would turn ten shares into one.
    """
    text = f"{value:,f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _pl_class(value, base="stat-value"):
    if value is None or value == 0:
        return base
    return f"{base} pl-gain" if value > 0 else f"{base} pl-loss"


def _stat_cell(label, value_children, value_class="stat-value", note=None):
    children = [
        html.Div(label, className="stat-label"),
        html.Div(value_children, className=value_class),
    ]
    if note:
        children.append(html.Div(note, className="stat-note"))
    return html.Div(children, className="stat-cell")


def _format_date(value):
    day = date.fromisoformat(value) if isinstance(value, str) else value
    return f"{day:%b} {day.day}, {day.year}"


def _empty_state(icon, message, sub=None, action=None):
    children = [
        html.Div(icon, className="empty-state-icon", **{"aria-hidden": "true"}),
        html.Div(message, className="empty-state-title"),
    ]
    if sub:
        children.append(html.Div(sub, className="empty-state-sub"))
    if action is not None:
        children.append(html.Div(action, className="empty-state-action"))
    return html.Div(children, className="empty-state")


def _field(label, control, control_id):
    return html.Div(
        [html.Label(label, htmlFor=control_id, className="form-label"), control],
        className="form-field",
    )


def _trade_form():
    today = date.today().isoformat()
    return html.Div(
        [
            html.H2("Record a trade", className="panel-title"),
            html.Div(
                [
                    _field(
                        "Side",
                        dbc.Select(
                            id="txn-side",
                            options=[
                                {"label": "Buy", "value": "BUY"},
                                {"label": "Sell", "value": "SELL"},
                            ],
                            value="BUY",
                        ),
                        "txn-side",
                    ),
                    _field(
                        "Ticker",
                        dbc.Input(
                            id="txn-symbol",
                            type="text",
                            placeholder="AAPL",
                            autoComplete="off",
                            maxLength=10,
                        ),
                        "txn-symbol",
                    ),
                    _field(
                        "Quantity",
                        dbc.Input(
                            id="txn-quantity",
                            type="number",
                            min=0,
                            step="any",
                            placeholder="10",
                            inputMode="decimal",
                        ),
                        "txn-quantity",
                    ),
                    _field(
                        "Price per share",
                        dbc.Input(
                            id="txn-price",
                            type="number",
                            min=0,
                            step="any",
                            placeholder="150.00",
                            inputMode="decimal",
                        ),
                        "txn-price",
                    ),
                    _field(
                        "Trade date",
                        dbc.Input(id="txn-date", type="date", value=today, max=today),
                        "txn-date",
                    ),
                ],
                className="trade-form-grid",
            ),
            dbc.Button(
                "Add transaction", id="txn-submit", n_clicks=0, className="sw-btn--primary w-100"
            ),
        ],
        className="sw-card",
    )


def _demo_invite():
    return html.Div(
        [
            html.H2("Your own portfolio", className="panel-title"),
            html.P(
                "This is a sample ledger priced with sample closes. Create a free "
                "account to record your own trades and track real positions.",
                className="invite-copy",
            ),
            html.Div(
                [
                    html.A(
                        "Create account",
                        href="/auth/register",
                        className="btn sw-btn--primary sw-btn--sm",
                    ),
                    html.A("Log in", href="/auth/login", className="sw-link-btn"),
                ],
                className="invite-actions",
            ),
        ],
        className="sw-card invite-card",
    )


def build_portfolio_tab(source):
    return html.Div(
        [
            html.Div(
                loading(
                    html.Div(
                        html.Div(stat_skeleton(4), className="stat-grid portfolio-stat-grid"),
                        id="portfolio-summary",
                    ),
                    "loading-portfolio-summary",
                ),
                className="sw-card portfolio-summary-card",
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.H2("Positions", id="positions-title", className="panel-title"),
                            loading(
                                html.Div(list_skeleton(3), id="portfolio-positions"),
                                "loading-portfolio-positions",
                            ),
                        ],
                        className="sw-card positions-card",
                        **{"aria-labelledby": "positions-title"},
                    ),
                    html.Section(
                        [
                            html.H2("Allocation", id="allocation-title", className="panel-title"),
                            html.Div(id="portfolio-allocation", className="allocation-body"),
                        ],
                        className="sw-card allocation-card",
                        **{"aria-labelledby": "allocation-title"},
                    ),
                ],
                className="portfolio-grid",
            ),
            html.Div(
                [
                    _demo_invite() if source.read_only else _trade_form(),
                    html.Section(
                        [
                            html.H2(
                                "Recent transactions",
                                id="transactions-title",
                                className="panel-title",
                            ),
                            html.Div(list_skeleton(4), id="portfolio-transactions"),
                        ],
                        className="sw-card transactions-card",
                        **{"aria-labelledby": "transactions-title"},
                    ),
                ],
                className="portfolio-grid portfolio-grid--ledger",
            ),
            # Bumped after any mutation to trigger a re-render
            dcc.Store(id="portfolio-refresh", data=0),
        ],
        className="portfolio-tab",
    )


def _coverage_note(summary, is_sample):
    """How much of the portfolio the totals cover, and as of which close."""
    holdings = summary.get("holding_count", 0)
    if not holdings:
        return None
    priced = summary.get("priced_count", 0)
    dates = summary.get("price_dates") or []
    if dates:
        closes = (
            _format_date(dates[-1])
            if len(dates) == 1
            else (f"{_format_date(dates[0])} – {_format_date(dates[-1])}")
        )
        when = f"{'Sample closes' if is_sample else 'Closes'} as of {closes}"
    else:
        when = None

    if priced == holdings:
        parts = [f"All {holdings} holding{'s' if holdings != 1 else ''} priced"]
    elif priced == 0:
        parts = [f"No prices available for your {holdings} holdings"]
    else:
        parts = [f"{priced} of {holdings} holdings priced — totals cover priced holdings only"]
    if when:
        parts.append(when)
    tone = "coverage-note coverage-note--partial" if priced < holdings else "coverage-note"
    return html.P(" · ".join(parts), className=tone)


def build_summary_cards(summary, is_sample=False):
    market_value = summary["market_value"]
    unrealized = summary["unrealized_pl"]
    unrealized_pct = summary["unrealized_pl_pct"]
    partial = summary.get("is_partial", False)

    if unrealized is None:
        unrealized_text = UNAVAILABLE
    else:
        unrealized_text = _money(unrealized, signed=True)
        if unrealized_pct is not None:
            unrealized_text += f" ({unrealized_pct:+.2f}%)"

    value_children = [UNAVAILABLE if market_value is None else _money(market_value)]
    if partial:
        value_children.append(html.Span("Partial", className="partial-badge"))

    return html.Div(
        [
            html.Div(
                [
                    _stat_cell(
                        "Market value",
                        value_children,
                        "stat-value stat-value--lg"
                        + (" stat-value--na" if market_value is None else ""),
                    ),
                    _stat_cell("Cost basis", _money(summary["cost_basis"])),
                    _stat_cell(
                        "Unrealized P/L" + (" (priced)" if partial else ""),
                        unrealized_text,
                        _pl_class(unrealized) + (" stat-value--na" if unrealized is None else ""),
                    ),
                    _stat_cell(
                        "Realized P/L",
                        _money(summary["realized_pl"], signed=True),
                        _pl_class(summary["realized_pl"]),
                    ),
                ],
                className="stat-grid portfolio-stat-grid",
            ),
            _coverage_note(summary, is_sample),
        ]
    )


def build_positions_table(positions, editable=True):
    if not positions:
        return _empty_state(
            "\U0001f4bc",
            "No open positions",
            "Record your first trade to start tracking P/L." if editable else None,
        )

    header = html.Tr(
        [
            html.Th("Symbol", scope="col"),
            html.Th("Qty", className="num", scope="col"),
            html.Th("Avg cost", className="num", scope="col"),
            html.Th("Last close", className="num", scope="col"),
            html.Th("Market value", className="num", scope="col"),
            html.Th("Unrealized P/L", className="num", scope="col"),
        ]
    )

    rows = []
    for p in positions:
        if p.unrealized_pl is None:
            pl_text = "—"
        else:
            pl_text = _money(p.unrealized_pl, signed=True)
            if p.unrealized_pl_pct is not None:
                pl_text += f" ({p.unrealized_pl_pct:+.2f}%)"
        unpriced_title = "Price unavailable" if p.current_price is None else None
        rows.append(
            html.Tr(
                [
                    html.Th(
                        [
                            html.Span(p.symbol, className="watchlist-ticker"),
                            html.Span(p.name, className="watchlist-company", title=p.name),
                        ],
                        scope="row",
                        className="position-name",
                    ),
                    html.Td(format_quantity(p.quantity), className="num"),
                    html.Td(_money(p.avg_cost), className="num"),
                    html.Td(
                        "—" if p.current_price is None else _money(p.current_price),
                        className="num",
                        title=unpriced_title
                        or (f"Close of {_format_date(p.price_date)}" if p.price_date else None),
                    ),
                    html.Td(
                        "—" if p.market_value is None else _money(p.market_value),
                        className="num",
                        title=unpriced_title,
                    ),
                    html.Td(pl_text, className=_pl_class(p.unrealized_pl, base="num")),
                ]
            )
        )

    # Wide tables scroll sideways inside this region; the page never does.
    return html.Div(
        html.Table([html.Thead(header), html.Tbody(rows)], className="portfolio-table"),
        className="table-scroll",
        tabIndex="0",
        role="region",
        **{"aria-label": "Positions table"},
    )


def build_allocation_chart(summary):
    allocations = summary["allocations"]
    if not allocations:
        return _empty_state(
            "\U0001f4ca",
            "Nothing to chart yet",
            "Allocation needs at least one priced holding."
            if summary.get("holding_count")
            else None,
        )

    figure = go.Figure(
        go.Pie(
            labels=[a["symbol"] for a in allocations],
            values=[float(a["value"]) for a in allocations],
            hole=0.55,
            marker={"colors": PIE_PALETTE, "line": {"color": SURFACE, "width": 2}},
            textinfo="label+percent",
            textfont={"color": TEXT, "size": 12},
            hovertemplate="%{label}: $%{value:,.2f} (%{percent})<extra></extra>",
            sort=False,
        )
    )
    figure.update_layout(
        showlegend=False,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        autosize=True,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": TEXT_MUTED},
    )
    note = None
    if summary.get("is_partial"):
        note = html.P(
            f"Priced holdings only ({summary['priced_count']} of {summary['holding_count']}).",
            className="coverage-note coverage-note--partial",
        )
    return html.Div(
        [
            dcc.Graph(
                figure=figure,
                config={"displayModeBar": False, "responsive": True},
                responsive=True,
                className="allocation-graph",
            ),
            note,
        ]
    )


def transaction_label(txn):
    return (
        f"{txn.side} {format_quantity(txn.quantity)} {txn.stock.symbol} @ {_money(txn.price)} "
        f"on {_format_date(txn.executed_at)}"
    )


def build_transactions_list(transactions, editable=True):
    if not transactions:
        return _empty_state("\U0001f9fe", "No transactions recorded")

    rows = []
    for txn in transactions:
        side_class = "txn-side txn-side--buy" if txn.side == "BUY" else "txn-side txn-side--sell"
        row = [
            html.Div(
                [
                    html.Span(txn.side, className=side_class),
                    html.Span(txn.stock.symbol, className="watchlist-ticker"),
                    html.Span(
                        f"{format_quantity(txn.quantity)} @ {_money(txn.price)}",
                        className="txn-detail",
                    ),
                    html.Time(
                        _format_date(txn.executed_at),
                        dateTime=txn.executed_at.isoformat(),
                        className="txn-date",
                    ),
                ],
                className="txn-row-info",
            )
        ]
        if editable:
            row.append(
                html.Button(
                    "Delete",
                    id={"type": "delete-transaction", "index": txn.id},
                    n_clicks=0,
                    type="button",
                    className="btn sw-btn--danger sw-btn--sm",
                    **{"aria-label": f"Delete transaction: {transaction_label(txn)}"},
                )
            )
        rows.append(html.Li(row, className="txn-row"))
    return html.Ul(rows, className="txn-list")


def render_portfolio_section(source):
    """(summary, positions, allocation, transactions) for the current source."""
    editable = not source.read_only
    summary = source.portfolio_summary()
    if summary is None:
        locked = _empty_state("\U0001f512", "Log in to view your portfolio.")
        return locked, None, None, None
    transactions = source.transactions(limit=25)
    return (
        build_summary_cards(summary, is_sample=source.is_sample),
        build_positions_table(summary["positions"], editable=editable),
        build_allocation_chart(summary),
        build_transactions_list(transactions, editable=editable),
    )


def register_portfolio_callbacks(dash_app, source):
    @dash_app.callback(
        Output("portfolio-summary", "children"),
        Output("portfolio-positions", "children"),
        Output("portfolio-allocation", "children"),
        Output("portfolio-transactions", "children"),
        Input("portfolio-refresh", "data"),
        Input("active-tab", "data"),
    )
    def render_portfolio(_refresh, active_tab):
        trigger = callback_context.triggered_id
        if source.is_sample:
            # Fixed data: render once at page load so the section is already
            # populated the moment it's selected; tab switches change nothing.
            if trigger == "active-tab":
                raise PreventUpdate
        elif active_tab != "portfolio":
            # Signed in: price holdings only when the section is opened, and
            # re-price each time it is (quotes are cached for five minutes).
            raise PreventUpdate
        return render_portfolio_section(source)

    if source.read_only:
        return

    @dash_app.callback(
        Output("portfolio-refresh", "data", allow_duplicate=True),
        Output("toast-trigger", "data", allow_duplicate=True),
        Output("txn-symbol", "value"),
        Output("txn-quantity", "value"),
        Output("txn-price", "value"),
        Input("txn-submit", "n_clicks"),
        State("txn-side", "value"),
        State("txn-symbol", "value"),
        State("txn-quantity", "value"),
        State("txn-price", "value"),
        State("txn-date", "value"),
        State("portfolio-refresh", "data"),
        prevent_initial_call=True,
    )
    def add_transaction(n_clicks, side, symbol, quantity, price, date_str, refresh):
        if not n_clicks:
            raise PreventUpdate
        return record_trade(source, side, symbol, quantity, price, date_str, refresh)


def record_trade(source, side, symbol, quantity, price, date_str, refresh):
    def toast(message, kind):
        return {"message": message, "type": kind, "n": (refresh or 0) + 1}

    if not symbol or quantity is None or price is None or not date_str:
        return (
            no_update,
            toast("Fill in ticker, quantity, price, and date.", "danger"),
            no_update,
            no_update,
            no_update,
        )

    try:
        executed_at = date.fromisoformat(str(date_str)[:10])
        if executed_at > date.today():
            raise PortfolioError("Trade date can't be in the future.")
        txn = source.record_transaction(symbol, side, str(quantity), str(price), executed_at)
    except (PortfolioError, ReadOnlyDemoError) as exc:
        return no_update, toast(str(exc), "danger"), no_update, no_update, no_update
    except ValueError:
        return (
            no_update,
            toast("Enter the date as YYYY-MM-DD.", "danger"),
            no_update,
            no_update,
            no_update,
        )
    except Exception:
        logger.exception("Failed to record transaction")
        return (
            no_update,
            toast("Could not record the transaction.", "danger"),
            no_update,
            no_update,
            no_update,
        )

    return (
        (refresh or 0) + 1,
        toast(
            f"Recorded {txn.side} {format_quantity(txn.quantity)} {txn.stock.symbol}.", "success"
        ),
        "",
        None,
        None,
    )
