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
from dash import dash_table

# Define color scheme (using values from custom.css)
COLORS = {
    'primary': '#3498db',
    'secondary': '#ecf0f1',
    'text': '#2c3e50',
    'positive': '#2ecc71',
    'negative': '#e74c3c',
    'background': '#f9f9f9',
    'card': '#ffffff'
}

# Define custom styles (integrating with custom.css)
CUSTOM_STYLES = {
    'card': {
        'borderRadius': '10px',
        'marginBottom': '20px',
        'transition': 'all 0.3s ease'
    },
    'button': {
        'borderRadius': '5px',
        'transition': 'all 0.3s ease'
    }
}


def create_stock_card(title, value, change):
    return dbc.Card([
        dbc.CardBody([
            html.H4(title, className="card-title"),
            html.H2(value, className="mb-2"),
            html.P(change, className=f"{
                   'text-success' if float(change.strip('%')) > 0 else 'text-danger'}")
        ])
    ], className='card')  # Using the 'card' class from custom.css


def create_watchlist_table(data):
    return dash_table.DataTable(
        data=data,
        columns=[
            {"name": "Symbol", "id": "symbol"},
            {"name": "Company", "id": "company"},
            {"name": "Price", "id": "price"},
            {"name": "Change", "id": "change"}
        ],
        style_cell={'textAlign': 'left'},
        style_data_conditional=[
            {
                'if': {'column_id': 'change', 'filter_query': '{change} > 0'},
                'color': COLORS['positive']
            },
            {
                'if': {'column_id': 'change', 'filter_query': '{change} < 0'},
                'color': COLORS['negative']
            }
        ],
        style_header={
            'backgroundColor': COLORS['secondary'],
            'fontWeight': 'bold'
        },
        style_table={'overflowX': 'auto'}
    )


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Polygon client
polygon_api_key = os.getenv('POLYGON_API_KEY')
client = RESTClient(api_key=polygon_api_key)


def create_dash_app(flask_app):
    dash_app = dash.Dash(__name__, server=flask_app, url_base_pathname='/dash/',
                         external_stylesheets=[
                             dbc.themes.BOOTSTRAP, '/assets/custom.css'],
                         assets_folder='assets')

    dash_app.layout = create_layout()

    register_callbacks(dash_app)

    return dash_app


def create_layout():
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.H2(id='welcome-message',
                            className='text-center mb-3'),
                    html.H3('Your Stock Dashboard',
                            className='text-center mb-4')
                ], className='stock-dashboard')
            ], width=12)
        ]),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        dbc.InputGroup([
                            dbc.Input(id='stock-input', type='text',
                                      placeholder='Enter a stock ticker...'),
                            dbc.InputGroupText(dbc.Button(
                                'Search', id='search-button', color='primary'))
                        ], className='mb-3'),
                        html.Div(id='stock-data')
                    ])
                ], className='mb-4'),
                html.Div(id='watchlist-section', children=[
                    dcc.Dropdown(id='watchlist-dropdown', options=[],
                                 placeholder='Select a watchlist', className='mb-2'),
                    dbc.Input(id='new-watchlist-input', type='text',
                              placeholder='Enter a new watchlist name...', className='mb-2'),
                    dbc.Button('Create Watchlist', id='create-watchlist-button',
                               color='primary', className='mb-3')
                ])
            ], md=4, className='mb-4'),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        dcc.Graph(id='stock-chart')
                    ])
                ])
            ], md=8)
        ]),
        dcc.Interval(id='watchlist-interval', interval=5*1000, n_intervals=0)
    ], fluid=True, className='py-4')


