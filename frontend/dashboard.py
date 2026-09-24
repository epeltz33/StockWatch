"""StockWatch dashboard: one Dash page, mounted twice.

create_dash_app() mounts the signed-in dashboard at /dash/ on LiveSource;
create_demo_app() mounts the public demo at /demo/ on SampleSource. Both are
built from this module's layout and callbacks — the section modules
(charts, stock_view, watchlist_panel, portfolio_tab, actions) hold the
rendering and logic. The source, fixed when the app is mounted, decides
where data comes from, and the demo registers no callback that can change
anything.
"""

import logging

import dash
import dash_bootstrap_components as dbc
from dash import (
    ALL,
    MATCH,
    ClientsideFunction,
    Input,
    Output,
    State,
    callback_context,
    dcc,
    html,
    no_update,
)
from dash.exceptions import PreventUpdate
from flask import jsonify, request

from frontend.actions import (
    add_symbol_to_watchlist,
    confirmation_prompt,
    perform_confirmed_delete,
    remove_symbol_from_watchlist,
)
from frontend.charts import GRAPH_CONFIG, blank_figure
from frontend.data_sources import LiveSource, ReadOnlyDemoError, SampleSource, WatchlistError
from frontend.portfolio_tab import build_portfolio_tab, register_portfolio_callbacks
from frontend.shell import (
    INDEX_STRING,
    build_header,
    confirm_modal,
    empty_state,
    header_skeleton,
    list_skeleton,
    loading,
    skeleton_block,
    skeleton_line,
    stat_skeleton,
    toast,
    toast_container,
)
from frontend.stock_view import (
    ABOUT_TEXT_EXPANDED_CLASS,
    about_display_state,
    change_period,
    handle_stock_request,
)
from frontend.watchlist_panel import (
    choose_watchlist,
    refresh_market,
    render_watchlist_section,
    watchlist_options,
)

logger = logging.getLogger(__name__)

ADD_TO_WATCHLIST_LABEL = "＋ Watchlist"
# Browser-session key for the signed-in dashboard's selections. The demo keeps
# none: every visit starts from the same sample view.
STORAGE_KEY = "stockwatch:dashboard:v1"
# Closing prices change once a session; five minutes is plenty while the
# Market section is visible, and polling stops everywhere else.
REFRESH_INTERVAL_MS = 5 * 60 * 1000


# ============================================================
# Layout
# ============================================================


def _create_watchlist_form():
    return html.Div(
        [
            html.Label("New watchlist name", htmlFor="new-watchlist-input", className="form-label"),
            dbc.InputGroup(
                [
                    dbc.Input(
                        id="new-watchlist-input",
                        type="text",
                        placeholder="e.g. Tech leaders",
                        maxLength=64,
                        autoComplete="off",
                    ),
                    dbc.Button(
                        "Create",
                        id="create-watchlist-button",
                        n_clicks=0,
                        className="sw-btn--primary",
                    ),
                ]
            ),
            html.Button(
                "Cancel", id="new-watchlist-cancel", n_clicks=0, type="button", className="link-btn"
            ),
        ],
        className="create-watchlist-form",
    )


def _search_section(source):
    sample_symbols = source.search_symbols
    input_kwargs = {"list": "sample-symbols"} if sample_symbols else {}
    placeholder = (
        "Search the sample — " + ", ".join(sample_symbols)
        if sample_symbols
        else "Search ticker — e.g. AAPL"
    )
    children = [
        html.Label("Search by ticker symbol", htmlFor="stock-input", className="visually-hidden"),
        dbc.InputGroup(
            [
                dbc.Input(
                    id="stock-input",
                    type="text",
                    placeholder=placeholder,
                    autoComplete="off",
                    maxLength=10,
                    **input_kwargs,
                ),
                dbc.Button("Search", id="search-button", n_clicks=0, className="sw-btn--primary"),
            ],
            className="search-group",
        ),
    ]
    if sample_symbols:
        names = {sym: (source.details(sym) or {}).get("name", sym) for sym in sample_symbols}
        children.append(
            html.Datalist(
                [html.Option(value=sym, label=names.get(sym, sym)) for sym in sample_symbols],
                id="sample-symbols",
            )
        )
        children.append(
            html.Div(
                [html.Span("Sample tickers", className="suggestions-label")]
                + [
                    html.Button(
                        sym,
                        id={"type": "symbol-suggestion", "index": sym},
                        n_clicks=0,
                        type="button",
                        className="suggestion-chip",
                        title=f"Show {names.get(sym, sym)}",
                    )
                    for sym in sample_symbols
                ],
                className="symbol-suggestions",
                role="group",
                **{"aria-label": "Sample tickers"},
            )
        )
    children.append(
        html.Div(
            id="search-status", className="search-status", role="status", **{"aria-live": "polite"}
        )
    )
    return html.Div(children, className="market-search")


