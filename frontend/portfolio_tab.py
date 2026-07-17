"""Portfolio tab: layout and callbacks for positions, P/L, and transactions.

Kept separate from dashboard.py so the main module stays focused on the
market/chart experience. Callbacks call app.services.portfolio_services
directly — the same service layer the REST API consumes.
"""

import logging
from datetime import date

import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from dash import ALL, Input, Output, State, callback_context, dcc, html, no_update
from flask_login import current_user

from app.services import portfolio_services
from app.services.portfolio_services import PortfolioError

logger = logging.getLogger(__name__)

# Mirrors the figure palette in dashboard.py / custom.css tokens
GAIN = "#2FBF71"
LOSS = "#F0544F"
TEXT = "#E8ECF4"
TEXT_MUTED = "#77839B"
SURFACE = "#121826"
PIE_PALETTE = ["#5B8DEF", "#2FBF71", "#E0B84C", "#B57BEE", "#4CC3E0", "#F0885E", "#7CA5F5"]


def _money(value, signed=False):
    if value is None:
        return "N/A"
    sign = "+" if signed and value > 0 else ""
    return f"{sign}${value:,.2f}" if value >= 0 else f"-${abs(value):,.2f}"


def _pl_class(value, base="stat-value"):
    if value is None or value == 0:
        return base
    return f"{base} pl-gain" if value > 0 else f"{base} pl-loss"


def _stat_cell(label, value_children, value_class="stat-value"):
    return html.Div(
        [
            html.Div(label, className="stat-label"),
            html.Div(value_children, className=value_class),
        ],
        className="stat-cell",
    )


def build_portfolio_tab():
    return html.Div(
        [
            # Summary stat cards (populated by callback)
            html.Div(
                id="portfolio-summary",
                className="sw-card portfolio-summary-card",
            ),
            dbc.Row(
                [
                    # Positions table
                    dbc.Col(
                        html.Div(
                            [
                                html.H2("Positions", className="panel-title"),
                                dcc.Loading(
                                    type="circle",
                                    color="#5B8DEF",
                                    children=html.Div(id="portfolio-positions"),
                                ),
                            ],
                            className="sw-card",
                        ),
                        lg=8,
                        md=12,
                        className="mb-4",
                    ),
                    # Allocation pie
                    dbc.Col(
                        html.Div(
                            [
                                html.H2("Allocation", className="panel-title"),
                                html.Div(id="portfolio-allocation"),
                            ],
                            className="sw-card",
                        ),
                        lg=4,
                        md=12,
                        className="mb-4",
                    ),
                ],
                className="g-4",
            ),
            dbc.Row(
                [
                    # Record transaction form
                    dbc.Col(
                        html.Div(
                            [
                                html.H2("Record a trade", className="panel-title"),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="txn-side",
                                                options=[
                                                    {"label": "Buy", "value": "BUY"},
                                                    {"label": "Sell", "value": "SELL"},
                                                ],
                                                value="BUY",
                                                clearable=False,
                                                className="dark-dropdown",
                                            ),
                                            width=6,
                                        ),
                                        dbc.Col(
                                            dbc.Input(
                                                id="txn-symbol",
                                                type="text",
                                                placeholder="Ticker",
                                                autoComplete="off",
                                            ),
                                            width=6,
                                        ),
                                    ],
                                    className="g-2 mb-2",
                                ),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            dbc.Input(
                                                id="txn-quantity",
                                                type="number",
                                                min=0,
                                                step="any",
                                                placeholder="Quantity",
                                            ),
                                            width=6,
                                        ),
                                        dbc.Col(
                                            dbc.Input(
                                                id="txn-price",
                                                type="number",
                                                min=0,
                                                step="any",
                                                placeholder="Price / share",
                                            ),
                                            width=6,
                                        ),
                                    ],
                                    className="g-2 mb-2",
                                ),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            dcc.DatePickerSingle(
                                                id="txn-date",
                                                date=date.today(),
                                                display_format="YYYY-MM-DD",
                                                max_date_allowed=date.today(),
                                                className="txn-datepicker",
                                            ),
                                            width=6,
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Add transaction",
                                                id="txn-submit",
                                                className="sw-btn--primary w-100",
                                            ),
                                            width=6,
                                        ),
                                    ],
                                    className="g-2 align-items-center",
                                ),
                            ],
                            className="sw-card",
                        ),
                        lg=4,
                        md=12,
                        className="mb-4",
                    ),
                    # Recent transactions
                    dbc.Col(
                        html.Div(
                            [
                                html.H2("Recent transactions", className="panel-title"),
                                html.Div(id="portfolio-transactions"),
                            ],
                            className="sw-card",
                        ),
                        lg=8,
                        md=12,
                        className="mb-4",
                    ),
                ],
                className="g-4",
            ),
            # Bumped after any mutation to trigger a re-render
            dcc.Store(id="portfolio-refresh", data=0),
        ],
        className="portfolio-tab",
    )


