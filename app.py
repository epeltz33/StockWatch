from flask import Flask, render_template
import dash
from dash import dcc
from dash import html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import pandas as pd
import requests
import pickle
from components import navbar, layout


# Flask setup
server = Flask(__name__)


@server.route('/')
def hello_world():
    return 'Hello World!'


# Load ticker list
try:
    with open('tickers.pickle', 'rb') as f:
        ticker_list = pickle.load(f)
except FileNotFoundError:
    ticker_list = {}

# Dash setup
app = dash.Dash(__name__, server=server, url_base_pathname='/dash/',
                external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = html.Div([
    dbc.NavbarSimple(
        brand="StockWatch",
        brand_href="#",
        color="primary",
        dark=True,
    ),
    dcc.Dropdown(
        id='ticker-dropdown',
        options=[{'label': name, 'value': ticker}
                 for ticker, name in ticker_list.items()],
        value='AAPL' if 'AAPL' in ticker_list else None,
        multi=False
    ),
    dcc.Graph(id='price-graph'),
    html.Div(id='ticker-data')
])


@app.callback(
    [Output('price-graph', 'figure'),
     Output('ticker-data', 'children')],
    [Input('ticker-dropdown', 'value')]
)
def update_graph(ticker):
    if not ticker:
        return {}, "No ticker selected"

    api_key = 'Aod7ULP46zqcMsvlxoBNWbhkW9nRDlmd'
    url = f'https://api.polygon.io/v1/open-close/{
        ticker}/2023-01-01?adjusted=true&apiKey={api_key}'
    response = requests.get(url).json()

    df = pd.DataFrame([response])
    fig = {
        'data': [{
            'x': df['from'],
            'y': df['close'],
            'type': 'line',
            'name': ticker
        }],
        'layout': {
            'title': ticker
        }
    }

    ticker_info = response
    info = [html.P(f"{key}: {value}") for key, value in ticker_info.items()]

    return fig, info


if __name__ == '__main__':
    app.run_server(debug=True)
