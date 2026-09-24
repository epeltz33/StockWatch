"""Page chrome shared by the signed-in dashboard and the demo.

Header (brand, sample-data badge, section navigation, account controls),
loading affordances (skeletons for the first load, a small "Updating" pill
for refreshes), the delete-confirmation dialog, and the HTML page template.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

SECTIONS = (("market", "Market"), ("portfolio", "Portfolio"))
SAMPLE_BADGE_TEXT = "Sample data · Not live prices"

# dcc.Loading keeps the previous content on screen (instead of hiding it)
# while a callback runs, with the small pill below as the only indicator.
# delay_show skips the indicator entirely for quick, cached updates.
LOADING_KWARGS = {
    "overlay_style": {"visibility": "visible", "opacity": 0.72},
    "delay_show": 250,
    "show_initially": False,
    "parent_className": "sw-loading",
}

INDEX_STRING = """<!DOCTYPE html>
<html lang="en">
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        <a class="skip-link" href="#main-content">Skip to main content</a>
        {%app_entry%}
        <noscript>StockWatch needs JavaScript to show charts and watchlists.</noscript>
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""


def updating_pill():
    return html.Div(
        [html.Span(className="updating-dot"), "Updating"],
        className="updating-pill",
        role="status",
    )


def loading(child, loading_id=None):
    kwargs = dict(LOADING_KWARGS)
    if loading_id:
        kwargs["id"] = loading_id
    return dcc.Loading(children=child, custom_spinner=updating_pill(), **kwargs)


def skeleton_line(width="100%", height="14px", extra_class=""):
    return html.Span(
        className=f"skeleton {extra_class}".strip(),
        style={"width": width, "height": height},
        **{"aria-hidden": "true"},
    )


def skeleton_block(height, extra_class=""):
    return html.Div(
        className=f"skeleton skeleton--block {extra_class}".strip(),
        style={"height": height},
        **{"aria-hidden": "true"},
    )


def header_skeleton():
    return html.Div(
        [
            html.Span(className="skeleton skeleton--logo", **{"aria-hidden": "true"}),
            html.Div(
                [skeleton_line("88px", "20px"), skeleton_line("150px", "12px")],
                className="skeleton-stack",
            ),
        ],
        className="chart-title-group",
    )


def list_skeleton(rows=3):
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [skeleton_line("56px", "14px"), skeleton_line("110px", "11px")],
                        className="skeleton-stack",
                    ),
                    skeleton_line("72px", "16px"),
                ],
                className="skeleton-row",
            )
            for _ in range(rows)
        ],
        className="skeleton-list",
        **{"aria-busy": "true", "aria-label": "Loading"},
    )


def stat_skeleton(cells=6):
    return [
        html.Div(
            [skeleton_line("60%", "10px"), skeleton_line("80%", "16px")],
            className="stat-cell skeleton-cell",
            **{"aria-hidden": "true"},
        )
        for _ in range(cells)
    ]


def nav_button(section, label, active):
    return html.Button(
        label,
        id={"type": "nav-tab", "index": section},
        n_clicks=0,
        type="button",
        className="sw-nav-btn sw-nav-btn--active" if active else "sw-nav-btn",
        **{"aria-controls": f"{section}-panel", "aria-current": "page" if active else "false"},
    )


def build_header(source, account_label=None):
    """Brand, section navigation, and account controls.

    The demo shows the sample-data badge in the header on every section, and
    offers log in / create account in place of the signed-in user's controls.
    """
    brand = html.A(
        [html.Span("▲", className="tick", **{"aria-hidden": "true"}), "StockWatch"],
        href="/",
        className="sw-brand",
        title="StockWatch home",
    )
    nav = html.Nav(
        [nav_button(section, label, section == "market") for section, label in SECTIONS],
        className="sw-nav",
        **{"aria-label": "Dashboard sections"},
    )

    if source.is_sample:
        account = html.Div(
            [
                html.A("Log in", href="/auth/login", className="sw-link-btn"),
                html.A(
                    "Create account",
                    href="/auth/register",
                    className="btn sw-btn--primary sw-btn--sm",
                ),
            ],
            className="sw-account",
        )
        badge = html.Span(SAMPLE_BADGE_TEXT, className="sample-badge", id="sample-badge")
        children = [brand, badge, nav, account]
    else:
        account = html.Div(
            [
                html.Span(account_label or "", className="sw-user", title="Signed in"),
                html.A("Log out", href="/auth/logout", className="btn sw-btn--ghost sw-btn--sm"),
            ],
            className="sw-account",
        )
        children = [brand, nav, account]

    return html.Header(children, className="sw-header")


def confirm_modal():
    """One dialog for every destructive action; the pending target lives in
    the pending-action store until the user confirms or cancels."""
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Confirm", id="confirm-title"), close_button=True),
            dbc.ModalBody(id="confirm-body"),
            dbc.ModalFooter(
                [
                    dbc.Button(
                        "Cancel", id="confirm-cancel", n_clicks=0, className="sw-btn--ghost"
                    ),
                    dbc.Button(
                        "Delete", id="confirm-accept", n_clicks=0, className="sw-btn--destructive"
                    ),
                ]
            ),
        ],
        id="confirm-modal",
        is_open=False,
        centered=True,
        className="sw-modal",
        labelledby="confirm-title",
    )


def toast_container():
    return html.Div(id="toast-container", className="toast-stack", **{"aria-live": "polite"})


def empty_state(icon, message, sub=None, action=None):
    """Muted placeholder shown before a container has been populated by a callback."""
    children = [
        html.Div(icon, className="empty-state-icon", **{"aria-hidden": "true"}),
        html.Div(message, className="empty-state-title"),
    ]
    if sub:
        children.append(html.Div(sub, className="empty-state-sub"))
    if action is not None:
        children.append(html.Div(action, className="empty-state-action"))
    return html.Div(children, className="empty-state")


def toast(message, kind, nonce):
    # nonce forces `toast-trigger` to register a change even if the message
    # text repeats between events.
    return {"message": message, "type": kind, "n": nonce}
