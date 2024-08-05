import dash
from dash import html, dcc, Input, Output, State, callback_context, no_update, ALL
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from polygon import RESTClient
from datetime import datetime, timedelta
import pandas as pd
import os
from app import db
from flask_login import current_user
from app.models import Watchlist, Stock
from sqlalchemy.exc import SQLAlchemyError
import logging
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Polygon client
polygon_api_key = os.getenv('POLYGON_API_KEY')
client = RESTClient(api_key=polygon_api_key)


def create_dash_app(flask_app):
    dash_app = dash.Dash(__name__, server=flask_app, url_base_pathname='/dash/',
                         external_stylesheets=[dbc.themes.BOOTSTRAP])

    dash_app.layout = create_layout()

    register_callbacks(dash_app)

    return dash_app


def create_layout():
    return dbc.Container([
        html.H2(id='welcome-message', className='text-center my-4'),
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
                html.Div(id='watchlist-section', children=[
                    dcc.Dropdown(id='watchlist-dropdown', options=[],
                                 placeholder='Select a watchlist', className='mb-2'),
                    dbc.Input(id='new-watchlist-input', type='text',
                              placeholder='Enter a new watchlist name...', className='mb-2'),
                    dbc.Button('Create Watchlist', id='create-watchlist-button',
                               color='primary', className='mb-4')
                ], className='mt-4')
            ], md=8)
        ]),
        dcc.Interval(id='watchlist-interval', interval=5*1000, n_intervals=0)
    ], fluid=True, className='px-4')


def register_callbacks(dash_app):
    @dash_app.callback(Output('welcome-message', 'children'),
                       Input('watchlist-interval', 'n_intervals'))
    def update_welcome_message(n_intervals):
        if current_user.is_authenticated:
            return f'Welcome to Your StockWatch Dashboard, {current_user.username}'
        return 'Welcome to Your StockWatch Dashboard'

    @dash_app.callback(Output('watchlist-dropdown', 'options'),
                       Input('watchlist-interval', 'n_intervals'))
    def update_watchlist_dropdown(n_intervals):
        if current_user.is_authenticated:
            watchlists = current_user.watchlists.all()
            return [{'label': w.name, 'value': w.id} for w in watchlists]
        return []

    @dash_app.callback(
        [Output('watchlist-section', 'children'),
         Output('watchlist-dropdown', 'value'),
         Output({'type': 'add-to-watchlist', 'index': ALL}, 'children')],
        [Input('create-watchlist-button', 'n_clicks'),
         Input({'type': 'add-to-watchlist', 'index': ALL}, 'n_clicks'),
         Input({'type': 'remove-from-watchlist', 'index': ALL}, 'n_clicks'),
         Input('watchlist-dropdown', 'value')],
        [State('new-watchlist-input', 'value'),
         State('watchlist-dropdown', 'value'),
         State({'type': 'add-to-watchlist', 'index': ALL}, 'id')]
    )
    def update_watchlist(create_clicks, add_clicks, remove_clicks, selected_watchlist_id, new_watchlist_name, current_watchlist_id, add_ids):
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, [no_update] * len(add_ids)

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if trigger_id == 'create-watchlist-button' and new_watchlist_name:
            return create_new_watchlist(new_watchlist_name, add_ids)
        elif 'add-to-watchlist' in trigger_id:
            button_id = json.loads(trigger_id)
            if any(click > 0 for click in add_clicks):
                return add_stock_to_watchlist(button_id, current_watchlist_id, add_ids)
        elif 'remove-from-watchlist' in trigger_id:
            button_id = json.loads(trigger_id)
            return remove_stock_from_watchlist(button_id, current_watchlist_id, add_ids)
        elif trigger_id == 'watchlist-dropdown':
            return update_watchlist_section(selected_watchlist_id), selected_watchlist_id, [no_update] * len(add_ids)

        return no_update, no_update, [no_update] * len(add_ids)

    @dash_app.callback(
        [Output('stock-data', 'children'), Output('stock-chart', 'figure')],
        [Input('search-button', 'n_clicks')],
        [State('stock-input', 'value')]
    )
    def update_stock_data(n_clicks, ticker):
        if not n_clicks or not ticker:
            return html.Div("Enter a stock ticker and click 'Search'"), go.Figure()
        return fetch_and_display_stock_data(ticker)


