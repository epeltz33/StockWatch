from .dash_app import app  # Import the Dash app instance
from dash.dependencies import Input, Output
import pandas as pd
import requests
from dash import html


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

    if 'error' in response:
        return {}, f"Error: {response['error']}"

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

    ticker_info = [html.P(f"{key}: {value}")
                   for key, value in response.items()]
    return fig, ticker_info