def _empty_state(icon, message, sub=None):
    children = [
        html.Div(icon, className="empty-state-icon"),
        html.Div(message, className="empty-state-title"),
    ]
    if sub:
        children.append(html.Div(sub, className="empty-state-sub"))
    return html.Div(children, className="empty-state")


def build_summary_cards(summary):
    unrealized = summary["unrealized_pl"]
    unrealized_pct = summary["unrealized_pl_pct"]
    unrealized_text = _money(unrealized, signed=True)
    if unrealized_pct is not None:
        unrealized_text += f" ({unrealized_pct:+.2f}%)"

    return html.Div(
        [
            _stat_cell(
                "Market Value", _money(summary["market_value"]), "stat-value stat-value--lg"
            ),
            _stat_cell("Cost Basis", _money(summary["cost_basis"])),
            _stat_cell("Unrealized P/L", unrealized_text, _pl_class(unrealized)),
            _stat_cell(
                "Realized P/L",
                _money(summary["realized_pl"], signed=True),
                _pl_class(summary["realized_pl"]),
            ),
        ],
        className="stat-grid portfolio-stat-grid",
    )


def build_positions_table(positions):
    if not positions:
        return _empty_state(
            "\U0001f4bc",
            "No open positions",
            "Record your first trade to start tracking P/L.",
        )

    header = html.Tr(
        [
            html.Th("Symbol"),
            html.Th("Qty", className="num"),
            html.Th("Avg Cost", className="num"),
            html.Th("Price", className="num"),
            html.Th("Market Value", className="num"),
            html.Th("Unrealized P/L", className="num"),
        ]
    )

    rows = []
    for p in positions:
        pl_text = _money(p.unrealized_pl, signed=True)
        if p.unrealized_pl_pct is not None:
            pl_text += f" ({p.unrealized_pl_pct:+.2f}%)"
        rows.append(
            html.Tr(
                [
                    html.Td(
                        [
                            html.Span(p.symbol, className="watchlist-ticker"),
                            html.Span(p.name, className="watchlist-company"),
                        ]
                    ),
                    html.Td(f"{p.quantity:,f}".rstrip("0").rstrip("."), className="num"),
                    html.Td(_money(p.avg_cost), className="num"),
                    html.Td(_money(p.current_price), className="num"),
                    html.Td(_money(p.market_value), className="num"),
                    html.Td(pl_text, className=_pl_class(p.unrealized_pl, base="num")),
                ]
            )
        )

    return html.Table(
        [html.Thead(header), html.Tbody(rows)],
        className="portfolio-table",
    )


def build_allocation_chart(summary):
    allocations = summary["allocations"]
    if not allocations:
        return _empty_state("\U0001f4ca", "Nothing to chart yet")

    figure = go.Figure(
        go.Pie(
            labels=[a["symbol"] for a in allocations],
            values=[float(a["value"]) for a in allocations],
            hole=0.55,
            marker={"colors": PIE_PALETTE, "line": {"color": SURFACE, "width": 2}},
            textinfo="label+percent",
            textfont={"color": TEXT, "size": 12},
            hovertemplate="%{label}: $%{value:,.2f} (%{percent})<extra></extra>",
        )
    )
    figure.update_layout(
        showlegend=False,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        height=260,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": TEXT_MUTED},
    )
    return dcc.Graph(figure=figure, config={"displayModeBar": False})


