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
                    html.P(f"Market Cap: ${details.market_cap:,.2f}"),
                    html.P(f"52 Week Range: ${
                           week_52_low:.2f} - ${week_52_high:.2f}"),
                    html.P(f"Open: ${latest_day.open:.2f}"),
                    html.P(f"Previous Close: ${previous_day.close:.2f}")

                ])

                #  dataframe for chart (last 6 months)
                df = pd.DataFrame([{
                    'Date': datetime.fromtimestamp(a.timestamp/1000),
                    'Close': a.close,
                    'Volume': a.volume
                    # Last 180 days (approximately 6 months)
                } for a in aggs[-180:]])

                # Create subplots
                fig = sp.make_subplots(rows=2, cols=1, shared_xaxes=True,
                                       vertical_spacing=0.03,
                                       row_heights=[0.7, 0.3])
                # Add price line
                fig.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['Close'],
                    mode='lines',
                    name='Close Price',
                    line=dict(color='blue')
                ), row=1, col=1)

                # add volume bars
                fig.add_trace(go.Bar(
                    x=df['Date'],
                    y=df['Volume'],
                    name='Volume',
                    marker_color='rgba(0, 0, 255, 0.3)'
                ), row=2, col=1)

                # Update layout
                fig.update_layout(
                    title=f'{ticker} Stock Price and Volume (Last 6 Months)',
                    xaxis_rangeslider_visible=False,
                    height=600,
                    showlegend=False
                )

                # Update y-axes
                fig.update_yaxes(title_text="Price ($)", row=1, col=1)
                fig.update_yaxes(title_text="Volume", row=2, col=1)

                return stock_info, fig

            except Exception as e:
                return f"An error occurred: {str(e)}", go.Figure()

        return "Enter a stock ticker and click 'Search'", go.Figure()

    return dash_app
