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
        'boxShadow': '0 4px 8px rgba(0,0,0,0.1)',
        'transition': 'all 0.3s ease'
    },
    'button': {
        'borderRadius': '5px',
        'transition': 'all 0.3s ease'
    },
    'stock_logo': {
        'height': '40px',
        'width': 'auto',
        'marginRight': '15px'
    },
    'stock_header': {
        'display': 'flex',
        'alignItems': 'center',
        'marginBottom': '20px'
    },
    'card_title': {
        'fontSize': '14px',
        'fontWeight': 'bold',
        'color': '#7f8c8d',
        'marginBottom': '10px',
        'textTransform': 'uppercase'
    },
    'card_value': {
        'fontSize': '22px',
        'fontWeight': 'bold',
        'marginBottom': '5px'
    },
    'card_change_positive': {
        'color': COLORS['positive'],
        'fontWeight': 'bold',
        'fontSize': '16px'
    },
    'card_change_negative': {
        'color': COLORS['negative'],
        'fontWeight': 'bold',
        'fontSize': '16px'
    }
}


def create_stock_card(title, value, change=None):
    # Determine style based on change value
    change_style = {}
    if change and change.strip('%'):
        try:
            change_value = float(change.strip('%'))
            change_style = CUSTOM_STYLES['card_change_positive'] if change_value > 0 else CUSTOM_STYLES['card_change_negative']
        except ValueError:
            change_style = {}

    return dbc.Card([
        dbc.CardBody([
            html.Div(title, style=CUSTOM_STYLES['card_title']),
            html.Div(value, style=CUSTOM_STYLES['card_value']),
            html.Div(change, style=change_style) if change is not None else html.Div()
        ], className="text-center")
    ], className='h-100', style=CUSTOM_STYLES['card'])


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
    @dash_app.callback(
        Output('welcome-message', 'children'),
        Input('watchlist-interval', 'n_intervals')
    )
    def update_welcome_message(n_intervals):
        if current_user.is_authenticated:
            return f"Welcome to Your StockWatch Dashboard, {current_user.username}"
        return "Welcome to Your StockWatch Dashboard"

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
        # Get historical data for the past year
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        historical_data = get_stock_data(stock_symbol, start_date, end_date)

        if not historical_data:
            return html.Div(f"No historical data available for {stock_symbol}"), go.Figure()

        # Convert to DataFrame
        df = pd.DataFrame(historical_data)

        # Create candlestick chart using close prices
        if 'close' in df.columns:
            chart = go.Figure(data=[go.Scatter(
                x=df['date'],
                y=df['close'],
                mode='lines',
                line=dict(color=COLORS['primary'], width=2),
                name=f"{stock_symbol} Price"
            )])

            chart.update_layout(
                title=f"{stock_symbol} Stock Price - Past Year",
                xaxis_title="Date",
                yaxis_title="Price ($)",
                template="plotly_white",
                margin=dict(l=40, r=40, t=50, b=40),
                hovermode="x unified",
                paper_bgcolor=COLORS['background'],
                plot_bgcolor=COLORS['background'],
                font=dict(color=COLORS['text']),
                height=500
            )

            # Get current price from service function
            current_price = get_stock_price(stock_symbol)

            # Ensure we have a valid current price
            if current_price is None and not df.empty:
                current_price = df['close'].iloc[-1]
            elif current_price is None:
                current_price = 0

            # Calculate change - SAFELY
            previous_close = current_price  # Default fallback
            change_str = "0.00%"
            change_value = 0

            # Calculate previous close and percent change
            if len(df) > 1 and current_price is not None:
                previous_close = df['close'].iloc[-2]
                # Avoid division by zero
                if previous_close != 0:
                    change_value = ((current_price - previous_close) / previous_close) * 100
                    change_str = f"{change_value:.2f}%"
                else:
                    change_str = "0.00%"

            # Get company details
            company_details = get_company_details(stock_symbol)
            company_name = company_details.get('name', stock_symbol) if company_details else stock_symbol

            # Get company logo
            icon_url = company_details.get('icon_url', "") if company_details else ""
            logo_url = company_details.get('logo_url', "") if company_details else ""

            # Choose the best logo - prefer icon_url if available
            display_logo = icon_url if icon_url else logo_url

            # Use a default image if no logo is available
            if not display_logo:
                display_logo = "/assets/default_stock_icon.png"

            # Calculate 52-week range
            if not df.empty and 'close' in df.columns:
                fifty_two_week_low = df['low'].min() if 'low' in df.columns else df['close'].min()
                fifty_two_week_high = df['high'].max() if 'high' in df.columns else df['close'].max()
                fifty_two_week_range = f"${fifty_two_week_low:.2f} - ${fifty_two_week_high:.2f}"
            else:
                fifty_two_week_range = "N/A"

            # Format market cap
            market_cap = company_details.get('market_cap', "N/A") if company_details else "N/A"
            market_cap_str = "N/A"
            if isinstance(market_cap, (int, float)) and market_cap > 0:
                if market_cap >= 1e12:
                    market_cap_str = f"${market_cap/1e12:.2f} Trillion"
                elif market_cap >= 1e9:
                    market_cap_str = f"${market_cap/1e9:.2f} Billion"
                elif market_cap >= 1e6:
                    market_cap_str = f"${market_cap/1e6:.2f} Million"
                else:
                    market_cap_str = f"${market_cap:,.2f}"

            # Create company header with logo
            company_header = html.Div([
                html.Div([
                    html.Img(src=display_logo, className="company-logo"),
                    html.Div([
                        html.H2(stock_symbol, className="company-symbol"),
                        html.H3(company_name, className="company-name")
                    ])
                ], className="company-header")
            ], className="mb-4")

            # Format website URL
            website = company_details.get('website', None) if company_details else None
            website_display = website if website else "N/A"

            # Format listing date
            list_date = company_details.get('list_date', None) if company_details else None
            list_date_display = list_date if list_date else "N/A"

            # Create a table-like display for company information
            company_info_table = html.Div([
                html.Div([
                    html.Div([
                        html.Div("Description", className="company-info-label"),
                        html.Div(company_details.get('description', "N/A") if company_details else "N/A",
                                className="company-info-value")
                    ], className="company-info-row"),

                    html.Div([
                        html.Div("Market Capitalization", className="company-info-label"),
                        html.Div(market_cap_str, className="company-info-value")
                    ], className="company-info-row"),

                    html.Div([
                        html.Div("Website", className="company-info-label"),
                        html.Div([
                            html.A(website_display, href=website, target="_blank") if website else website_display
                        ], className="company-info-value")
                    ], className="company-info-row"),

                    html.Div([
                        html.Div("List Date", className="company-info-label"),
                        html.Div(list_date_display, className="company-info-value")
                    ], className="company-info-row"),

                    html.Div([
                        html.Div("Listing Exchange", className="company-info-label"),
                        html.Div(company_details.get('exchange', "N/A") if company_details else "N/A",
                                className="company-info-value")
                    ], className="company-info-row")
                ], style={'backgroundColor': 'white', 'borderRadius': '10px', 'boxShadow': '0 2px 6px rgba(0,0,0,0.1)', 'padding': '15px 20px'})
            ], className="mb-4")

            # Create price cards for current price, change, etc.
            price_cards = dbc.Row([
                dbc.Col(create_stock_card("Current Price", f"${current_price:.2f}", change_str), md=4),
                dbc.Col(create_stock_card("Previous Close", f"${previous_close:.2f}"), md=4),
                dbc.Col(create_stock_card("52-Week Range", fifty_two_week_range), md=4)
            ], className="mb-4 g-3")

            # Put it all together
            stock_info = html.Div([
                company_header,
                company_info_table,
                price_cards
            ], className="p-2")

            return stock_info, chart
        else:
            return html.Div(f"Insufficient data for {stock_symbol}"), go.Figure()

    except Exception as e:
        logger.error(f"Error fetching stock data: {str(e)}")
        return html.Div([
            html.H4(f"Error fetching data for {stock_symbol}"),
            html.P(f"Details: {str(e)}")
        ], className="p-3 text-danger"), go.Figure()