def register_callbacks(dash_app):
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
            if add_clicks is not None and any(click is not None and click > 0 for click in add_clicks):
                return add_stock_to_watchlist(button_id, current_watchlist_id, add_ids)
        elif 'remove-from-watchlist' in trigger_id:
            button_id = json.loads(trigger_id)
            return remove_stock_from_watchlist(button_id, current_watchlist_id, add_ids)
        elif trigger_id == 'watchlist-dropdown':
            return update_watchlist_section(selected_watchlist_id), selected_watchlist_id, [no_update] * len(add_ids)

        return no_update, no_update, [no_update] * len(add_ids)

    @dash_app.callback(
        [Output('stock-data', 'children'),
         Output('stock-chart', 'figure'),
         Output('stock-input', 'value')],
        [Input({'type': 'watchlist-stock', 'index': ALL}, 'n_clicks'),
         Input('search-button', 'n_clicks')],
        [State({'type': 'watchlist-stock', 'index': ALL}, 'id'),
         State('stock-input', 'value')]
    )
    def update_stock_data(watchlist_clicks, search_clicks, watchlist_stock_ids, search_input):
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if 'watchlist-stock' in trigger_id:
            clicked_stock = json.loads(trigger_id)['index']
        elif trigger_id == 'search-button':
            clicked_stock = search_input
        else:
            return no_update, no_update, no_update

        if not clicked_stock:
            return html.Div("Enter a stock ticker and click 'Search'"), go.Figure(), no_update

        stock_info, chart = fetch_and_display_stock_data(clicked_stock)
        return stock_info, chart, clicked_stock


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
    logger.info(f"Adding stock {stock_symbol} to watchlist {watchlist_id}")
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
        logger.info(f"Creating new stock: {stock_symbol}")
        stock_details = client.get_ticker_details(stock_symbol)
        stock_name = stock_details.name if hasattr(
            stock_details, 'name') else stock_symbol
        stock = Stock(symbol=stock_symbol, name=stock_name)
        db.session.add(stock)
        db.session.commit()
        logger.info(f"Stock created: {stock_symbol} - {stock_name}")
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
            print(watchlist_content)
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
            html.H4(watchlist.name, className="text-center")),
        dbc.CardBody([
            dbc.ListGroup([
                dbc.ListGroupItem
                (
                    [
                        html.Span(stock.symbol, id={
                                  'type': 'watchlist-stock', 'index': stock.symbol}, style={'cursor': 'pointer'}),
                        html.Span(f" ({stock.name})", className='text-muted'),
                        dbc.Button('Remove', id={
                                   'type': 'remove-from-watchlist', 'index': stock.id}, color='danger', size='sm', className='float-end')
                    ]
                ) for stock in watchlist.stocks
            ], flush=True) if watchlist.stocks else html.P("No stocks added yet.")
        ])
    ])


def fetch_and_display_stock_data(stock_symbol):
    try:
        # Fetch stock data from Polygon API
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        logger.info(f"Fetching stock data for {stock_symbol} from {
                    start_date.date()} to {end_date.date()}")
        daily_aggs = client.get_daily_open_close_agg(
            stock_symbol, start_date.date(), end_date.date())

        # Process stock data for chart
        df = pd.DataFrame(daily_aggs)
        df['date'] = pd.to_datetime(df['from'], unit='ms')
        chart = go.Figure(data=[go.Candlestick(x=df['date'],
                                               open=df['open'],
                                               high=df['high'],
                                               low=df['low'],
                                               close=df['close'])])
        chart.update_layout(title=f"{stock_symbol} Stock Price",
                            xaxis_title="Date",
                            yaxis_title="Price")

        # Fetch current price and calculate change
        current_price = client.get_last_trade(stock_symbol).price
        previous_close = df['close'].iloc[-2] if len(df) > 1 else current_price
        change = (current_price - previous_close) / previous_close * 100
        change_str = f"{change:.2f}%"

        # Create stock cards
        stock_cards = dbc.Row([
            dbc.Col(create_stock_card("Current Price", f"${
                    current_price:.2f}", change_str), md=4),
            dbc.Col(create_stock_card("Previous Close",
                    f"${previous_close:.2f}", ""), md=4),
            dbc.Col(create_stock_card("Change", change_str, ""), md=4)
        ], className="mb-4")

        # Add to Watchlist button
        add_to_watchlist_button = dbc.Button(
            "Add to Watchlist",
            id={'type': 'add-to-watchlist', 'index': stock_symbol},
            color='primary',
            className='mb-3'
        )

        return html.Div([stock_cards, add_to_watchlist_button]), chart
    except Exception as e:
        logger.error(f"Error fetching stock data: {str(e)}")
        return html.Div(f"Error fetching data for {stock_symbol}"), go.Figure()
