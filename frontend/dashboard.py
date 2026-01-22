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

# Define color scheme (modern professional palette)
COLORS = {
    'primary': '#1a91df',
    'primary_dark': '#1574b3',
    'primary_light': '#47a7e6',
    'secondary': '#f1f5f9',
    'text': '#1e293b',
    'text_secondary': '#64748b',
    'text_muted': '#94a3b8',
    'positive': '#10b981',
    'positive_light': '#ecfdf5',
    'negative': '#ef4444',
    'negative_light': '#fef2f2',
    'background': '#f1f5f9',
    'card': '#ffffff',
    'border': '#e2e8f0',
    'accent': '#0891b2'
}

# Define custom styles (modern professional design system)
CUSTOM_STYLES = {
    'card': {
        'borderRadius': '18px',
        'marginBottom': '24px',
        'boxShadow': '0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04)',
        'border': f'1px solid {COLORS["border"]}',
        'transition': 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
        'overflow': 'hidden'
    },
    'button': {
        'borderRadius': '10px',
        'fontWeight': '600',
        'transition': 'all 0.15s cubic-bezier(0.4, 0, 0.2, 1)'
    },
    'stock_logo': {
        'height': '64px',
        'width': '64px',
        'objectFit': 'contain',
        'marginRight': '20px',
        'borderRadius': '14px',
        'backgroundColor': '#ffffff',
        'padding': '8px',
        'border': '2px solid #f1f5f9',
        'boxShadow': '0 1px 3px rgba(15, 23, 42, 0.06)'
    },
    'stock_header': {
        'display': 'flex',
        'alignItems': 'center',
        'marginBottom': '24px'
    },
    'card_title': {
        'fontSize': '13px',
        'fontWeight': '600',
        'color': COLORS['text_secondary'],
        'marginBottom': '8px',
        'textTransform': 'uppercase',
        'letterSpacing': '0.5px'
    },
    'card_value': {
        'fontSize': '28px',
        'fontWeight': '700',
        'marginBottom': '4px',
        'letterSpacing': '-0.5px',
        'color': COLORS['text']
    },
    'card_change_positive': {
        'color': COLORS['positive'],
        'fontWeight': '600',
        'fontSize': '14px',
        'backgroundColor': COLORS['positive_light'],
        'padding': '4px 8px',
        'borderRadius': '6px',
        'display': 'inline-block'
    },
    'card_change_negative': {
        'color': COLORS['negative'],
        'fontWeight': '600',
        'fontSize': '14px',
        'backgroundColor': COLORS['negative_light'],
        'padding': '4px 8px',
        'borderRadius': '6px',
        'display': 'inline-block'
    }
}

def create_stock_card(title, value, change=None):
    """Create a modern, polished stock information card"""
    # Determine style based on change value
    change_style = {}
    change_value = 0
    if change and change.strip('%'):
        try:
            change_value = float(change.strip('%'))
            change_style = CUSTOM_STYLES['card_change_positive'] if change_value > 0 else CUSTOM_STYLES['card_change_negative']
        except ValueError:
            change_style = {}

    # Add arrow indicator based on change value
    change_indicator = "↑ " if change_value > 0 else "↓ " if change_value < 0 else ""
    change_display = f"{change_indicator}{change}" if change else ""

    return html.Div([
        html.Div(title, style=CUSTOM_STYLES['card_title']),
        html.Div(value, style=CUSTOM_STYLES['card_value']),
        html.Div(change_display, style=change_style) if change is not None else html.Div()
    ], style={
        'backgroundColor': COLORS['card'],
        'borderRadius': '14px',
        'padding': '20px',
        'textAlign': 'center',
        'boxShadow': '0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04)',
        'border': f'1px solid {COLORS["border"]}',
        'height': '100%',
        'minHeight': '130px',
        'transition': 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)'
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
        # Main Content Section with better spacing
        dbc.Row([
            # Left Sidebar with enhanced spacing
            dbc.Col([
                # Search Section
                dbc.Card([
                    dbc.CardBody([
                        html.H5("Search Stocks", className="card-title"),
                        dbc.InputGroup([
                            dbc.Input(id='stock-input',
                                    type='text',
                                    placeholder='Enter a stock ticker (e.g., AAPL)...',
                                    className='form-control'),
                            dbc.InputGroupText(
                                dbc.Button('Search',
                                        id='search-button',
                                        color='primary',
                                        className='w-100',
                                        style={'borderRadius': '0 8px 8px 0'})
                            )
                        ], className='mb-3'),
                        html.Div(id='stock-data')
                    ], className='p-4')
                ], className='mb-4', style={'border': 'none', 'boxShadow': 'none'}),

                # Watchlist Section with enhanced spacing
                dbc.Card([
                    dbc.CardBody([
                        html.H5("Watchlists", className="card-title"),
                        dcc.Dropdown(id='watchlist-dropdown',
                                options=[],
                                placeholder='Select a watchlist',
                                className='mb-3',
                                style={'minHeight': '48px'}),
                        dbc.InputGroup([
                            dbc.Input(id='new-watchlist-input',
                                    type='text',
                                    placeholder='Create a new watchlist...',
                                    className='form-control'),
                            dbc.InputGroupText(
                                dbc.Button('Create',
                                        id='create-watchlist-button',
                                        color='primary',
                                        className='w-100',
                                        style={'borderRadius': '0 8px 8px 0'})
                            )
                        ], className='mb-3'),
                        html.Div(id='watchlist-section')
                    ], className='p-4')
                ], style={'border': 'none', 'boxShadow': 'none'})
            ], lg=4, md=12, className='mb-4'),
            dbc.Col([
                # Chart Section
                dbc.Card([
                    dbc.CardBody([
                        html.Div(id='stock-chart-container',
                            className='chart-container',
                            style={'minHeight': '500px'})
                    ], className='p-0')  # Chart container has its own padding
                ], className='mb-4'),

                # Company Info Section
                html.Div(id='company-info-container',
                    className='company-info-container')
            ], lg=8, md=12)
        ], className='g-4'),  # Add gutter spacing between columns

        # Update Interval
        dcc.Interval(id='watchlist-interval', interval=30*1000, n_intervals=0)  # Update every 30 seconds
    ], fluid=True, className='py-4', style={'maxWidth': '1400px'})


