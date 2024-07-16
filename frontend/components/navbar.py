
from dash import dcc
from dash import html


def create_navbar():
    navbar = html.Div(
        [
            html.Nav(
                [
                    html.A("Home", href="/", className="nav-link"),
                    html.A("Page 1", href="/page-1", className="nav-link"),
                    html.A("Page 2", href="/page-2", className="nav-link"),
                ],
                className="navbar"
            )
        ],
        className="navbar-container"
    )
    return navbar