def build_transactions_list(transactions):
    if not transactions:
        return _empty_state("\U0001f9fe", "No transactions recorded")

    rows = []
    for txn in transactions:
        side_class = "txn-side txn-side--buy" if txn.side == "BUY" else "txn-side txn-side--sell"
        rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(txn.side, className=side_class),
                            html.Span(txn.stock.symbol, className="watchlist-ticker"),
                            html.Span(
                                f"{txn.quantity:,f}".rstrip("0").rstrip(".")
                                + f" @ {_money(txn.price)}",
                                className="txn-detail",
                            ),
                            html.Span(
                                txn.executed_at.strftime("%Y-%m-%d"), className="txn-date"
                            ),
                        ],
                        className="watchlist-row-info txn-row-info",
                    ),
                    dbc.Button(
                        "Delete",
                        id={"type": "delete-transaction", "index": txn.id},
                        size="sm",
                        className="sw-btn--danger sw-btn--sm",
                    ),
                ],
                className="watchlist-row",
            )
        )
    return html.Div(rows)


def register_portfolio_callbacks(dash_app):
    @dash_app.callback(
        [
            Output("portfolio-summary", "children"),
            Output("portfolio-positions", "children"),
            Output("portfolio-allocation", "children"),
            Output("portfolio-transactions", "children"),
        ],
        [
            Input("portfolio-refresh", "data"),
            Input("main-tabs", "value"),
        ],
    )
    def render_portfolio(_refresh, active_tab):
        if active_tab != "portfolio":
            return no_update, no_update, no_update, no_update
        if not current_user.is_authenticated:
            locked = _empty_state("\U0001f512", "Please log in to view your portfolio.")
            return locked, None, None, None

        summary = portfolio_services.get_portfolio_summary(current_user.id)
        transactions = portfolio_services.list_transactions(current_user.id, limit=25)
        return (
            build_summary_cards(summary),
            build_positions_table(summary["positions"]),
            build_allocation_chart(summary),
            build_transactions_list(transactions),
        )

    @dash_app.callback(
        [
            Output("portfolio-refresh", "data"),
            Output("toast-trigger", "data", allow_duplicate=True),
            Output("txn-symbol", "value"),
            Output("txn-quantity", "value"),
            Output("txn-price", "value"),
        ],
        Input("txn-submit", "n_clicks"),
        [
            State("txn-side", "value"),
            State("txn-symbol", "value"),
            State("txn-quantity", "value"),
            State("txn-price", "value"),
            State("txn-date", "date"),
            State("portfolio-refresh", "data"),
        ],
        prevent_initial_call=True,
    )
    def add_transaction(n_clicks, side, symbol, quantity, price, date_str, refresh):
        if not n_clicks or not current_user.is_authenticated:
            return (no_update,) * 5

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
            executed_at = date.fromisoformat(date_str[:10])
            txn = portfolio_services.record_transaction(
                current_user.id, symbol, side, str(quantity), str(price), executed_at
            )
        except PortfolioError as exc:
            return no_update, toast(str(exc), "danger"), no_update, no_update, no_update
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
            toast(f"Recorded {txn.side} {quantity} {txn.stock.symbol}.", "success"),
            "",
            None,
            None,
        )

    @dash_app.callback(
        [
            Output("portfolio-refresh", "data", allow_duplicate=True),
            Output("toast-trigger", "data", allow_duplicate=True),
        ],
        Input({"type": "delete-transaction", "index": ALL}, "n_clicks"),
        State("portfolio-refresh", "data"),
        prevent_initial_call=True,
    )
    def remove_transaction(n_clicks_list, refresh):
        if not current_user.is_authenticated or not any(n_clicks_list or []):
            return no_update, no_update

        triggered = callback_context.triggered_id
        if not triggered or "index" not in triggered:
            return no_update, no_update

        def toast(message, kind):
            return {"message": message, "type": kind, "n": (refresh or 0) + 1}

        try:
            deleted = portfolio_services.delete_transaction(current_user.id, triggered["index"])
        except PortfolioError as exc:
            return no_update, toast(str(exc), "danger")
        except Exception:
            logger.exception("Failed to delete transaction")
            return no_update, toast("Could not delete the transaction.", "danger")

        if not deleted:
            return no_update, toast("Transaction not found.", "danger")
        return (refresh or 0) + 1, toast("Transaction deleted.", "success")