def _chart_card(source):
    header = [html.Div(header_skeleton(), id="stock-header", className="chart-identity")]
    if not source.read_only:
        header.append(
            html.Button(
                ADD_TO_WATCHLIST_LABEL,
                id="add-to-watchlist",
                n_clicks=0,
                type="button",
                disabled=True,
                className="btn sw-btn--ghost sw-btn--sm",
                title="Add this stock to the selected watchlist",
            )
        )
    body = html.Div(
        [
            html.Div(header, className="chart-header"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        skeleton_line("150px", "34px"),
                                        id="stock-quote-price",
                                        className="quote-price",
                                    ),
                                    html.Div(id="chart-change-readout", className="readout"),
                                ],
                                className="price-row",
                            ),
                            html.Div(
                                skeleton_line("190px", "11px"),
                                id="stock-quote-caption",
                                className="price-caption",
                            ),
                        ],
                        className="price-block",
                    ),
                    html.Div(id="period-toolbar", className="period-toolbar"),
                ],
                className="chart-controls",
            ),
            html.Div(
                [
                    dcc.Graph(
                        id="stock-chart",
                        figure=blank_figure(),
                        config=GRAPH_CONFIG,
                        responsive=True,
                        className="stock-graph",
                    ),
                    skeleton_block("100%", "chart-skeleton"),
                    html.Div(
                        empty_state(
                            "\U0001f4c8",
                            "Search a ticker to begin",
                            "Type a symbol like AAPL above and press Enter.",
                        ),
                        className="chart-empty",
                    ),
                ],
                className="chart-body",
            ),
        ]
    )
    return html.Section(
        loading(body, "loading-chart"),
        id="chart-card",
        className="sw-card chart-card chart-card--initial",
        **{"aria-label": "Price chart"},
    )


def _watchlist_card(source):
    editable = not source.read_only
    actions = []
    if not source.is_sample:
        actions.append(
            html.Button(
                "↻",
                id="refresh-watchlist",
                n_clicks=0,
                type="button",
                className="icon-btn",
                title="Refresh prices",
                **{"aria-label": "Refresh watchlist prices"},
            )
        )
    if editable:
        actions.append(
            html.Button(
                "＋ New",
                id="new-watchlist-toggle",
                n_clicks=0,
                type="button",
                className="btn sw-btn--ghost sw-btn--sm",
                **{"aria-expanded": "false", "aria-controls": "new-watchlist-collapse"},
            )
        )
    children = [
        html.Div(
            [
                html.H2("Watchlist", id="watchlist-title", className="panel-title"),
                html.Div(actions, className="card-actions"),
            ],
            className="card-head",
        ),
        html.Div(
            dcc.Dropdown(
                id="watchlist-dropdown",
                options=[],
                value=None,
                clearable=False,
                searchable=False,
                placeholder="Select a watchlist",
                className="dark-dropdown",
            ),
            className="watchlist-picker",
            role="group",
            hidden=source.is_sample,
            **{"aria-label": "Choose a watchlist"},
        ),
    ]
    if editable:
        children.append(
            dbc.Collapse(_create_watchlist_form(), id="new-watchlist-collapse", is_open=False)
        )
    children += [
        loading(html.Div(list_skeleton(), id="watchlist-section"), "loading-watchlist"),
        html.Div(
            id="watchlist-status",
            className="market-status",
            role="status",
            **{"aria-live": "polite"},
        ),
    ]
    return html.Section(
        children,
        className="sw-card watchlist-card",
        **{"aria-labelledby": "watchlist-title"},
    )