def create_new_watchlist(new_watchlist_name, add_ids):
    try:
        watchlist = Watchlist(name=new_watchlist_name, user_id=current_user.id)
        db.session.add(watchlist)
        db.session.commit()
        return update_watchlist_section(watchlist.id), watchlist.id, [no_update] * len(add_ids)
    except SQLAlchemyError as e:
        logger.error(f"Error creating watchlist: {str(e)}")
        return no_update, no_update, [no_update] * len(add_ids)


def add_stock_to_watchlist(button_id, watchlist_id, add_ids):
    stock_symbol = button_id['index']
    try:
        stock = Stock.query.filter_by(symbol=stock_symbol).first()
        if not stock:
            stock = create_new_stock(stock_symbol)

        watchlist = Watchlist.query.get(watchlist_id)
        if watchlist and stock not in watchlist.stocks:
            watchlist.stocks.append(stock)
            db.session.commit()
        updated_add_ids = ['Added' if id['index'] ==
                           stock_symbol else no_update for id in add_ids]
        return update_watchlist_section(watchlist_id), watchlist_id, updated_add_ids
    except Exception as e:
        logger.error(f"Error adding stock to watchlist: {str(e)}")
        return no_update, no_update, [no_update] * len(add_ids)


def remove_stock_from_watchlist(button_id, watchlist_id, add_ids):
    stock_id = button_id['index']
    try:
        stock = Stock.query.get(stock_id)
        watchlist = Watchlist.query.get(watchlist_id)
        if watchlist and stock in watchlist.stocks:
            watchlist.stocks.remove(stock)
            db.session.commit()
        return update_watchlist_section(watchlist_id), watchlist_id, [no_update] * len(add_ids)
    except Exception as e:
        logger.error(f"Error removing stock from watchlist: {str(e)}")
        return no_update, no_update, [no_update] * len(add_ids)


def create_new_stock(stock_symbol):
    try:
        stock_details = client.get_ticker_details(stock_symbol)
        stock_name = stock_details.name if hasattr(
            stock_details, 'name') else stock_symbol
        stock = Stock(symbol=stock_symbol, name=stock_name)
        db.session.add(stock)
        db.session.commit()
        return stock
    except Exception as e:
        logger.error(f"Error creating stock: {stock_symbol} - {str(e)}")
        raise


def update_watchlist_section(watchlist_id):
    if not current_user.is_authenticated:
        return html.P("Please log in to view your watchlists.")

    watchlists = current_user.watchlists.all()
    if not watchlists:
        return create_empty_watchlist_section()

    watchlist_options = [{'label': w.name, 'value': w.id} for w in watchlists]
    watchlist_dropdown = dcc.Dropdown(
        id='watchlist-dropdown',
        options=watchlist_options,
        value=watchlist_id,
        className='mb-2'
    )
    create_watchlist_input = dbc.Input(
        id='new-watchlist-input',
        type='text',
        placeholder='Enter a new watchlist name...',
        className='mb-2'
    )
    create_watchlist_button = dbc.Button(
        'Create Watchlist',
        id='create-watchlist-button',
        color='primary',
        className='mb-4'
    )

    if watchlist_id:
        watchlist = Watchlist.query.get(watchlist_id)
        if watchlist:
            watchlist_content = create_watchlist_content(watchlist)
        else:
            watchlist_content = html.P(
                "Select a watchlist to view stocks or create a new watchlist.")
    else:
        watchlist_content = html.P(
            "Select a watchlist to view stocks or create a new watchlist.")

    return html.Div([
        watchlist_dropdown,
        create_watchlist_input,
        create_watchlist_button,
        watchlist_content
    ])


