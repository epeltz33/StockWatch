import dash
from dash import html, dcc, Input, Output, State, callback_context, no_update
import dash_bootstrap_components as dbc
from flask import Flask
import plotly.graph_objs as go
from polygon import RESTClient
from datetime import datetime, timedelta
import pandas as pd
import os
from app import db
from flask_login import current_user
from app.models import Watchlist, Stock
from sqlalchemy.exc import SQLAlchemyError
import json

polygon_api_key = os.getenv('POLYGON_API_KEY')
client = RESTClient(polygon_api_key)

# print(f"Polygon API Key: {polygon_api_key}")  # Debug print


def create_dash_app(flask_app):
    dash_app = dash.Dash(__name__, server=flask_app, url_base_pathname='/dash/',
                         external_stylesheets=[dbc.themes.BOOTSTRAP])

    dash_app.layout = dbc.Container([
        html.H2('Welcome to Your StockWatch Dashboard, willa33',
                className='text-center my-4'),
        dbc.Row([
            dbc.Col([
                html.H3('Your Stock Dashboard', className='text-center mb-4'),
                dbc.InputGroup([
                    dbc.Input(id='stock-input', type='text',
                              placeholder='Enter a stock ticker...'),
                    dbc.InputGroupText(dbc.Button(
                        'Search', id='search-button', color='primary'))
                ], className='mb-4'),
                html.Div(id='stock-data', className='mb-4'),
            ], md=4, className='mb-4'),
            dbc.Col([
                dcc.Graph(id='stock-chart'),
                html.Div(id='watchlist-section', className='mt-4')
            ], md=8)
        ]),
        dcc.Interval(
            id='watchlist-interval',
            interval=5*1000,  # in milliseconds, updates every 5 seconds
            n_intervals=0
        )
    ], fluid=True, className='px-4')

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
        [Output('watchlist-section', 'children'),
         Output({'type': 'add-to-watchlist', 'index': dash.ALL}, 'children'),
         Output('watchlist-dropdown', 'value'),
         Output('new-watchlist-input', 'value')],
        [Input('watchlist-dropdown', 'value'),
         Input('watchlist-interval', 'n_intervals'),
         Input({'type': 'add-to-watchlist', 'index': dash.ALL}, 'n_clicks'),
         Input('create-watchlist-button', 'n_clicks')],
        [State({'type': 'add-to-watchlist', 'index': dash.ALL}, 'id'),
         State('new-watchlist-input', 'value')]
    )
    def update_watchlist(watchlist_id, n_intervals, add_clicks, create_clicks, add_ids, new_watchlist_name):
        ctx = dash.callback_context
        triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if triggered_id == 'watchlist-dropdown' or triggered_id == 'watchlist-interval':
            watchlist_content = update_watchlist_section(
                watchlist_id, n_intervals)
            return watchlist_content, [no_update] * len(add_ids), no_update, no_update
        elif 'add-to-watchlist' in triggered_id:
            add_to_watchlist_result = add_to_watchlist(
                add_clicks, add_ids, watchlist_id)
            return add_to_watchlist_result[1], add_to_watchlist_result[0], no_update, no_update
        elif triggered_id == 'create-watchlist-button':
            if current_user.is_authenticated and create_clicks and new_watchlist_name:
                try:
                    watchlist = Watchlist(
                        name=new_watchlist_name, user_id=current_user.id)
                    db.session.add(watchlist)
                    db.session.commit()
                    watchlist_content = update_watchlist_section(
                        watchlist.id, None)
                    return watchlist_content, [no_update] * len(add_ids), watchlist.id, ''
                except SQLAlchemyError as e:
                    db.session.rollback()
                    return no_update, [no_update] * len(add_ids), no_update, no_update

        return no_update, [no_update] * len(add_ids), no_update, no_update

    def update_watchlist_section(watchlist_id, n_intervals):
        if current_user.is_authenticated:
            watchlists = current_user.watchlists.all()

            if not watchlists:
                return html.Div([
                    html.H4("You don't have any watchlists yet."),
                    dbc.Input(id='new-watchlist-input', type='text',
                              placeholder='Enter a new watchlist name...', className='mb-2'),
                    dbc.Button('Create Watchlist', id='create-watchlist-button',
                               color='primary', className='mb-4')
                ])

            watchlist_options = [{'label': w.name, 'value': w.id}
                                 for w in watchlists]

            watchlist_dropdown = dcc.Dropdown(
                id='watchlist-dropdown', options=watchlist_options, value=watchlist_id, className='mb-2')
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
                                        dbc.Col(html.Div(stock.name), width=8),
                                        dbc.Col(
                                            dbc.Button("Remove", color="danger", size="sm", className="float-right",
                                                       id={'type': 'remove-from-watchlist', 'index': stock.id}),
                                            width=2
                                        )
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

    def add_to_watchlist(n_clicks, ids, watchlist_id):
        if current_user.is_authenticated and n_clicks and any(n_clicks):
            ctx = callback_context
            button_id = ctx.triggered[0]['prop_id'].split('.')[0]
            try:
                ticker = json.loads(button_id.replace("'", "\""))['index']
            except json.JSONDecodeError:
                return [no_update] * len(ids), "Error: Invalid button ID"

            if not watchlist_id:
                return [no_update] * len(ids), "Please select a watchlist"

            try:
                watchlist = Watchlist.query.get(watchlist_id)
                stock = Stock.query.filter_by(symbol=ticker).first()
                if not stock:
                    stock = Stock(symbol=ticker, name=ticker)
                    db.session.add(stock)

                if watchlist and stock:
                    if stock not in watchlist.stocks:
                        watchlist.stocks.append(stock)
                        db.session.commit()
                        return [dbc.Button('Added', color='success', disabled=True) if i['index'] == ticker else no_update for i in ids], \
                            update_watchlist_section(watchlist_id, None)
                    else:
                        return [dbc.Button('Already in Watchlist', color='info', disabled=True) if i['index'] == ticker else no_update for i in ids], \
                            update_watchlist_section(watchlist_id, None)
                else:
                    return [dbc.Button('Error: Stock or Watchlist not found', color='danger', disabled=True) if i['index'] == ticker else no_update for i in ids], \
                        "Error: Stock or Watchlist not found"
            except SQLAlchemyError as e:
                db.session.rollback()
                return [dbc.Button(f'Error: {str(e)}', color='danger', disabled=True) if i['index'] == ticker else no_update for i in ids], \
                    f"Error: {str(e)}"

        return [no_update] * len(ids), no_update

    @dash_app.callback(
        [Output('stock-data', 'children'),
         Output('stock-chart', 'figure')],
        [Input('search-button', 'n_clicks')],
        [State('stock-input', 'value')]
    )
    def update_stock_data(n_clicks, ticker):
        # print(f"Search button clicked. Ticker: {ticker}")  # Debug print
        ctx = callback_context
        if not ctx.triggered:
            return html.Div("Enter a stock ticker and click 'Search'"), go.Figure()

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'search-button' and ticker:
            try:
                # print(f"Fetching details for {ticker}")  # Debug print
                details = client.get_ticker_details(ticker)
                # print(f"Details fetched: {details}")  # Debug print

                end_date = datetime.now()
                start_date = end_date - timedelta(days=365)
                # print(f"Fetching aggregates from {
                # start_date} to {end_date}")  # Debug print
                aggs = client.get_aggs(ticker, 1, "day", start_date.strftime(
                    "%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
                print(f"Aggregates fetched: {
                      len(aggs)} records")  # Debug print

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
                                 style={'max-width': '100%', 'height': 'auto', 'max-height': '50px', 'marginBottom': '10px'}) if logo_url else None,
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
                            'type': 'add-to-watchlist', 'index': ticker}, color='success', className='mt-2')
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
               # print(f"Error in update_stock_data: {str(e)}")  # Debug print
                return html.Div(f"An error occurred: {str(e)}"), go.Figure()

        return html.Div("Enter a stock ticker and click 'Search'"), go.Figure()

    @dash_app.callback(
        Output({'type': 'remove-from-watchlist', 'index': dash.ALL}, 'children'),
        Input({'type': 'remove-from-watchlist', 'index': dash.ALL}, 'n_clicks'),
        State('watchlist-dropdown', 'value'),
        prevent_initial_call=True
    )
    def remove_from_watchlist(n_clicks, watchlist_id):
        if not current_user.is_authenticated or not any(n_clicks):
            return [no_update] * len(n_clicks)

        ctx = dash.callback_context
        triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
        stock_id = json.loads(triggered_id)['index']

        watchlist = Watchlist.query.get(watchlist_id)
        stock = Stock.query.get(stock_id)

        if watchlist and stock:
            watchlist.stocks.remove(stock)
            db.session.commit()

        return ["Removed" if i+1 == stock_id else no_update for i in range(len(n_clicks))]

    return dash_app
