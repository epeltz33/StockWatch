import frontend.callbacks
import html
from flask import Flask, redirect, render_template
import dash
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import pandas as pd
import requests
import pickle
from components import navbar, layout

# Flask setup
server = Flask(__name__)


@server.route('/')
def index():
    return redirect('/dash/')


# Load ticker list
try:
    with open('tickers.pickle', 'rb') as f:
        ticker_list = pickle.load(f)
except FileNotFoundError:
    ticker_list = {}

# Dash setup
app = dash.Dash(__name__, server=server, url_base_pathname='/dash/',
                external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = layout.create_layout()


@app.callback(
    [Output('price-graph', 'figure'), Output('ticker-data', 'children')],
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
    app.run(debug=True)