def create_empty_watchlist_section():
    return html.Div([
        html.H4("You don't have any watchlists yet."),
        dbc.Input(id='new-watchlist-input', type='text',
                  placeholder='Enter a new watchlist name...', className='mb-2'),
        dbc.Button('Create Watchlist', id='create-watchlist-button',
                   color='primary', className='mb-4')
    ])


def create_watchlist_content(watchlist):
    return dbc.Card([
        dbc.CardHeader(
            html.H4(f"Watchlist: {watchlist.name}", className="text-center")),
        dbc.CardBody([
            dbc.ListGroup([
                dbc.ListGroupItem([
                    dbc.Row([
                        dbc.Col(html.Span(stock.symbol,
                                className="font-weight-bold"), width=3),
                        dbc.Col(html.Span(stock.name), width=7),
                        dbc.Col(
                            dbc.Button(
                                "Remove",
                                color="danger",
                                size="sm",
                                className="float-right",
                                id={'type': 'remove-from-watchlist',
                                    'index': stock.id}
                            ),
                            width=2
                        )
                    ], className="align-items-center")
                ], className="py-2")
                for stock in watchlist.stocks
            ], flush=True)
        ])
    ], className="mb-4")


def fetch_and_display_stock_data(ticker):
    try:
        details = client.get_ticker_details(ticker)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        aggs = client.get_aggs(ticker, 1, "day", start_date.strftime(
            "%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

        if not aggs:
            return html.Div(f"No data available for {ticker}"), go.Figure()

        df = pd.DataFrame(aggs)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        stock_info = create_stock_info_card(details, df, ticker)
        fig = create_stock_chart(df, ticker)

        return stock_info, fig

    except Exception as e:
        logger.error(f"Error fetching stock data for {ticker}: {str(e)}")
        return html.Div(f"An error occurred: {str(e)}"), go.Figure()


def create_stock_info_card(details, df, ticker):
    week_52_high = df['high'].max()
    week_52_low = df['low'].min()
    latest_day = df.iloc[-1]
    previous_day = df.iloc[-2]

    name = getattr(details, 'name', ticker)
    description = getattr(details, 'description', 'No description available')
    market_cap = getattr(details, 'market_cap', 'N/A')
    logo_url = getattr(details.branding, 'logo_url', '') if hasattr(
        details, 'branding') else ''

    if logo_url:
        logo_url = f"{logo_url}?apiKey={polygon_api_key}"

    return dbc.Card([
        dbc.CardBody([
            html.Img(src=logo_url, alt=f"{name} logo", style={
                    'max-width': '100%', 'height': 'auto', 'max-height': '50px', 'marginBottom': '10px'}) if logo_url else None,
            html.H4(f"{name} ({ticker})", className='card-title'),
            html.P(description, className='card-text'),
            html.P(f"Market Cap: ${market_cap:,}" if isinstance(
                market_cap, (int, float)) else f"Market Cap: {market_cap}", className='card-text'),
            html.P(f"52 Week Range: ${
                   week_52_low:.2f} - ${week_52_high:.2f}", className='card-text'),
            html.P(f"Open: ${latest_day['open']:.2f}", className='card-text'),
            html.P(f"Previous Close: ${
                   previous_day['close']:.2f}", className='card-text'),
            dbc.Button('Add to Watchlist',
                       id={'type': 'add-to-watchlist', 'index': ticker},
                       color='success',
                       className='mt-2',
                       n_clicks=0)

        ])
    ])


def create_stock_chart(df, ticker):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['close'], mode='lines', name='Close Price'))
    fig.update_layout(title=f"{ticker} Stock Price",
                      xaxis_title='Date', yaxis_title='Price', height=600)
    return fig
