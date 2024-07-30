import dash
from dash import html, dcc, Input, Output, State, callback_context, no_update
import dash_bootstrap_components as dbc
from flask import Flask
import plotly.graph_objs as go
from polygon import RESTClient
from datetime import datetime, timedelta
import pandas as pd
import os
from app import cache, db
from flask_login import current_user
from app.models import Watchlist, Stock
from sqlalchemy.exc import SQLAlchemyError
import json

polygon_api_key = os.getenv('POLYGON_API_KEY')
client = RESTClient(polygon_api_key)

flask_app = Flask(__name__)


def create_dash_app(flask_app):
    dash_app = dash.Dash(__name__, server=flask_app, url_base_pathname='/dash/',
                         external_stylesheets=[dbc.themes.BOOTSTRAP])

    dash_app.layout = dbc.Container([
        html.H2('Welcome to Your StockWatch Dashboard, willa33',
                className='text-center my-4'),
        dbc.Row([
            dbc.Col([
                html.H3('Your Stock Dashboard', className='text-center my-4'),
                dbc.InputGroup([
                    dbc.Input(id='stock-input', type='text',
                              placeholder='Enter a stock ticker...'),
                    dbc.InputGroupText(dbc.Button(
                        'Search', id='search-button', color='primary'))
                ], className='mb-4'),
                html.Div(id='stock-data', className='mb-4'),
                html.Div(id='watchlist-section')
            ], md=4),
            dbc.Col([
                dcc.Graph(id='stock-chart')
            ], md=8)
        ]),
        dcc.Interval(
            id='watchlist-interval',
            interval=5*1000,  # in milliseconds, updates every 5 seconds
            n_intervals=0
        )
    ], fluid=True)

    @dash_app.callback(
        Output('watchlist-dropdown', 'options'),
        Input('watchlist-interval', 'n_intervals')
    )
    def update_watchlist_dropdown(n_intervals):
        if current_user.is_authenticated:
            watchlists = current_user.watchlists.all()
            return [{'label': w.name, 'value': w.id} for w in watchlists]
        return []

    @dash_app.callback(
        Output('watchlist-section', 'children'),
        Input('watchlist-dropdown', 'value'),
        Input('watchlist-interval', 'n_intervals')
    )
    def update_watchlist_section(watchlist_id, n_intervals):
        if current_user.is_authenticated:
            watchlists = current_user.watchlists.all()
            watchlist_options = [{'label': w.name, 'value': w.id}
                                 for w in watchlists]

            watchlist_dropdown = dcc.Dropdown(
                id='watchlist-dropdown', options=watchlist_options, className='mb-2')
            create_watchlist_input = dbc.Input(
                id='new-watchlist-input', type='text', placeholder='Enter a new watchlist name...', className='mb-2')
            create_watchlist_button = dbc.Button(
                'Create Watchlist', id='create-watchlist-button', color='primary', className='mb-4')

            if watchlist_id:
                watchlist = Watchlist.query.get(watchlist_id)
                if watchlist:
                    watchlist_content = dbc.Card([
                        dbc.CardHeader(
                            html.H4(f"Watchlist: {watchlist.name}")),
                        dbc.CardBody(
                            dbc.ListGroup([
                                dbc.ListGroupItem([
                                    dbc.Row([
                                        dbc.Col(
                                            html.Div(stock.symbol), width=2),
                                        dbc.Col(html.Div(stock.name), width=10)
                                    ])
                                ]) for stock in watchlist.stocks
                            ])
                        )
                    ])
                else:
                    watchlist_content = html.P(
                        "Select a watchlist to view stocks or create a new watchlist.")
            else:
                watchlist_content = html.P(
                    "Select a watchlist to view stocks or create a new watchlist.")

            return html.Div([watchlist_dropdown, create_watchlist_input, create_watchlist_button, watchlist_content])

        return html.P("Please log in to view your watchlists.")

    @dash_app.callback(
        [Output('stock-data', 'children'),
         Output('stock-chart', 'figure')],
        [Input('search-button', 'n_clicks')],
        [State('stock-input', 'value')]
    )
    def update_stock_data(n_clicks, ticker):
        ctx = callback_context
        if not ctx.triggered:
            return html.Div("Enter a stock ticker and click 'Search'"), go.Figure()

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'search-button' and ticker:
            try:
                details = client.get_ticker_details(ticker)
                end_date = datetime.now()
                start_date = end_date - timedelta(days=365)
                aggs = client.get_aggs(ticker, 1, "day", start_date.strftime(
                    "%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

                df = pd.DataFrame([agg.__dict__ for agg in aggs])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

                week_52_high = df['high'].max()
                week_52_low = df['low'].min()

                latest_day = aggs[-1]
                previous_day = aggs[-2]

                logo_url = f"{details.branding.logo_url}?apiKey={polygon_api_key}" if hasattr(
                    details, 'branding') and hasattr(details.branding, 'logo_url') else ''
                stock_info = dbc.Card([
                    dbc.CardBody([
                        html.Img(src=logo_url,
                                 alt=f"{details.name} logo",
                                 style={'height': '50px', 'marginBottom': '10px'}) if logo_url else None,
                        html.H4(f"{details.name} ({ticker})",
                                className='card-title'),
                        html.P(details.description, className='card-text') if hasattr(
                            details, 'description') else None,
                        html.P(f"Market Cap: ${
                               details.market_cap:,.2f}", className='card-text') if hasattr(details, 'market_cap') else None,
                        html.P(f"52 Week Range: ${
                               week_52_low:.2f} - ${week_52_high:.2f}", className='card-text'),
                        html.P(f"Open: ${latest_day.open:.2f}",
                               className='card-text'),
                        html.P(f"Previous Close: ${
                            previous_day.close:.2f}", className='card-text'),
                        dbc.Button('Add to Watchlist', id={
                            'type': 'add-to-watchlist', 'index': ticker}, color='success')
                    ])
                ])

                fig = go.Figure()

                fig.add_trace(go.Scatter(x=df['timestamp'], y=df['close'],
                                         mode='lines', name='Close Price'))

                fig.update_layout(title=f"{ticker} Stock Price",
                                  xaxis_title='Date',
                                  yaxis_title='Price',
                                  height=600)

                return stock_info, fig

            except Exception as e:
                return html.Div(f"An error occurred: {str(e)}"), go.Figure()

        return html.Div("Enter a stock ticker and click 'Search'"), go.Figure()

    @dash_app.callback(
        [Output({'type': 'add-to-watchlist', 'index': dash.ALL}, 'children'),
         Output('selected-watchlist-content', 'children')],
        [Input({'type': 'add-to-watchlist', 'index': dash.ALL}, 'n_clicks')],
        [State({'type': 'add-to-watchlist', 'index': dash.ALL}, 'id'),
         State('watchlist-dropdown', 'value')],
        prevent_initial_call=True
    )
    def add_to_watchlist(n_clicks, id, watchlist_id):
        if current_user.is_authenticated and n_clicks and any(n_clicks):
            ctx = callback_context
            button_id = ctx.triggered[0]['prop_id'].split('.')[0]
            try:
                ticker = json.loads(button_id.replace("'", "\""))['index']
            except json.JSONDecodeError:
                return [no_update] * len(id), "Error: Invalid button ID"

            if not watchlist_id:
                return [dbc.Button('Select a Watchlist', color='warning', disabled=True) if i['index'] == ticker else no_update for i in id], "Please select a watchlist"

            try:
                watchlist = Watchlist.query.get(watchlist_id)
                stock = Stock.query.filter_by(symbol(ticker)).first()
                if not stock:
                    # If the stock doesn't exist, create it
                    # For now, we'll just use the ticker as the name as well
                    stock = Stock(symbol=ticker, name=ticker)
                    db.session.add(stock)

                if watchlist and stock:
                    if stock not in watchlist.stocks:
                        watchlist.stocks.append(stock)
                        db.session.commit()
                        # After adding the stock to the watchlist, display the updated watchlist
                        return [dbc.Button('Added', color='success', disabled=True) if i['index'] == ticker else no_update for i in id], \
                            html.Div([
                                html.H4(f"Watchlist: {watchlist.name}"),
                                dbc.ListGroup([
                                    dbc.ListGroupItem(f"{s.symbol} - {s.name}") for s in watchlist.stocks
                                ])
                            ])
                    else:
                        return [dbc.Button('Already in Watchlist', color='info', disabled=True) if i['index'] == ticker else no_update for i in id], \
                            html.Div([
                                html.H4(f"Watchlist: {watchlist.name}"),
                                dbc.ListGroup([
                                    dbc.ListGroupItem(f"{s.symbol} - {s.name}") for s in watchlist.stocks
                                ])
                            ])
                else:
                    return [dbc.Button(f'Error: Stock or Watchlist not found', color='danger', disabled=True) if i['index'] == ticker else no_update for i in id], "Error: Stock or Watchlist not found"
            except SQLAlchemyError as e:
                db.session.rollback()
                return [dbc.Button(f'Error: {str(e)}', color='danger', disabled=True) if i['index'] == ticker else no_update for i in id], f"Error: {str(e)}"

        return [no_update] * len(id), no_update

    @dash_app.callback(
        [Output('watchlist-dropdown', 'value'),
         Output('new-watchlist-input', 'value')],
        [Input('create-watchlist-button', 'n_clicks')],
        [State('new-watchlist-input', 'value')]
    )
    def create_watchlist(n_clicks, watchlist_name):
        if current_user.is_authenticated and n_clicks and watchlist_name:
            try:
                watchlist = Watchlist(
                    name=watchlist_name, user_id=current_user.id)
                db.session.add(watchlist)
                db.session.commit()
                return watchlist.id, ''
            except SQLAlchemyError as e:
                db.session.rollback()
                return no_update, no_update

        return no_update, no_update

    return dash_app