def get_stock_data(symbol, start_date, end_date):
    """Fetch historical stock data from Polygon API"""
    try:
        # Use the Polygon API client to get aggregates (historical data)
        aggs = client.get_aggs(
            ticker=symbol,
            multiplier=1,
            timespan="day",
            from_=start_date,
            to=end_date
        )

        # Convert to list of dictionaries
        historical_data = []
        for agg in aggs:
            historical_data.append({
                'date': datetime.fromtimestamp(agg.timestamp/1000).strftime('%Y-%m-%d'),
                'open': agg.open,
                'high': agg.high,
                'low': agg.low,
                'close': agg.close,
                'volume': agg.volume
            })

        return historical_data
    except Exception as e:
        logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
        return []


def get_stock_price(symbol):
    """Fetch current stock price from Polygon API"""
    try:
        # Get the last trade for the symbol
        last_trade = client.get_last_trade(symbol)
        return last_trade.price if last_trade else None
    except Exception as e:
        logger.error(f"Error fetching price for {symbol}: {str(e)}")
        return None


def get_company_details(symbol):
    """Fetch company details from Polygon API"""
    try:
        # Get ticker details
        ticker_details = client.get_ticker_details(symbol)

        # Extract relevant information
        company_details = {
            'name': ticker_details.name if hasattr(ticker_details, 'name') else symbol,
            'description': ticker_details.description if hasattr(ticker_details, 'description') else "",
            'market_cap': ticker_details.market_cap if hasattr(ticker_details, 'market_cap') else None,
            'icon_url': ticker_details.branding.icon_url if hasattr(ticker_details, 'branding') and hasattr(ticker_details.branding, 'icon_url') else None,
            'logo_url': ticker_details.branding.logo_url if hasattr(ticker_details, 'branding') and hasattr(ticker_details.branding, 'logo_url') else None,
            'avg_volume': ticker_details.weighted_shares_outstanding if hasattr(ticker_details, 'weighted_shares_outstanding') else None,
            'website': ticker_details.homepage_url if hasattr(ticker_details, 'homepage_url') else None,
            'list_date': ticker_details.list_date if hasattr(ticker_details, 'list_date') else None,
            'exchange': ticker_details.primary_exchange if hasattr(ticker_details, 'primary_exchange') else None
        }

        # If we get a URL with a {apiKey} parameter, substitute it
        if company_details['icon_url'] and '{apiKey}' in company_details['icon_url']:
            company_details['icon_url'] = company_details['icon_url'].replace('{apiKey}', polygon_api_key)

        if company_details['logo_url'] and '{apiKey}' in company_details['logo_url']:
            company_details['logo_url'] = company_details['logo_url'].replace('{apiKey}', polygon_api_key)

        return company_details
    except Exception as e:
        logger.error(f"Error fetching company details for {symbol}: {str(e)}")
        return None