def register_callbacks(dash_app):
    @dash_app.callback(
        Output('welcome-message', 'children'),
        Input('watchlist-interval', 'n_intervals')
    )
    def update_welcome_message(n_intervals):
        if current_user.is_authenticated:
            return f"Welcome to Your StockWatch Dashboard, {current_user.username}"


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
        State({'type': 'add-to-watchlist', 'index': ALL}, 'id')]
    )
    def update_watchlist(create_clicks, add_clicks, remove_clicks, selected_watchlist_id, new_watchlist_name, add_ids):
        ctx = callback_context
        triggered_id = ctx.triggered_id

        num_add_buttons = len(add_ids) if add_ids else 0
        no_update_list = [no_update] * num_add_buttons

        # If nothing triggered (initial load), do nothing
        if not triggered_id:
            return no_update, no_update, no_update_list

        # Determine the type of trigger (string or dict for pattern-matching)
        trigger_type = None
        if isinstance(triggered_id, dict) and 'type' in triggered_id:
            trigger_type = triggered_id.get('type')
        elif isinstance(triggered_id, str):
            trigger_type = triggered_id # e.g., 'create-watchlist-button', 'watchlist-dropdown'

        # --- Handle specific triggers ---

        # Case 1: Create Watchlist Button Clicked
        if trigger_type == 'create-watchlist-button' and new_watchlist_name:
            try:
                watchlist = Watchlist(name=new_watchlist_name, user_id=current_user.id)
                db.session.add(watchlist)
                db.session.commit()
                logger.info(f"Created watchlist '{new_watchlist_name}' with id {watchlist.id}")
                # Return updated section, new dropdown value, and no_update for add buttons
                return update_watchlist_section(watchlist.id), watchlist.id, no_update_list
            except SQLAlchemyError as e:
                logger.error(f"Error creating watchlist: {str(e)}")
                # Potentially return an error message to the user here
                return no_update, no_update, no_update_list

        # Case 2: Add Stock Button Clicked
        elif trigger_type == 'add-to-watchlist':
            # triggered_id is the dict {'type': 'add...', 'index': 'STOCK_SYMBOL'}
            stock_symbol = triggered_id['index']

            # Get the specific button's click value from add_clicks
            button_index = next((i for i, btn_id in enumerate(add_ids)
                            if btn_id['index'] == stock_symbol), None)

            # Only proceed if we found the button and it was actually clicked
            if button_index is None or not add_clicks or button_index >= len(add_clicks) or not add_clicks[button_index]:
                logger.info(f"Add to watchlist ignored for {stock_symbol} - no valid click detected")
                return no_update, no_update, no_update_list

            # Ensure a watchlist is selected before adding
            if not selected_watchlist_id:
                logger.warning(f"Attempted to add {stock_symbol} but no watchlist selected.")
                return no_update, no_update, no_update_list

            logger.info(f"Adding stock {stock_symbol} to watchlist {selected_watchlist_id}")
            try:
                # Check if stock is already in the watchlist
                watchlist = Watchlist.query.get(selected_watchlist_id)
                if not watchlist:
                    logger.warning(f"Watchlist {selected_watchlist_id} not found")
                    return no_update, no_update, no_update_list

                existing_stock = Stock.query.filter_by(symbol=stock_symbol).first()
                if existing_stock and existing_stock in watchlist.stocks:
                    logger.info(f"Stock {stock_symbol} already in watchlist {selected_watchlist_id}")
                    return no_update, no_update, no_update_list

                # Create or get the stock
                stock = existing_stock or create_new_stock(stock_symbol)
                if not stock:
                    logger.error(f"Failed to create/get stock {stock_symbol}")
                    return no_update, no_update, no_update_list

                # Add the stock to the watchlist
                watchlist.stocks.append(stock)
                db.session.commit()
                logger.info(f"Successfully added {stock_symbol} to watchlist {selected_watchlist_id}")

                # Update button states
                updated_add_button_texts = []
                for button_state_id in add_ids:
                    if button_state_id['index'] == stock_symbol:
                        updated_add_button_texts.append("Added")
                    else:
                        updated_add_button_texts.append(no_update)

                return update_watchlist_section(selected_watchlist_id), selected_watchlist_id, updated_add_button_texts

            except Exception as e:
                db.session.rollback()
                logger.error(f"Error adding stock {stock_symbol} to watchlist {selected_watchlist_id}: {str(e)}")
                return no_update, no_update, no_update_list

        elif trigger_type == 'remove-from-watchlist':
            # triggered_id is the dict {'type': 'remove...', 'index': STOCK_DB_ID}
            stock_id = triggered_id['index'] # This is the stock's primary key from the DB
            if not selected_watchlist_id:
                logger.warning(f"Attempted to remove stock ID {stock_id} but no watchlist selected.")
                return no_update, no_update, no_update_list

            logger.info(f"Removing stock id {stock_id} from watchlist {selected_watchlist_id}")
            try:
                stock = Stock.query.get(stock_id)
                watchlist = Watchlist.query.get(selected_watchlist_id)
                if watchlist and stock and stock in watchlist.stocks:
                    watchlist.stocks.remove(stock)
                    db.session.commit()
                    logger.info(f"Successfully removed stock id {stock_id} from watchlist {selected_watchlist_id}")
                # Return updated section, same dropdown value, no_update for add buttons
                return update_watchlist_section(selected_watchlist_id), selected_watchlist_id, no_update_list
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error removing stock id {stock_id} from watchlist {selected_watchlist_id}: {str(e)}")
                return no_update, no_update, no_update_list
        elif trigger_type == 'watchlist-dropdown':
            logger.info(f"Watchlist dropdown changed to: {selected_watchlist_id}")
            # *Crucially*, only update the watchlist section and the dropdown value itself.
            # Return no_update for the add_to_watchlist button statuses.
            return update_watchlist_section(selected_watchlist_id), selected_watchlist_id, no_update_list


        logger.debug(f"update_watchlist: No specific action taken for trigger {triggered_id}")
        return no_update, no_update, no_update_list

    @dash_app.callback(
        [Output('stock-data', 'children'),
        Output('stock-chart-container', 'children'),
        Output('stock-input', 'value')],
        [Input({'type': 'load-watchlist-stock', 'index': ALL}, 'n_clicks'),
        Input('search-button', 'n_clicks')],
        [State({'type': 'load-watchlist-stock', 'index': ALL}, 'id'),
        State('stock-input', 'value')]
    )
    def update_stock_data(watchlist_clicks, search_clicks, watchlist_stock_ids, search_input):
        ctx = callback_context
        trigger_source = None # To track 'watchlist' or 'search'

        # Check if the callback was triggered by anything
        if not ctx.triggered or not ctx.triggered[0]:
            # logger.info("update_stock_data: No trigger detected (initial load?)")
            return no_update, no_update, no_update

        # Get the specific property and value that triggered the callback
        triggered_prop = ctx.triggered[0]['prop_id']
        triggered_value = ctx.triggered[0]['value']

        # logger.info(f"update_stock_data: Triggered by prop '{triggered_prop}' with value '{triggered_value}'")

        # --- Check for valid click triggers ---

        # Scenario 1: A watchlist stock span was clicked
        # prop_id will be like '{"index":"AAPL","type":"load-watchlist-stock"}.n_clicks'
        if triggered_prop.endswith('.n_clicks') and '"type":"load-watchlist-stock"' in triggered_prop:
            if triggered_value is not None and triggered_value > 0:
                # Extract the stock symbol (index) from the JSON part of the prop_id
                json_part = triggered_prop.split('.')[0]
                try:
                    clicked_stock_info = json.loads(json_part)
                    clicked_stock = clicked_stock_info.get('index')
                    trigger_source = 'watchlist'
                    # logger.info(f"Watchlist stock click detected for: {clicked_stock}")
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse watchlist trigger prop_id: {triggered_prop}")
                    return no_update, no_update, no_update # Error state
            # else: logger.debug(f"Watchlist view button trigger {triggered_prop} ignored (value <= 0 or None)")


        elif triggered_prop == 'search-button.n_clicks':
            if triggered_value is not None and triggered_value > 0:
                if search_input: # Check if the search box has text
                    clicked_stock = search_input
                    trigger_source = 'search'
                    logger.info(f"Search button clicked for: {clicked_stock}")

        # --- Process if a valid click was identified ---

        if not clicked_stock or not trigger_source:
            # logger.info(f"Callback triggered by '{triggered_prop}', but not processed as a valid click action.")
            # If triggered but not by a valid click, don't change anything.
            return no_update, no_update, no_update

        # logger.info(f"Proceeding to fetch data for {clicked_stock} (Trigger: {trigger_source})")
        stock_info, chart = fetch_and_display_stock_data(clicked_stock)

        # Create chart container with modern styling
        chart_container = html.Div([
            dcc.Graph(
                id='stock-chart',
                figure=chart,
                style={'height': '500px', 'width': '100%'},
                config={
                    'displayModeBar': True,
                    'responsive': True,
                    'displaylogo': False,
                    'modeBarButtonsToRemove': ['lasso2d', 'select2d']
                }
            )
        ], style={
            'backgroundColor': COLORS['card'],
            'borderRadius': '18px',
            'padding': '16px',
            'boxShadow': '0 4px 6px -1px rgba(15, 23, 42, 0.08), 0 2px 4px -2px rgba(15, 23, 42, 0.05)',
            'border': f'1px solid {COLORS["border"]}',
            'marginBottom': '24px'
        })

        # Decide whether to update the stock input field based on the trigger
        stock_input_update = clicked_stock if trigger_source == 'search' else no_update

        return stock_info, chart_container, stock_input_update


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
        html.Div([
            html.Span("📋", style={'fontSize': '36px', 'marginBottom': '16px', 'display': 'block'}),
            html.H4("Create your first watchlist", style={
                'fontWeight': '700',
                'color': COLORS['text'],
                'marginBottom': '8px',
                'fontSize': '18px'
            }),
            html.P("Track your favorite stocks in one place.", style={
                'color': COLORS['text_muted'],
                'fontSize': '14px',
                'marginBottom': '24px'
            })
        ], style={'textAlign': 'center'}),
        dbc.Input(id='new-watchlist-input', type='text',
                placeholder='Enter watchlist name...', className='mb-3'),
        dbc.Button('Create Watchlist', id='create-watchlist-button',
                color='primary', className='w-100', style={
                    'borderRadius': '10px',
                    'padding': '12px 20px',
                    'fontWeight': '600'
                })
    ], style={
        'backgroundColor': COLORS['card'],
        'borderRadius': '18px',
        'padding': '32px 24px',
        'border': f'1px solid {COLORS["border"]}',
        'boxShadow': '0 1px 3px rgba(15, 23, 42, 0.06)'
    })


