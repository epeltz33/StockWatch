from dash import dcc
from dash import html
from frontend.components.navbar import create_navbar


def create_layout():
    return html.Div([
        create_navbar(),
        dcc.Dropdown(id='ticker-dropdown', options=[
            {'label': 'AAPL', 'value': 'AAPL'},
            {'label': 'GOOG', 'value': 'GOOG'},
            {'label': 'MSFT', 'value': 'MSFT'}
        ]),
        dcc.Graph(id='price-graph'),
        html.Div(id='ticker-data')
    ])