def _details_card():
    return html.Section(
        [
            html.H2("Details", id="details-title", className="panel-title"),
            loading(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    stat_skeleton(2), id="stock-quote-stats", className="stat-group"
                                ),
                                html.Div(
                                    stat_skeleton(4),
                                    id="stock-profile-stats",
                                    className="stat-group",
                                ),
                            ],
                            className="stat-grid",
                        ),
                        html.Div(id="stock-about"),
                    ]
                ),
                "loading-details",
            ),
        ],
        className="sw-card details-card",
        **{"aria-labelledby": "details-title"},
    )


def build_layout(source):
    """The whole page for one request."""
    boot = {
        "storage_key": None if source.is_sample else STORAGE_KEY,
        "user": None if source.is_sample else source.account_key(),
        "mode": source.mode,
    }
    title = "StockWatch demo with sample data" if source.is_sample else "StockWatch dashboard"
    market = html.Section(
        [
            _search_section(source),
            html.Div(
                [_chart_card(source), _watchlist_card(source), _details_card()],
                className="market-grid",
            ),
        ],
        id="market-panel",
        className="sw-panel",
        **{"aria-label": "Market"},
    )
    portfolio = html.Section(
        build_portfolio_tab(source),
        id="portfolio-panel",
        className="sw-panel",
        hidden=True,
        **{"aria-label": "Portfolio"},
    )
    children = [
        build_header(source, source.account_label()),
        html.Main(
            [html.H1(title, className="visually-hidden"), market, portfolio],
            id="main-content",
            className="sw-main",
            tabIndex="-1",
        ),
        dcc.Store(id="boot", data=boot),
        dcc.Store(id="restore-request"),
        dcc.Store(id="ui-state"),
        dcc.Store(id="stock-symbol-store"),
        dcc.Store(id="chart-period-store"),
        dcc.Store(id="stock-meta"),
        dcc.Store(id="failed-search"),
        dcc.Store(id="symbol-request"),
        dcc.Store(id="active-tab", data="market"),
        dcc.Store(id="watchlist-version", data=0),
        dcc.Store(id="market-refresh-meta"),
        dcc.Store(id="toast-trigger"),
        dcc.Interval(
            id="market-refresh-interval",
            interval=REFRESH_INTERVAL_MS,
            n_intervals=0,
            # The sample never changes: no polling in the demo
            disabled=source.is_sample,
        ),
        toast_container(),
    ]
    if not source.is_sample:
        children.append(dcc.Store(id="retry-request"))
    if not source.read_only:
        children += [
            dcc.Store(id="pending-action"),
            dcc.Store(id="remove-request"),
            dcc.Store(id="delete-request"),
            confirm_modal(),
        ]
    return html.Div(children, className=f"sw-app sw-app--{source.mode}")


# ============================================================
# Callbacks
# ============================================================


def _key(dependency):
    return f"{dependency.component_id}.{dependency.component_property}"


def _respond(outputs, values):
    """Order a {"id.prop": value} dict to match `outputs`; the rest no_update."""
    return tuple(values.get(_key(o), no_update) for o in outputs)


def _triggered():
    """(triggered id, value) for the input that fired, or (None, None)."""
    ctx = callback_context
    if not ctx.triggered:
        return None, None
    return ctx.triggered_id, ctx.triggered[0].get("value")