def create_watchlist_content(watchlist):
    return dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.Div(style={
                    'width': '4px',
                    'height': '20px',
                    'background': f'linear-gradient(180deg, {COLORS["primary"]} 0%, {COLORS["primary_dark"]} 100%)',
                    'borderRadius': '4px',
                    'marginRight': '12px'
                }),
                html.H5(watchlist.name, className="mb-0",
                    style={
                        'fontWeight': '700',
                        'letterSpacing': '-0.3px',
                        'color': COLORS['text'],
                        'fontSize': '16px'
                    })
            ], style={'display': 'flex', 'alignItems': 'center'})
        ], style={
            'padding': '18px 24px',
            'background': f'linear-gradient(180deg, {COLORS["secondary"]} 0%, {COLORS["card"]} 100%)',
            'borderBottom': f'1px solid {COLORS["border"]}'
        }),

        dbc.CardBody([
            dbc.ListGroup([
                dbc.ListGroupItem(
                    html.Div([
                        # Left side: Stock info
                        html.Div([
                            html.Span(stock.symbol,
                                    style={
                                        'fontWeight': '700',
                                        'fontSize': '16px',
                                        'display': 'inline-block',
                                        'marginRight': '10px',
                                        'letterSpacing': '-0.3px',
                                        'color': COLORS['text']
                                    }),
                            html.Span(f"{stock.name}",
                                    style={
                                        'fontSize': '13px',
                                        'fontWeight': '500',
                                        'color': COLORS['text_muted']
                                    })
                        ], style={
                            'flex': '1',
                            'minWidth': '0',
                            'overflow': 'hidden',
                            'textOverflow': 'ellipsis',
                            'whiteSpace': 'nowrap'
                        }),

                        # Right side: Buttons
                        html.Div([
                            dbc.Button(
                                'View',
                                id={'type': 'load-watchlist-stock', 'index': stock.symbol},
                                color='info',
                                size='sm',
                                style={
                                    'borderRadius': '8px',
                                    'padding': '6px 14px',
                                    'fontWeight': '600',
                                    'fontSize': '12px'
                                }
                            ),
                            dbc.Button(
                                'Remove',
                                id={'type': 'remove-from-watchlist', 'index': stock.id},
                                color='danger',
                                size='sm',
                                style={
                                    'borderRadius': '8px',
                                    'padding': '6px 14px',
                                    'fontWeight': '600',
                                    'fontSize': '12px'
                                }
                            )
                        ], style={
                            'display': 'flex',
                            'gap': '8px',
                            'alignItems': 'center'
                        })
                    ], style={
                        'display': 'flex',
                        'justifyContent': 'space-between',
                        'alignItems': 'center',
                        'width': '100%',
                        'gap': '16px'
                    }),
                    className='border-0',
                    style={
                        'padding': '14px 20px',
                        'borderBottom': f'1px solid {COLORS["border"]}',
                        'transition': 'background-color 0.15s ease'
                    }
                ) for stock in watchlist.stocks
            ], flush=True, className='border-0') if watchlist.stocks else
            html.Div([
                html.Div([
                    html.Span("📊", style={'fontSize': '32px', 'marginBottom': '12px', 'display': 'block'}),
                    html.P("No stocks added yet",
                        style={
                            'fontSize': '15px',
                            'fontWeight': '600',
                            'color': COLORS['text'],
                            'marginBottom': '6px'
                        }),
                    html.P("Search for stocks above and add them to your watchlist.",
                        style={
                            'fontSize': '13px',
                            'color': COLORS['text_muted'],
                            'margin': '0'
                        })
                ], style={'textAlign': 'center'})
            ], style={'padding': '40px 20px'})
        ], className='p-0')
    ], style={
        'border': f'1px solid {COLORS["border"]}',
        'borderRadius': '18px',
        'boxShadow': '0 1px 3px rgba(15, 23, 42, 0.06)',
        'overflow': 'hidden'
    })

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

        # Create chart using close prices with modern styling
        if 'close' in df.columns:
            # Create gradient fill effect with scatter
            chart = go.Figure()
            
            # Add gradient area fill
            chart.add_trace(go.Scatter(
                x=df['date'],
                y=df['close'],
                mode='lines',
                line=dict(color=COLORS['primary'], width=2.5, shape='spline'),
                fill='tozeroy',
                fillcolor='rgba(26, 145, 223, 0.08)',
                name=f"{stock_symbol}",
                hovertemplate='<b>%{x}</b><br>$%{y:.2f}<extra></extra>'
            ))

            chart.update_layout(
                title=dict(
                    text=f'<b>{stock_symbol}</b> Stock Price',
                    font=dict(size=20, color=COLORS['text'], family='Inter, -apple-system, sans-serif'),
                    x=0.02,
                    xanchor='left'
                ),
                xaxis_title=None,
                yaxis_title=dict(text="Price ($)", font=dict(size=12, color=COLORS['text_secondary'])),
                template="plotly_white",
                margin=dict(l=60, r=30, t=70, b=50),
                hovermode="x unified",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color=COLORS['text'], family='Inter, -apple-system, sans-serif'),
                height=480,
                autosize=True,
                showlegend=False,
                hoverlabel=dict(
                    bgcolor=COLORS['card'],
                    font_size=14,
                    font_family='Inter, -apple-system, sans-serif',
                    bordercolor=COLORS['border']
                )
            )

            # Style axes
            chart.update_xaxes(
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(226, 232, 240, 0.5)',
                showline=False,
                tickfont=dict(size=11, color=COLORS['text_secondary']),
                rangeselector=dict(
                    buttons=list([
                        dict(count=1, label="1M", step="month", stepmode="backward"),
                        dict(count=3, label="3M", step="month", stepmode="backward"),
                        dict(count=6, label="6M", step="month", stepmode="backward"),
                        dict(count=1, label="YTD", step="year", stepmode="todate"),
                        dict(label="1Y", step="all")
                    ]),
                    bgcolor='rgba(241, 245, 249, 0.8)',
                    activecolor=COLORS['primary'],
                    bordercolor=COLORS['border'],
                    borderwidth=1,
                    font=dict(color=COLORS['text'], size=12),
                    x=0.02,
                    xanchor='left',
                    y=1.12
                ),
                rangeslider=dict(visible=False)
            )
            
            chart.update_yaxes(
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(226, 232, 240, 0.5)',
                showline=False,
                tickfont=dict(size=11, color=COLORS['text_secondary']),
                tickprefix='$',
                tickformat=',.0f'
            )

            # Get current price from service function
            current_price = get_stock_price(stock_symbol)

            # Ensure we have a valid current price
            if current_price is None and not df.empty:
                current_price = df['close'].iloc[-1]
            elif current_price is None:
                current_price = 0

            # Calculate change
            previous_close = current_price  # Default fallback
            change_str = "0.00%"
            change_value = 0
            dollar_change = 0

            # Calculate previous close and percent change
            if len(df) > 1 and current_price is not None:
                previous_close = df['close'].iloc[-2]
                # Avoid division by zero
                if previous_close != 0:
                    change_value = ((current_price - previous_close) / previous_close) * 100
                    dollar_change = current_price - previous_close
                    change_str = f"{change_value:+.2f}%"
                else:
                    change_str = "0.00%"

            # Get company details
            company_details = get_company_details(stock_symbol)
            company_name = company_details.get('name', stock_symbol) if company_details else stock_symbol

            # Get company logo
            icon_url = company_details.get('icon_url', "") if company_details else ""
            logo_url = company_details.get('logo_url', "") if company_details else ""

            # Choose the best logo - prefer icon_url if available
            display_logo = None
            if icon_url:
                display_logo = icon_url
            elif logo_url:
                display_logo = logo_url

            # Additional fallback
            if not display_logo:
                display_logo = f"https://eodhistoricaldata.com/img/logos/US/{stock_symbol}.png"

            # Use a default image if no logo is available
            if not display_logo:
                display_logo = "/assets/default_stock_icon.svg"

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

            # Determine price change styling
            price_change_style = {
                'display': 'inline-flex',
                'alignItems': 'center',
                'gap': '3px',
                'padding': '4px 10px',
                'borderRadius': '6px',
                'fontWeight': '600',
                'fontSize': '13px',
                'verticalAlign': 'middle'
            }
            if change_value > 0:
                price_change_style['backgroundColor'] = COLORS['positive_light']
                price_change_style['color'] = COLORS['positive']
                arrow = "↑"
            elif change_value < 0:
                price_change_style['backgroundColor'] = COLORS['negative_light']
                price_change_style['color'] = COLORS['negative']
                arrow = "↓"
            else:
                price_change_style['backgroundColor'] = COLORS['secondary']
                price_change_style['color'] = COLORS['text_secondary']
                arrow = ""

            # Create modern, professional layout
            stock_info = html.Div([
                # Company Header Card with gradient background and Add to Watchlist button
                html.Div([
                    html.Div([
                        # Left side: Logo and Company Info
                        html.Div([
                            # Logo with modern styling
                            html.Img(
                                src=display_logo,
                                alt=stock_symbol,
                                style=CUSTOM_STYLES['stock_logo'],
                                className='company-logo'
                            ) if display_logo else html.Div(
                                html.Span(stock_symbol[0].upper(),
                                        style={
                                            'fontSize': '28px',
                                            'fontWeight': '700',
                                            'color': 'white'
                                        }),
                                style={
                                    'background': f'linear-gradient(135deg, {COLORS["primary"]} 0%, {COLORS["primary_dark"]} 100%)',
                                    'borderRadius': '14px',
                                    'display': 'flex',
                                    'alignItems': 'center',
                                    'justifyContent': 'center',
                                    'width': '64px',
                                    'height': '64px',
                                    'marginRight': '20px',
                                    'boxShadow': '0 4px 14px rgba(26, 145, 223, 0.3)'
                                }
                            ),
                            # Company Info
                            html.Div([
                                html.H2(stock_symbol, style={
                                    'margin': '0 0 4px 0',
                                    'fontWeight': '700',
                                    'fontSize': '26px',
                                    'letterSpacing': '-0.5px',
                                    'color': COLORS['text']
                                }),
                                html.P(company_name, style={
                                    'margin': '0',
                                    'fontSize': '15px',
                                    'color': COLORS['text_secondary'],
                                    'fontWeight': '500'
                                })
                            ])
                        ], style={
                            'display': 'flex',
                            'alignItems': 'center',
                            'flex': '1'
                        }),
                        # Right side: Add to Watchlist Button
                        html.Div([
                            dbc.Button([
                                html.Span("+ ", style={'fontWeight': '400', 'marginRight': '4px'}),
                                "Add to Watchlist"
                            ],
                                id={'type': 'add-to-watchlist', 'index': stock_symbol},
                                color='success',
                                style={
                                    'borderRadius': '10px',
                                    'padding': '10px 20px',
                                    'fontWeight': '600',
                                    'fontSize': '14px',
                                    'boxShadow': '0 2px 8px rgba(16, 185, 129, 0.3)',
                                    'whiteSpace': 'nowrap'
                                }
                            )
                        ])
                    ], style={
                        'display': 'flex',
                        'alignItems': 'center',
                        'justifyContent': 'space-between',
                        'gap': '16px',
                        'flexWrap': 'wrap'
                    })
                ], style={
                    'background': f'linear-gradient(135deg, {COLORS["card"]} 0%, {COLORS["secondary"]} 100%)',
                    'borderRadius': '18px',
                    'padding': '24px',
                    'marginBottom': '20px',
                    'border': f'1px solid {COLORS["border"]}',
                    'boxShadow': '0 1px 3px rgba(15, 23, 42, 0.06)'
                }),

                # Company Details Card with Current Price at top
                dbc.Card([
                    dbc.CardBody([
                        html.Table([
                            html.Tbody([
                                # Current Price Row (prominent)
                                html.Tr([
                                    html.Td("Current Price", style={
                                        'fontWeight': '600',
                                        'color': COLORS['text_secondary'],
                                        'width': '40%',
                                        'padding': '18px 20px',
                                        'borderBottom': f'1px solid {COLORS["border"]}',
                                        'background': f'linear-gradient(90deg, {COLORS["secondary"]} 0%, {COLORS["card"]} 100%)',
                                        'fontSize': '13px',
                                        'textTransform': 'uppercase',
                                        'letterSpacing': '0.5px'
                                    }),
                                    html.Td([
                                        html.Span(f"${current_price:.2f}", style={
                                            'fontSize': '22px',
                                            'fontWeight': '700',
                                            'color': COLORS['text'],
                                            'letterSpacing': '-0.3px',
                                            'marginRight': '12px'
                                        }),
                                        html.Span([
                                            html.Span(f"{arrow} ", style={'fontSize': '11px'}),
                                            html.Span(f"{dollar_change:+.2f} ({change_str})")
                                        ], style=price_change_style)
                                    ], style={
                                        'padding': '18px 20px',
                                        'borderBottom': f'1px solid {COLORS["border"]}'
                                    })
                                ]),

                                # Previous Close Row
                                html.Tr([
                                    html.Td("Previous Close", style={
                                        'fontWeight': '600',
                                        'color': COLORS['text_secondary'],
                                        'width': '40%',
                                        'padding': '16px 20px',
                                        'borderBottom': f'1px solid {COLORS["border"]}',
                                        'background': f'linear-gradient(90deg, {COLORS["secondary"]} 0%, {COLORS["card"]} 100%)',
                                        'fontSize': '13px',
                                        'textTransform': 'uppercase',
                                        'letterSpacing': '0.5px'
                                    }),
                                    html.Td(f"${previous_close:.2f}", style={
                                        'padding': '16px 20px',
                                        'borderBottom': f'1px solid {COLORS["border"]}',
                                        'fontSize': '15px',
                                        'fontWeight': '500',
                                        'color': COLORS['text']
                                    })
                                ]),

                                # 52-Week Range Row
                                html.Tr([
                                    html.Td("52-Week Range", style={
                                        'fontWeight': '600',
                                        'color': COLORS['text_secondary'],
                                        'width': '40%',
                                        'padding': '16px 20px',
                                        'borderBottom': f'1px solid {COLORS["border"]}',
                                        'background': f'linear-gradient(90deg, {COLORS["secondary"]} 0%, {COLORS["card"]} 100%)',
                                        'fontSize': '13px',
                                        'textTransform': 'uppercase',
                                        'letterSpacing': '0.5px'
                                    }),
                                    html.Td(fifty_two_week_range, style={
                                        'padding': '16px 20px',
                                        'borderBottom': f'1px solid {COLORS["border"]}',
                                        'fontSize': '15px',
                                        'fontWeight': '500',
                                        'color': COLORS['text']
                                    })
                                ]),

                                # Market Cap Row
                                html.Tr([
                                    html.Td("Market Cap", style={
                                        'fontWeight': '600',
                                        'color': COLORS['text_secondary'],
                                        'width': '40%',
                                        'padding': '16px 20px',
                                        'borderBottom': f'1px solid {COLORS["border"]}',
                                        'background': f'linear-gradient(90deg, {COLORS["secondary"]} 0%, {COLORS["card"]} 100%)',
                                        'fontSize': '13px',
                                        'textTransform': 'uppercase',
                                        'letterSpacing': '0.5px'
                                    }),
                                    html.Td(market_cap_str, style={
                                        'padding': '16px 20px',
                                        'borderBottom': f'1px solid {COLORS["border"]}',
                                        'fontSize': '15px',
                                        'fontWeight': '500',
                                        'color': COLORS['text']
                                    })
                                ]),

                                # Exchange Row
                                html.Tr([
                                    html.Td("Exchange", style={
                                        'fontWeight': '600',
                                        'color': COLORS['text_secondary'],
                                        'width': '40%',
                                        'padding': '16px 20px',
                                        'borderBottom': f'1px solid {COLORS["border"]}',
                                        'background': f'linear-gradient(90deg, {COLORS["secondary"]} 0%, {COLORS["card"]} 100%)',
                                        'fontSize': '13px',
                                        'textTransform': 'uppercase',
                                        'letterSpacing': '0.5px'
                                    }),
                                    html.Td(company_details.get('exchange', "N/A") if company_details else "N/A", style={
                                        'padding': '16px 20px',
                                        'borderBottom': f'1px solid {COLORS["border"]}',
                                        'fontSize': '15px',
                                        'fontWeight': '500',
                                        'color': COLORS['text']
                                    })
                                ]),

                                # Website Row
                                html.Tr([
                                    html.Td("Website", style={
                                        'fontWeight': '600',
                                        'color': COLORS['text_secondary'],
                                        'width': '40%',
                                        'padding': '16px 20px',
                                        'borderBottom': f'1px solid {COLORS["border"]}',
                                        'background': f'linear-gradient(90deg, {COLORS["secondary"]} 0%, {COLORS["card"]} 100%)',
                                        'fontSize': '13px',
                                        'textTransform': 'uppercase',
                                        'letterSpacing': '0.5px'
                                    }),
                                    html.Td([
                                        html.A(website_display.replace('https://', '').replace('http://', ''),
                                            href=website,
                                            target="_blank",
                                            style={
                                                'color': COLORS['primary'],
                                                'textDecoration': 'none',
                                                'fontSize': '15px',
                                                'fontWeight': '500',
                                                'transition': 'color 0.15s ease'
                                            }) if website else html.Span("N/A", style={'color': COLORS['text_muted']})
                                    ], style={
                                        'padding': '16px 20px',
                                        'borderBottom': f'1px solid {COLORS["border"]}'
                                    })
                                ]),

                                # Description Row
                                html.Tr([
                                    html.Td("About", style={
                                        'fontWeight': '600',
                                        'color': COLORS['text_secondary'],
                                        'width': '40%',
                                        'padding': '16px 20px',
                                        'background': f'linear-gradient(90deg, {COLORS["secondary"]} 0%, {COLORS["card"]} 100%)',
                                        'fontSize': '13px',
                                        'textTransform': 'uppercase',
                                        'letterSpacing': '0.5px',
                                        'verticalAlign': 'top'
                                    }),
                                    html.Td(company_details.get('description', "N/A") if company_details else "N/A", style={
                                        'padding': '16px 20px',
                                        'fontSize': '14px',
                                        'lineHeight': '1.7',
                                        'color': COLORS['text_secondary']
                                    })
                                ])
                            ])
                        ], style={
                            'width': '100%',
                            'borderCollapse': 'collapse',
                            'margin': '0'
                        })
                    ], className='p-0')
                ], style={
                    'border': f'1px solid {COLORS["border"]}',
                    'boxShadow': '0 1px 3px rgba(15, 23, 42, 0.06)',
                    'borderRadius': '18px',
                    'overflow': 'hidden'
                })
            ])

            return stock_info, chart
        else:
            return html.Div(f"Insufficient data for {stock_symbol}", className="alert alert-warning m-3 p-3"), go.Figure()

    except Exception as e:
        logger.error(f"Error fetching stock data: {str(e)}")
        return html.Div([
            html.Div([
                html.Span("⚠️", style={'fontSize': '28px', 'marginBottom': '12px', 'display': 'block'}),
                html.H4(f"Unable to load data for {stock_symbol}",
                    style={
                        'color': COLORS['negative'],
                        'fontWeight': '600',
                        'marginBottom': '8px'
                    }),
                html.P(f"Please check the ticker symbol and try again.",
                    style={
                        'color': COLORS['text_secondary'],
                        'fontSize': '14px',
                        'margin': '0'
                    })
            ], style={'textAlign': 'center'})
        ], className="alert alert-danger", style={
            'borderRadius': '14px',
            'padding': '32px 24px',
            'border': 'none',
            'background': f'linear-gradient(135deg, {COLORS["negative_light"]} 0%, #fff5f5 100%)',
            'borderLeft': f'4px solid {COLORS["negative"]}'
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


        if icon_url:
            separator = '?' if '?' not in icon_url else '&'
            icon_url = f"{icon_url}{separator}apiKey={polygon_api_key}"
            logger.info(f"Final icon URL after replacement: {icon_url}")

        if logo_url:
            separator = '?' if '?' not in logo_url else '&'
            logo_url = f"{logo_url}{separator}apiKey={polygon_api_key}"
            logger.info(f"Final logo URL after replacement: {logo_url}")


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