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
    change_value = 0
    if change and change.strip('%'):
        try:
            change_value = float(change.strip('%'))
            change_style = {
                'color': COLORS['positive'] if change_value > 0 else COLORS['negative'],
                'fontWeight': 'bold',
                'fontSize': '16px'
            }
        except ValueError:
            change_style = {}

    # Add arrow indicator based on change value
    change_indicator = "▲ " if change_value > 0 else "▼ " if change_value < 0 else ""
    change_display = f"{change_indicator}{change}" if change else ""

    return dbc.Card([
        dbc.CardBody([
            html.Div(title, style={
                'fontSize': '14px',
                'fontWeight': 'bold',
                'color': '#7f8c8d',
                'marginBottom': '10px',
                'textTransform': 'uppercase'
            }),
            html.Div(value, style={
                'fontSize': '22px',
                'fontWeight': 'bold',
                'marginBottom': '5px',
                'whiteSpace': 'nowrap'  # Prevent breaking across lines
            }),
            html.Div(change_display, style=change_style) if change is not None else html.Div()
        ], className="text-center py-3")
    ], className='h-100', style={
        'borderRadius': '10px',
        'boxShadow': '0 4px 8px rgba(0,0,0,0.1)',
        'border': 'none',
        'transition': 'all 0.3s ease',
        'marginBottom': '10px'
    })


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
        # Welcome Section
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.H2(id='welcome-message',
                            className='text-center mb-3'),
                    html.H3('Your Stock Dashboard',
                            className='text-center mb-4')
                ], className='stock-dashboard')
            ], width=12)
        ], className='mb-4'),

        # Main Content Section
        dbc.Row([
            # Left Sidebar
            dbc.Col([
                # Search Section
                dbc.Card([
                    dbc.CardBody([
                        html.H5("Search Stocks", className="card-title mb-3"),
                        dbc.InputGroup([
                            dbc.Input(id='stock-input', type='text',
                                      placeholder='Enter a stock ticker...',
                                      className='form-control'),
                            dbc.InputGroupText(
                                dbc.Button('Search', id='search-button',
                                          color='primary', className='w-100')
                            )
                        ], className='mb-3'),
                        html.Div(id='stock-data')
                    ], className='p-3')
                ], className='mb-4 shadow-sm'),

                # Watchlist Section
                dbc.Card([
                    dbc.CardBody([
                        html.H5("Watchlists", className="card-title mb-3"),
                        dcc.Dropdown(id='watchlist-dropdown',
                                   options=[],
                                   placeholder='Select a watchlist',
                                   className='mb-3'),
                        dbc.InputGroup([
                            dbc.Input(id='new-watchlist-input',
                                      type='text',
                                      placeholder='Enter a new watchlist name...',
                                      className='form-control'),
                            dbc.InputGroupText(
                                dbc.Button('Create',
                                          id='create-watchlist-button',
                                          color='primary',
                                          className='w-100')
                            )
                        ])
                    ], className='p-3')
                ], className='shadow-sm')
            ], md=4, className='mb-4'),

            # Main Content Area
            dbc.Col([
                # Chart Section
                dbc.Card([
                    dbc.CardBody([
                        html.Div(id='stock-chart-container', className='chart-container')
                    ], className='p-3')
                ], className='mb-4 shadow-sm'),

                # Company Info Section
                dbc.Card([
                    dbc.CardBody([
                        html.Div(id='company-info-container', className='company-info-container')
                    ], className='p-3')
                ], className='shadow-sm')
            ], md=8)
        ]),

        # Update Interval
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
         Output('stock-chart-container', 'children'),
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
            return html.Div("Enter a stock ticker and click 'Search'"), html.Div("Please search for a stock to view its chart."), no_update

        stock_info, chart = fetch_and_display_stock_data(clicked_stock)

        # Create chart container with proper styling
        chart_container = html.Div([
            dcc.Graph(
                id='stock-chart',
                figure=chart,
                style={'height': '100%', 'width': '100%'},
                config={
                    'displayModeBar': True,
                    'scrollZoom': True,
                    'responsive': True
                }
            )
        ], className='chart-container')

        return stock_info, chart_container, clicked_stock


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
            return html.Div(f"No historical data available for {stock_symbol}",
                        className="alert alert-warning m-3 p-3"), go.Figure()

        # Convert to DataFrame
        df = pd.DataFrame(historical_data)

        # Create chart using close prices
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
                height=500,
                autosize=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )

            # Add selector buttons without range slider
            chart.update_xaxes(
                rangeselector=dict(
                    buttons=list([
                        dict(count=1, label="1m", step="month", stepmode="backward"),
                        dict(count=6, label="6m", step="month", stepmode="backward"),
                        dict(count=1, label="YTD", step="year", stepmode="todate"),
                        dict(step="all")
                    ]),
                    bgcolor=COLORS['secondary'],
                    activecolor=COLORS['primary'],
                    font=dict(color=COLORS['text'])
                )
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

            # Log the logo URLs for debugging
            logger.info(f"For {stock_symbol} - Icon URL: {icon_url}, Logo URL: {logo_url}")

            # Choose the best logo - prefer icon_url if available
            display_logo = None
            if icon_url:
                display_logo = icon_url
                logger.info(f"Using icon_url for {stock_symbol}")
            elif logo_url:
                display_logo = logo_url
                logger.info(f"Using logo_url for {stock_symbol}")

            # Additional fallback - try to use a public stock logo service if Polygon doesn't provide one
            if not display_logo:
                logger.info(f"No Polygon logo found for {stock_symbol}, trying fallbacks")
                # Try dedicated stock logo service first
                display_logo = f"https://eodhistoricaldata.com/img/logos/US/{stock_symbol}.png"
                logger.info(f"Using EOD logo URL: {display_logo}")

                # Alternative: Try clearbit logo API if we have a website
                if company_details and company_details.get('website'):
                    website = company_details.get('website')
                    if website:
                        if not website.startswith('http'):
                            website = f"https://{website}"
                        try:
                            domain = website.split('//')[1].split('/')[0] if '//' in website else ""
                            if domain:
                                clearbit_logo = f"https://logo.clearbit.com/{domain}?size=60"
                                logger.info(f"Also prepared Clearbit URL as fallback: {clearbit_logo}")
                        except Exception as e:
                            logger.error(f"Error parsing website URL: {str(e)}")

            # Use a default image if no logo is available
            if not display_logo:
                display_logo = "/assets/default_stock_icon.svg"
                logger.info(f"Falling back to default logo for {stock_symbol}")

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

            # Format website URL
            website = company_details.get('website', None) if company_details else None
            website_display = website if website else "N/A"

            # Format listing date
            list_date = company_details.get('list_date', None) if company_details else None
            list_date_display = list_date if list_date else "N/A"

            # Update the stock_info layout with better spacing and responsiveness
            stock_info = html.Div([
                # Company Header
                html.Div([
                    # Logo/Icon
                    html.Div([
                        html.Img(
                            src=display_logo,
                            id="company-logo",
                            alt=stock_symbol,
                            style={
                                'height': '50px',
                                'width': '50px',
                                'objectFit': 'contain',
                                'borderRadius': '4px',
                                'marginRight': '15px',
                                'backgroundColor': '#f5f5f5',
                                'padding': '2px',
                                'border': '1px solid #e0e0e0'
                            },
                            className='company-logo',
                            # Add error handler to use fallback if image fails to load
                            loading_state={'is_loading': True},
                            # Add event handler for image load error
                            n_clicks=0
                        ) if display_logo else html.Div(
                            html.Span(stock_symbol[0].upper(),
                                     style={
                                        'fontSize': '24px',
                                        'fontWeight': 'bold',
                                        'color': 'white',
                                        'backgroundColor': COLORS['primary'],
                                        'borderRadius': '4px',
                                        'padding': '8px 12px',
                                        'display': 'inline-block',
                                        'textAlign': 'center',
                                        'width': '50px',
                                        'height': '50px',
                                        'lineHeight': '34px'
                                     }),
                            style={'marginRight': '15px'}
                        )
                    ], style={'display': 'inline-block', 'verticalAlign': 'middle'}),

                    # Company Name and Symbol
                    html.Div([
                        html.H3(stock_symbol,
                               style={
                                   'margin': '0',
                                   'fontWeight': 'bold',
                                   'fontSize': '24px'
                               }),
                        html.Div(company_name,
                                style={
                                    'fontSize': '16px',
                                    'color': '#666'
                                })
                    ], style={'display': 'inline-block', 'verticalAlign': 'middle'})
                ], style={
                    'display': 'flex',
                    'alignItems': 'center',
                    'marginBottom': '25px',
                    'padding': '0 0 15px 0',
                    'borderBottom': '1px solid #eee'
                }),

                # Price Information Cards
                html.Div([
                    # Current Price Card
                    html.Div([
                        html.Div("CURRENT PRICE", className="label",
                                style={
                                    'fontSize': '12px',
                                    'fontWeight': '600',
                                    'color': '#777',
                                    'textTransform': 'uppercase',
                                    'letterSpacing': '0.5px',
                                    'marginBottom': '5px'
                                }),
                        html.Div(f"${current_price:.2f}", className="value",
                                style={
                                    'fontSize': '22px',
                                    'fontWeight': 'bold',
                                    'whiteSpace': 'nowrap',
                                    'overflow': 'hidden',
                                    'textOverflow': 'ellipsis'
                                }),
                        html.Div([
                            "▲ " if change_value > 0 else "▼ " if change_value < 0 else "",
                            change_str
                        ], style={
                            'color': COLORS['positive'] if change_value > 0 else COLORS['negative'] if change_value < 0 else '#666',
                            'fontSize': '14px',
                            'fontWeight': 'bold',
                            'whiteSpace': 'nowrap'
                        })
                    ], className="price-card", style={
                        'flex': '1',
                        'padding': '15px',
                        'textAlign': 'center',
                        'marginRight': '10px',
                        'backgroundColor': 'white',
                        'borderRadius': '8px',
                        'boxShadow': '0 1px 3px rgba(0,0,0,0.08)'
                    }),

                    # Previous Close Card
                    html.Div([
                        html.Div("PREVIOUS CLOSE", className="label",
                                style={
                                    'fontSize': '12px',
                                    'fontWeight': '600',
                                    'color': '#777',
                                    'textTransform': 'uppercase',
                                    'letterSpacing': '0.5px',
                                    'marginBottom': '5px'
                                }),
                        html.Div(f"${previous_close:.2f}", className="value",
                                style={
                                    'fontSize': '22px',
                                    'fontWeight': 'bold',
                                    'whiteSpace': 'nowrap',
                                    'overflow': 'hidden',
                                    'textOverflow': 'ellipsis'
                                })
                    ], className="price-card", style={
                        'flex': '1',
                        'padding': '15px',
                        'textAlign': 'center',
                        'marginRight': '10px',
                        'marginLeft': '10px',
                        'backgroundColor': 'white',
                        'borderRadius': '8px',
                        'boxShadow': '0 1px 3px rgba(0,0,0,0.08)'
                    }),

                    # 52-Week Range Card
                    html.Div([
                        html.Div("52-WEEK RANGE", className="label",
                                style={
                                    'fontSize': '12px',
                                    'fontWeight': '600',
                                    'color': '#777',
                                    'textTransform': 'uppercase',
                                    'letterSpacing': '0.5px',
                                    'marginBottom': '5px'
                                }),
                        html.Div(fifty_two_week_range, className="value",
                                style={
                                    'fontSize': '18px',
                                    'fontWeight': 'bold',
                                    'whiteSpace': 'nowrap',
                                    'overflow': 'hidden',
                                    'textOverflow': 'ellipsis'
                                })
                    ], className="price-card", style={
                        'flex': '1',
                        'padding': '15px',
                        'textAlign': 'center',
                        'marginLeft': '10px',
                        'backgroundColor': 'white',
                        'borderRadius': '8px',
                        'boxShadow': '0 1px 3px rgba(0,0,0,0.08)'
                    })
                ], style={
                    'display': 'flex',
                    'flexDirection': 'row',
                    'flexWrap': 'wrap',
                    'justifyContent': 'space-between',
                    'marginBottom': '25px',
                    'gap': '10px'
                }),

                # Company Information Table
                html.Table([
                    html.Tbody([
                        # Description row
                        html.Tr([
                            html.Td("Description", style={
                                'fontWeight': 'bold',
                                'width': '25%',
                                'padding': '15px 20px',
                                'verticalAlign': 'top',
                                'borderBottom': '1px solid #eee',
                                'whiteSpace': 'nowrap'
                            }),
                            html.Td(company_details.get('description', "N/A") if company_details else "N/A", style={
                                'padding': '15px 20px',
                                'lineHeight': '1.5',
                                'borderBottom': '1px solid #eee',
                                'wordBreak': 'break-word'
                            })
                        ]),

                        # Market Cap row
                        html.Tr([
                            html.Td("Market Cap", style={
                                'fontWeight': 'bold',
                                'width': '25%',
                                'padding': '15px 20px',
                                'verticalAlign': 'top',
                                'borderBottom': '1px solid #eee',
                                'whiteSpace': 'nowrap'
                            }),
                            html.Td(market_cap_str, style={
                                'padding': '15px 20px',
                                'borderBottom': '1px solid #eee',
                                'whiteSpace': 'nowrap'
                            })
                        ]),

                        # Website row
                        html.Tr([
                            html.Td("Website", style={
                                'fontWeight': 'bold',
                                'width': '25%',
                                'padding': '15px 20px',
                                'verticalAlign': 'top',
                                'borderBottom': '1px solid #eee',
                                'whiteSpace': 'nowrap'
                            }),
                            html.Td([
                                html.A(website_display, href=website, target="_blank", style={
                                    'color': COLORS['primary'],
                                    'textDecoration': 'none',
                                    'wordBreak': 'break-all'
                                }) if website else website_display
                            ], style={
                                'padding': '15px 20px',
                                'borderBottom': '1px solid #eee'
                            })
                        ]),

                        # List Date row
                        html.Tr([
                            html.Td("List Date", style={
                                'fontWeight': 'bold',
                                'width': '25%',
                                'padding': '15px 20px',
                                'verticalAlign': 'top',
                                'borderBottom': '1px solid #eee',
                                'whiteSpace': 'nowrap'
                            }),
                            html.Td(list_date_display, style={
                                'padding': '15px 20px',
                                'borderBottom': '1px solid #eee',
                                'whiteSpace': 'nowrap'
                            })
                        ]),

                        # Exchange row
                        html.Tr([
                            html.Td("Exchange", style={
                                'fontWeight': 'bold',
                                'width': '25%',
                                'padding': '15px 20px',
                                'verticalAlign': 'top',
                                'whiteSpace': 'nowrap'
                            }),
                            html.Td(company_details.get('exchange', "N/A") if company_details else "N/A", style={
                                'padding': '15px 20px',
                                'whiteSpace': 'nowrap'
                            })
                        ])
                    ])
                ], style={
                    'width': '100%',
                    'borderCollapse': 'collapse',
                    'backgroundColor': 'white',
                    'borderRadius': '10px',
                    'boxShadow': '0 2px 10px rgba(0,0,0,0.08)',
                    'overflow': 'hidden'
                })
            ], style={
                'fontFamily': 'Arial, sans-serif',
                'padding': '20px',
                'backgroundColor': '#f9f9f9',
                'borderRadius': '10px',
                'maxWidth': '100%',
                'overflow': 'hidden'
            })

            return stock_info, chart
        else:
            return html.Div(f"Insufficient data for {stock_symbol}", className="alert alert-warning m-3 p-3"), go.Figure()

    except Exception as e:
        logger.error(f"Error fetching stock data: {str(e)}")
        return html.Div([
            html.H4(f"Error fetching data for {stock_symbol}",
                   style={'color': COLORS['negative']}),
            html.P(f"Details: {str(e)}",
                  style={'color': '#666'})
        ], className="alert alert-danger m-3 p-4", style={
            'textAlign': 'center',
            'borderRadius': '10px'
        }), go.Figure()


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
        # Get ticker details with more detailed error logging
        logger.info(f"Fetching ticker details for: {symbol}")

        try:
            ticker_details = client.get_ticker_details(symbol)
            logger.info(f"Successfully received response for {symbol}")
        except Exception as e:
            logger.error(f"Error in API call for {symbol}: {str(e)}")
            ticker_details = None

        # Initialize variables
        icon_url = None
        logo_url = None

        # Debug the response structure
        if ticker_details:
            logger.info(f"Ticker details structure: {type(ticker_details)}")
            if hasattr(ticker_details, '__dict__'):
                logger.info(f"Fields available: {list(ticker_details.__dict__.keys())}")

        # Approach 1: Direct branding access
        if ticker_details and hasattr(ticker_details, 'branding'):
            branding = ticker_details.branding
            logger.info(f"Found branding information: {branding}")

            if isinstance(branding, dict):
                icon_url = branding.get('icon_url')
                logo_url = branding.get('logo_url')
                logger.info(f"From dict: icon_url={icon_url}, logo_url={logo_url}")
            else:
                icon_url = getattr(branding, 'icon_url', None)
                logo_url = getattr(branding, 'logo_url', None)
                logger.info(f"From object: icon_url={icon_url}, logo_url={logo_url}")

        # Approach 2: Access through results
        if not icon_url and ticker_details and hasattr(ticker_details, 'results'):
            results = ticker_details.results
            logger.info(f"Looking in results: {results}")

            if hasattr(results, 'branding'):
                branding = results.branding
                logger.info(f"Found branding in results: {branding}")

                if isinstance(branding, dict):
                    icon_url = branding.get('icon_url')
                    logo_url = branding.get('logo_url')
                else:
                    icon_url = getattr(branding, 'icon_url', None)
                    logo_url = getattr(branding, 'logo_url', None)

        # Approach 3: Try to extract from raw response
        if not icon_url and ticker_details:
            # Try to access the raw response if available
            try:
                if hasattr(ticker_details, 'raw'):
                    raw_data = ticker_details.raw
                    logger.info(f"Examining raw response: {raw_data}")

                    if isinstance(raw_data, dict) and 'branding' in raw_data:
                        branding = raw_data['branding']
                        icon_url = branding.get('icon_url')
                        logo_url = branding.get('logo_url')
                        logger.info(f"From raw data: icon_url={icon_url}, logo_url={logo_url}")
            except Exception as e:
                logger.error(f"Error extracting from raw response: {str(e)}")

        # Insert API key if URLs are found
        if icon_url:
            icon_url = icon_url.replace('{apiKey}', polygon_api_key)
            logger.info(f"Final icon URL after replacement: {icon_url}")

        if logo_url:
            logo_url = logo_url.replace('{apiKey}', polygon_api_key)
            logger.info(f"Final logo URL after replacement: {logo_url}")

        # Extract other company details
        # ... (rest of the function remains the same)

        # Get name from appropriate location depending on response format
        name = symbol
        if hasattr(ticker_details, 'name'):
            name = ticker_details.name
        elif hasattr(ticker_details, 'results') and hasattr(ticker_details.results, 'name'):
            name = ticker_details.results.name

        # Get other attributes, checking both direct and .results paths
        market_cap = None
        if hasattr(ticker_details, 'market_cap'):
            market_cap = ticker_details.market_cap
        elif hasattr(ticker_details, 'results') and hasattr(ticker_details.results, 'market_cap'):
            market_cap = ticker_details.results.market_cap

        website = None
        if hasattr(ticker_details, 'homepage_url'):
            website = ticker_details.homepage_url
        elif hasattr(ticker_details, 'results') and hasattr(ticker_details.results, 'homepage_url'):
            website = ticker_details.results.homepage_url

        list_date = None
        if hasattr(ticker_details, 'list_date'):
            list_date = ticker_details.list_date
        elif hasattr(ticker_details, 'results') and hasattr(ticker_details.results, 'list_date'):
            list_date = ticker_details.results.list_date

        exchange = None
        if hasattr(ticker_details, 'primary_exchange'):
            exchange = ticker_details.primary_exchange
        elif hasattr(ticker_details, 'results') and hasattr(ticker_details.results, 'primary_exchange'):
            exchange = ticker_details.results.primary_exchange

        # Extract description safely
        description = ""
        if hasattr(ticker_details, 'description') and ticker_details.description:
            description = ticker_details.description[:150]
            if len(ticker_details.description) > 150:
                description += "..."
        elif hasattr(ticker_details, 'results') and hasattr(ticker_details.results, 'description'):
            desc = ticker_details.results.description
            if desc:
                description = desc[:150]
                if len(desc) > 150:
                    description += "..."

        company_details = {
            'name': name,
            'description': description,
            'market_cap': market_cap,
            'icon_url': icon_url,
            'logo_url': logo_url,
            'website': website,
            'list_date': list_date,
            'exchange': exchange
        }

        logger.info(f"Final company details for {symbol}: {company_details}")
        return company_details
    except Exception as e:
        logger.error(f"Error fetching company details for {symbol}: {str(e)}")
        return None