def register_callbacks(dash_app, source):
    editable = not source.read_only

    # --- session restore -------------------------------------------------
    dash_app.clientside_callback(
        ClientsideFunction("stockwatch", "readSavedState"),
        Output("restore-request", "data"),
        Input("boot", "data"),
    )
    dash_app.clientside_callback(
        ClientsideFunction("stockwatch", "saveState"),
        Output("ui-state", "data"),
        Input("stock-symbol-store", "data"),
        Input("chart-period-store", "data"),
        Input("watchlist-dropdown", "value"),
        State("boot", "data"),
        prevent_initial_call=True,
    )

    @dash_app.callback(
        Output("watchlist-dropdown", "options"),
        Output("watchlist-dropdown", "value"),
        Output("watchlist-version", "data", allow_duplicate=True),
        Input("restore-request", "data"),
        State("watchlist-version", "data"),
        prevent_initial_call=True,
    )
    def restore_watchlists(saved, version):
        """Pick the watchlist to show: the saved one if it is still the
        user's own (ids in browser storage are client-controlled), else the
        first. Bumping the version renders it even if the value is unchanged."""
        if saved is None:
            raise PreventUpdate
        chosen = choose_watchlist(source, (saved or {}).get("watchlist_id"))
        return watchlist_options(source.watchlists()), chosen, (version or 0) + 1

    # --- loading a stock -------------------------------------------------
    stock_outputs = [
        Output("stock-header", "children"),
        Output("stock-quote-price", "children"),
        Output("stock-quote-caption", "children"),
        Output("chart-change-readout", "children"),
        Output("period-toolbar", "children"),
        Output("stock-chart", "figure"),
        Output("stock-quote-stats", "children"),
        Output("stock-profile-stats", "children"),
        Output("stock-about", "children"),
        Output("chart-card", "className"),
        Output("stock-symbol-store", "data"),
        Output("chart-period-store", "data"),
        Output("stock-meta", "data"),
        Output("search-status", "children"),
        Output("failed-search", "data"),
        Output("stock-input", "value"),
        Output("stock-input", "invalid"),
    ]
    if editable:
        stock_outputs.append(Output("add-to-watchlist", "disabled"))

    # Clicks on tickers (watchlist rows, sample chips, retry) reach the server
    # loader only through this browser-side gate. Rendering those buttons
    # fires pattern-matching inputs with zero clicks, and Dash drops an
    # in-flight response when its callback is triggered again — so wiring the
    # buttons to the loader directly let a watchlist render cancel the page's
    # initial stock load.
    dash_app.clientside_callback(
        ClientsideFunction("stockwatch", "requestSymbol"),
        Output("symbol-request", "data"),
        Input({"type": "symbol-suggestion", "index": ALL}, "n_clicks"),
        Input({"type": "load-watchlist-stock", "index": ALL}, "n_clicks"),
        Input({"type": "retry-search", "index": ALL}, "n_clicks"),
        State("failed-search", "data"),
        prevent_initial_call=True,
    )

    @dash_app.callback(
        *stock_outputs,
        Input("search-button", "n_clicks"),
        Input("stock-input", "n_submit"),
        Input("symbol-request", "data"),
        Input("restore-request", "data"),
        State("stock-input", "value"),
        State("chart-period-store", "data"),
        State("stock-symbol-store", "data"),
        prevent_initial_call=True,
    )
    def load_stock(_search, _submit, symbol_request, restore, typed, period, shown):
        trigger, value = _triggered()
        values = handle_stock_request(
            source,
            trigger,
            value,
            typed=typed,
            period=period,
            shown=shown,
            restore=restore,
        )
        return _respond(stock_outputs, values)

    # --- period buttons --------------------------------------------------
    period_outputs = [
        Output("stock-chart", "figure", allow_duplicate=True),
        Output({"type": "period-btn", "index": ALL}, "className"),
        Output({"type": "period-btn", "index": ALL}, "aria-pressed"),
        Output("chart-change-readout", "children", allow_duplicate=True),
        Output("chart-period-store", "data", allow_duplicate=True),
    ]

    @dash_app.callback(
        *period_outputs,
        Input({"type": "period-btn", "index": ALL}, "n_clicks"),
        State("stock-symbol-store", "data"),
        State({"type": "period-btn", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def update_chart_period(_clicks, symbol, btn_ids):
        trigger, value = _triggered()
        # Rendering the toolbar recreates the buttons, which fires this
        # callback with n_clicks=0. Only act on a real click.
        if not isinstance(trigger, dict) or not value or not symbol:
            raise PreventUpdate
        return change_period(source, symbol, trigger["index"], btn_ids)

    @dash_app.callback(
        Output({"type": "about-text", "index": MATCH}, "className"),
        Output({"type": "about-toggle", "index": MATCH}, "children"),
        Output({"type": "about-toggle", "index": MATCH}, "aria-expanded"),
        Input({"type": "about-toggle", "index": MATCH}, "n_clicks"),
        State({"type": "about-text", "index": MATCH}, "className"),
        prevent_initial_call=True,
    )
    def toggle_company_description(n_clicks, current_class_name):
        """Toggle a selected stock's About section between preview and full text."""
        if not n_clicks:
            raise PreventUpdate
        is_expanded = ABOUT_TEXT_EXPANDED_CLASS in (current_class_name or "")
        return about_display_state(expanded=not is_expanded)

    # --- watchlist rendering ---------------------------------------------
    dash_app.clientside_callback(
        ClientsideFunction("stockwatch", "markActiveTicker"),
        Output({"type": "load-watchlist-stock", "index": ALL}, "className"),
        Output({"type": "load-watchlist-stock", "index": ALL}, "aria-current"),
        Input("stock-symbol-store", "data"),
        # Rows and the symbol load in parallel on page load; whichever lands
        # second must still leave the right row marked.
        Input("watchlist-section", "children"),
        State({"type": "load-watchlist-stock", "index": ALL}, "id"),
        prevent_initial_call=True,
    )

    @dash_app.callback(
        Output("watchlist-section", "children"),
        Output("watchlist-status", "children"),
        Output("market-refresh-meta", "data"),
        Input("watchlist-dropdown", "value"),
        Input("watchlist-version", "data"),
        State("stock-symbol-store", "data"),
        prevent_initial_call=True,
    )
    def render_watchlist(watchlist_id, _version, active_symbol):
        return render_watchlist_section(source, watchlist_id, active_symbol)

    # --- sections ----------------------------------------------------------
    dash_app.clientside_callback(
        ClientsideFunction("stockwatch", "selectSection"),
        Output("active-tab", "data"),
        Input({"type": "nav-tab", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    dash_app.clientside_callback(
        ClientsideFunction("stockwatch", "showSection"),
        Output({"type": "nav-tab", "index": ALL}, "className"),
        Output({"type": "nav-tab", "index": ALL}, "aria-current"),
        Output("market-panel", "hidden"),
        Output("portfolio-panel", "hidden"),
        Input("active-tab", "data"),
        State({"type": "nav-tab", "index": ALL}, "id"),
        prevent_initial_call=True,
    )

    @dash_app.callback(
        Output("toast-container", "children"),
        Input("toast-trigger", "data"),
        prevent_initial_call=True,
    )
    def render_toast(payload):
        if not payload or not payload.get("message"):
            return no_update
        kind = payload.get("type", "info")
        icon_map = {
            "success": "success",
            "danger": "danger",
            "info": "primary",
            "warning": "warning",
        }
        header_map = {"success": "Done", "danger": "Error", "info": "Notice", "warning": "Warning"}
        return dbc.Toast(
            payload["message"],
            id={"type": "toast-instance", "index": payload.get("n", 0)},
            header=header_map.get(kind, "Notice"),
            icon=icon_map.get(kind, "primary"),
            is_open=True,
            dismissable=True,
            duration=4000,
            className="sw-toast",
        )

    if not source.is_sample:
        _register_refresh_callbacks(dash_app, source)
    if editable:
        _register_edit_callbacks(dash_app, source)


def _register_refresh_callbacks(dash_app, source):
    """Price refreshes: polling while Market is visible, the manual button,
    and retry after a failure. The demo's sample never changes: it has none."""
    dash_app.clientside_callback(
        ClientsideFunction("stockwatch", "pollWhileVisible"),
        Output("market-refresh-interval", "disabled"),
        Input("active-tab", "data"),
    )
    refresh_outputs = [
        Output({"type": "watchlist-quote", "index": ALL}, "children"),
        Output("stock-quote-price", "children", allow_duplicate=True),
        Output("stock-quote-caption", "children", allow_duplicate=True),
        Output("stock-quote-stats", "children", allow_duplicate=True),
        Output("watchlist-status", "children", allow_duplicate=True),
        Output("market-refresh-meta", "data", allow_duplicate=True),
    ]

    # Buttons rendered inside callback output reach server callbacks through
    # this gate (see requestSymbol): only real clicks become requests.
    dash_app.clientside_callback(
        ClientsideFunction("stockwatch", "clickRequest"),
        Output("retry-request", "data"),
        Input({"type": "retry-prices", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )

    @dash_app.callback(
        *refresh_outputs,
        Input("market-refresh-interval", "n_intervals"),
        Input("refresh-watchlist", "n_clicks"),
        Input("retry-request", "data"),
        State({"type": "watchlist-quote", "index": ALL}, "id"),
        State("stock-meta", "data"),
        State("market-refresh-meta", "data"),
        prevent_initial_call=True,
    )
    def refresh_prices(_ticks, _manual, _retry, quote_ids, stock_meta, meta):
        trigger, value = _triggered()
        if not value:
            raise PreventUpdate
        return refresh_market(source, [q["index"] for q in quote_ids], stock_meta, meta)


def _register_edit_callbacks(dash_app, source):
    """Watchlist edits and confirmed deletions. Never registered for a
    read-only source, so the demo has no code path that changes anything."""
    dash_app.clientside_callback(
        ClientsideFunction("stockwatch", "toggleCreateForm"),
        Output("new-watchlist-collapse", "is_open"),
        Output("new-watchlist-toggle", "aria-expanded"),
        Input("new-watchlist-toggle", "n_clicks"),
        Input("new-watchlist-cancel", "n_clicks"),
        Input({"type": "open-create-watchlist", "index": ALL}, "n_clicks"),
        State("new-watchlist-collapse", "is_open"),
        prevent_initial_call=True,
    )

    @dash_app.callback(
        Output("watchlist-dropdown", "options", allow_duplicate=True),
        Output("watchlist-dropdown", "value", allow_duplicate=True),
        Output("watchlist-version", "data", allow_duplicate=True),
        Output("new-watchlist-collapse", "is_open", allow_duplicate=True),
        Output("new-watchlist-input", "value"),
        Output("toast-trigger", "data", allow_duplicate=True),
        Input("create-watchlist-button", "n_clicks"),
        Input("new-watchlist-input", "n_submit"),
        State("new-watchlist-input", "value"),
        State("watchlist-version", "data"),
        prevent_initial_call=True,
    )
    def create_watchlist(_clicks, _submit, name, version):
        _, value = _triggered()
        if not value:
            raise PreventUpdate
        nonce = (version or 0) + 1
        try:
            created = source.create_watchlist(name)
        except (WatchlistError, ReadOnlyDemoError) as exc:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                toast(str(exc), "danger", nonce),
            )
        except Exception:
            logger.exception("Failed to create watchlist")
            return (no_update,) * 5 + (toast("Could not create the watchlist.", "danger", nonce),)
        return (
            watchlist_options(source.watchlists()),
            created.id,
            nonce,
            False,
            "",
            toast(f"Created watchlist “{created.name}”.", "success", nonce),
        )

    @dash_app.callback(
        Output("watchlist-version", "data", allow_duplicate=True),
        Output("toast-trigger", "data", allow_duplicate=True),
        Input("add-to-watchlist", "n_clicks"),
        State("stock-symbol-store", "data"),
        State("watchlist-dropdown", "value"),
        State("watchlist-version", "data"),
        prevent_initial_call=True,
    )
    def add_to_watchlist(n_clicks, symbol, watchlist_id, version):
        if not n_clicks or not symbol:
            raise PreventUpdate
        return add_symbol_to_watchlist(source, watchlist_id, symbol, version)

    dash_app.clientside_callback(
        ClientsideFunction("stockwatch", "clickRequest"),
        Output("remove-request", "data"),
        Input({"type": "remove-from-watchlist", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )

    @dash_app.callback(
        Output("watchlist-version", "data", allow_duplicate=True),
        Output("toast-trigger", "data", allow_duplicate=True),
        Input("remove-request", "data"),
        State("watchlist-dropdown", "value"),
        State("watchlist-version", "data"),
        prevent_initial_call=True,
    )
    def remove_from_watchlist(click, watchlist_id, version):
        if not click:
            raise PreventUpdate
        return remove_symbol_from_watchlist(source, watchlist_id, click["index"], version)

    # --- confirmation for destructive actions ------------------------------
    dash_app.clientside_callback(
        ClientsideFunction("stockwatch", "clickRequest"),
        Output("delete-request", "data"),
        Input({"type": "delete-watchlist", "index": ALL}, "n_clicks"),
        Input({"type": "delete-transaction", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )

    @dash_app.callback(
        Output("confirm-modal", "is_open"),
        Output("confirm-title", "children"),
        Output("confirm-body", "children"),
        Output("pending-action", "data"),
        Input("delete-request", "data"),
        prevent_initial_call=True,
    )
    def ask_to_confirm(click):
        if not click:
            raise PreventUpdate
        prompt = confirmation_prompt(source, click["type"], click["index"])
        if prompt is None:
            raise PreventUpdate
        title, body, pending = prompt
        return True, title, body, pending

    dash_app.clientside_callback(
        ClientsideFunction("stockwatch", "cancelConfirm"),
        Output("confirm-modal", "is_open", allow_duplicate=True),
        Output("pending-action", "data", allow_duplicate=True),
        Input("confirm-cancel", "n_clicks"),
        prevent_initial_call=True,
    )

    @dash_app.callback(
        Output("confirm-modal", "is_open", allow_duplicate=True),
        Output("pending-action", "data", allow_duplicate=True),
        Output("watchlist-dropdown", "options", allow_duplicate=True),
        Output("watchlist-dropdown", "value", allow_duplicate=True),
        Output("watchlist-version", "data", allow_duplicate=True),
        Output("portfolio-refresh", "data", allow_duplicate=True),
        Output("toast-trigger", "data", allow_duplicate=True),
        Input("confirm-accept", "n_clicks"),
        State("pending-action", "data"),
        State("watchlist-dropdown", "value"),
        State("watchlist-version", "data"),
        State("portfolio-refresh", "data"),
        prevent_initial_call=True,
    )
    def confirm_delete(n_clicks, pending, watchlist_id, version, portfolio_version):
        if not n_clicks or not pending:
            raise PreventUpdate
        return perform_confirmed_delete(source, pending, watchlist_id, version, portfolio_version)


# ============================================================
# Mounting
# ============================================================


_EXTERNAL_STYLESHEETS = [
    dbc.themes.BOOTSTRAP,
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap",
]


def create_dash_app(flask_app, source=None, url_base_pathname="/dash/", title="StockWatch"):
    """Mount one dashboard on `flask_app`. Defaults to the signed-in app."""
    source = source or LiveSource()
    dash_app = dash.Dash(
        __name__,
        server=flask_app,
        url_base_pathname=url_base_pathname,
        external_stylesheets=_EXTERNAL_STYLESHEETS,
        assets_folder="assets",
        suppress_callback_exceptions=True,
        title=title,
        # The tab title stays put while callbacks run (5-minute refreshes
        # would otherwise flash "Updating..." in the browser tab)
        update_title=None,
        index_string=INDEX_STRING,
        meta_tags=[
            {"name": "viewport", "content": "width=device-width, initial-scale=1"},
            {"name": "theme-color", "content": "#0B0F17"},
        ],
    )
    dash_app.layout = lambda: build_layout(source)
    register_callbacks(dash_app, source)
    register_portfolio_callbacks(dash_app, source)
    return dash_app


def create_demo_app(flask_app, url_base_pathname="/demo/"):
    """Mount the public, read-only demo on fixed sample data.

    The demo app only registers read-only callbacks. A request naming any
    other callback — a hand-built attempt to create, edit, or delete — is
    rejected with 403 before Dash sees it, instead of surfacing as a 500.
    """
    dash_app = create_dash_app(
        flask_app,
        source=SampleSource(),
        url_base_pathname=url_base_pathname,
        title="StockWatch demo — sample data",
    )
    update_path = f"{url_base_pathname}_dash-update-component"

    @flask_app.before_request
    def reject_unknown_demo_callbacks():
        if request.path != update_path or request.method != "POST":
            return None
        body = request.get_json(silent=True)
        output = body.get("output") if isinstance(body, dict) else None
        if output not in dash_app.callback_map:
            return jsonify({"error": "The demo is read-only."}), 403
        return None

    return dash_app
