from dash import Dash, html, dcc, Input, Output, State
import plotly.graph_objs as go
from polygon import RESTClient
from datetime import datetime, timedelta
import pandas as pd
import os
import plotly.subplots as sp

polygon_api_key = os.getenv('POLYGON_API_KEY')
client = RESTClient(polygon_api_key)


def create_dash_app(flask_app):
    dash_app = Dash(__name__, server=flask_app, url_base_pathname='/dash/')

    dash_app.layout = html.Div([
        html.H1('StockWatch Dashboard'),
        html.Div(id='user-info'),
        html.Div([
            dcc.Input(id='stock-input', type='text',
                      placeholder='Enter a stock ticker...'),
            html.Button('Search', id='search-button', n_clicks=0)
        ]),
        html.Div(id='stock-data'),
        dcc.Graph(id='stock-chart')
    ])

    @dash_app.callback(
        [Output('stock-data', 'children'),
         Output('stock-chart', 'figure')],
        [Input('search-button', 'n_clicks')],
        [State('stock-input', 'value')]
    )
    def update_stock_data(n_clicks, ticker):
        if n_clicks > 0 and ticker:
            try:
                # Fetch stock details
                details = client.get_ticker_details(ticker)

                # Fetch stock price data for the last year
                end_date = datetime.now()
                start_date = end_date - timedelta(days=365)
                aggs = client.get_aggs(ticker, 1, "day", start_date.strftime(
                    '%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))

                # Calculate 52-week range
                prices = [a.close for a in aggs]
                week_52_low = min(prices)
                week_52_high = max(prices)

                # Get the most recent trading day's data
                latest_day = aggs[-1]
                previous_day = aggs[-2]

                # stock info
                stock_info = html.Div([
                    html.H2(f"{details.name} ({ticker})"),
                    html.P
                ])
