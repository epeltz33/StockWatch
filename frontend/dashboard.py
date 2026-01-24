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

# Define color scheme (modern dark glassmorphism palette)
COLORS = {
    'primary': '#38bdf8',
    'primary_dark': '#0ea5e9',
    'primary_light': '#7dd3fc',
    'secondary': 'rgba(30, 41, 59, 0.8)',
    'text': '#f1f5f9',
    'text_secondary': '#cbd5e1',
    'text_muted': '#94a3b8',
    'positive': '#4ade80',
    'positive_light': 'rgba(34, 197, 94, 0.15)',
    'negative': '#f87171',
    'negative_light': 'rgba(248, 113, 113, 0.15)',
    'background': 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
    'background_solid': '#0f172a',
    'card': 'rgba(30, 41, 59, 0.8)',
    'card_solid': '#1e293b',
    'border': 'rgba(148, 163, 184, 0.2)',
    'border_hover': 'rgba(56, 189, 248, 0.4)',
    'accent': '#06b6d4'
}

# Define custom styles (modern dark glassmorphism design system)
CUSTOM_STYLES = {
    'card': {
        'borderRadius': '12px',
        'marginBottom': '20px',
        'boxShadow': '0 4px 30px rgba(0, 0, 0, 0.3)',
        'border': f'1px solid {COLORS["border"]}',
        'transition': 'all 0.3s ease',
        'overflow': 'hidden',
        'backgroundColor': COLORS['card'],
        'backdropFilter': 'blur(10px)',
        'WebkitBackdropFilter': 'blur(10px)'
    },
    'button': {
        'borderRadius': '8px',
        'fontWeight': '500',
        'transition': 'all 0.3s ease',
        'border': f'1px solid {COLORS["border"]}',
        'backgroundColor': 'rgba(56, 189, 248, 0.1)',
        'color': COLORS['primary']
    },
    'button_primary': {
        'borderRadius': '8px',
        'fontWeight': '500',
        'transition': 'all 0.3s ease',
        'border': f'1px solid rgba(56, 189, 248, 0.3)',
        'backgroundColor': 'rgba(56, 189, 248, 0.1)',
        'color': COLORS['primary'],
        'padding': '10px 20px'
    },
    'stock_logo': {
        'height': '56px',
        'width': '56px',
        'objectFit': 'contain',
        'marginRight': '16px',
        'borderRadius': '12px',
        'backgroundColor': 'rgba(30, 41, 59, 0.6)',
        'padding': '8px',
        'border': f'1px solid {COLORS["border"]}',
        'boxShadow': '0 4px 15px rgba(0, 0, 0, 0.2)'
    },
    'stock_header': {
        'display': 'flex',
        'alignItems': 'center',
        'marginBottom': '20px'
    },
    'card_title': {
        'fontSize': '0.85rem',
        'fontWeight': '600',
        'color': COLORS['text_muted'],
        'marginBottom': '8px',
        'textTransform': 'uppercase',
        'letterSpacing': '0.5px'
    },
    'card_value': {
        'fontSize': '1.8rem',
        'fontWeight': '700',
        'marginBottom': '6px',
        'letterSpacing': '-0.5px',
        'color': COLORS['text']
    },
    'card_change_positive': {
        'color': COLORS['positive'],
        'fontWeight': '600',
        'fontSize': '0.9rem',
        'display': 'inline-block'
    },
    'card_change_negative': {
        'color': COLORS['negative'],
        'fontWeight': '600',
        'fontSize': '0.9rem',
        'display': 'inline-block'
    },
    'metric_card': {
        'backgroundColor': COLORS['card'],
        'border': f'1px solid {COLORS["border"]}',
        'borderRadius': '12px',
        'padding': '20px',
        'backdropFilter': 'blur(10px)',
        'WebkitBackdropFilter': 'blur(10px)',
        'transition': 'all 0.3s ease'
    },
    'section_title': {
        'fontSize': '1.3rem',
        'fontWeight': '600',
        'color': COLORS['text'],
        'marginBottom': '20px'
    }
}

def create_stock_card(title, value, change=None):
    """Create a modern dark glassmorphism stock information card"""
    # Determine style based on change value
    change_style = {'color': COLORS['text_muted'], 'fontSize': '0.9rem'}
    change_value = 0
    if change and change.strip('%'):
        try:
            change_value = float(change.strip('%'))
            change_style = CUSTOM_STYLES['card_change_positive'] if change_value > 0 else CUSTOM_STYLES['card_change_negative']
        except ValueError:
            change_style = {'color': COLORS['text_muted'], 'fontSize': '0.9rem'}

    # Add arrow indicator based on change value
    change_indicator = "↑ " if change_value > 0 else "↓ " if change_value < 0 else ""
    change_display = f"{change_indicator}{change}" if change else ""

    return html.Div([
        html.Div(title, style=CUSTOM_STYLES['card_title']),
        html.Div(value, style=CUSTOM_STYLES['card_value']),
        html.Div(change_display, style=change_style) if change is not None else html.Div()
    ], style={
        'backgroundColor': COLORS['card'],
        'borderRadius': '12px',
        'padding': '20px',
        'boxShadow': '0 4px 30px rgba(0, 0, 0, 0.3)',
        'border': f'1px solid {COLORS["border"]}',
        'height': '100%',
        'minHeight': '120px',
        'transition': 'all 0.3s ease',
        'backdropFilter': 'blur(10px)',
        'WebkitBackdropFilter': 'blur(10px)'
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
        style_cell={
            'textAlign': 'left',
            'backgroundColor': 'transparent',
            'color': COLORS['text'],
            'border': 'none',
            'borderBottom': f'1px solid {COLORS["border"]}',
            'padding': '15px 20px',
            'fontFamily': "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            'fontSize': '0.95rem'
        },
        style_data_conditional=[
            {
                'if': {'column_id': 'change', 'filter_query': '{change} > 0'},
                'color': COLORS['positive']
            },
            {
                'if': {'column_id': 'change', 'filter_query': '{change} < 0'},
                'color': COLORS['negative']
            },
            {
                'if': {'state': 'hover'},
                'backgroundColor': 'rgba(56, 189, 248, 0.05)'
            }
        ],
        style_header={
            'backgroundColor': 'rgba(15, 23, 42, 0.5)',
            'fontWeight': '600',
            'color': COLORS['text_muted'],
            'textTransform': 'uppercase',
            'letterSpacing': '0.5px',
            'fontSize': '0.85rem',
            'border': 'none',
            'borderBottom': f'1px solid {COLORS["border"]}'
        },
        style_table={
            'overflowX': 'auto',
            'backgroundColor': 'transparent'
        }
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
        # Header Section
        html.Div([
            html.Div([
                html.H1("StockWatch", style={
                    'fontSize': '2.5rem',
                    'fontWeight': '700',
                    'background': 'linear-gradient(135deg, #38bdf8 0%, #0ea5e9 100%)',
                    'WebkitBackgroundClip': 'text',
                    'WebkitTextFillColor': 'transparent',
                    'backgroundClip': 'text',
                    'margin': '0'
                }),
            ]),
            html.Div([
                html.Span("Last Updated: ", style={'color': COLORS['text_muted']}),
                html.Span(id='last-update-time', style={'color': COLORS['text_secondary']})
            ], style={'fontSize': '0.9rem'})
        ], style={
            'display': 'flex',
            'justifyContent': 'space-between',
            'alignItems': 'center',
            'flexWrap': 'wrap',
            'gap': '20px',
            'marginBottom': '30px',
            'paddingBottom': '20px',
            'borderBottom': f'1px solid {COLORS["border"]}'
        }),

        # Main Content Section
        dbc.Row([
            # Left Sidebar
            dbc.Col([
                # Search Section
                html.Div([
                    html.H5("Search Stocks", style={
                        'fontSize': '1.2rem',
                        'fontWeight': '600',
                        'color': COLORS['text'],
                        'marginBottom': '16px'
                    }),
                    dbc.InputGroup([
                        dbc.Input(id='stock-input',
                                type='text',
                                placeholder='Enter ticker (e.g., AAPL)...',
                                style={
                                    'backgroundColor': 'rgba(15, 23, 42, 0.5)',
                                    'border': f'1px solid {COLORS["border"]}',
                                    'borderRadius': '8px 0 0 8px',
                                    'color': COLORS['text'],
                                    'padding': '12px 16px',
                                    'fontSize': '0.95rem'
                                }),
                        dbc.Button('Search',
                                id='search-button',
                                style={
                                    'backgroundColor': COLORS['primary'],
                                    'border': 'none',
                                    'borderRadius': '0 8px 8px 0',
                                    'color': '#0f172a',
                                    'fontWeight': '600',
                                    'padding': '12px 20px'
                                })
                    ], className='mb-4'),
                    html.Div(id='stock-data')
                ], style={
                    'backgroundColor': COLORS['card'],
                    'borderRadius': '12px',
                    'padding': '24px',
                    'border': f'1px solid {COLORS["border"]}',
                    'backdropFilter': 'blur(10px)',
                    'WebkitBackdropFilter': 'blur(10px)',
                    'marginBottom': '20px'
                }),

                # Watchlist Section
                html.Div([
                    html.H5("Watchlists", style={
                        'fontSize': '1.2rem',
                        'fontWeight': '600',
                        'color': COLORS['text'],
                        'marginBottom': '16px'
                    }),
                    dcc.Dropdown(id='watchlist-dropdown',
                            options=[],
                            placeholder='Select a watchlist',
                            className='mb-3 dark-dropdown',
                            style={'minHeight': '44px'}),
                    dbc.InputGroup([
                        dbc.Input(id='new-watchlist-input',
                                type='text',
                                placeholder='New watchlist name...',
                                style={
                                    'backgroundColor': 'rgba(15, 23, 42, 0.5)',
                                    'border': f'1px solid {COLORS["border"]}',
                                    'borderRadius': '8px 0 0 8px',
                                    'color': COLORS['text'],
                                    'padding': '12px 16px',
                                    'fontSize': '0.95rem'
                                }),
                        dbc.Button('Create',
                                id='create-watchlist-button',
                                style={
                                    'backgroundColor': 'rgba(56, 189, 248, 0.1)',
                                    'border': f'1px solid rgba(56, 189, 248, 0.3)',
                                    'borderRadius': '0 8px 8px 0',
                                    'color': COLORS['primary'],
                                    'fontWeight': '500',
                                    'padding': '12px 20px'
                                })
                    ], className='mb-4'),
                    html.Div(id='watchlist-section')
                ], style={
                    'backgroundColor': COLORS['card'],
                    'borderRadius': '12px',
                    'padding': '24px',
                    'border': f'1px solid {COLORS["border"]}',
                    'backdropFilter': 'blur(10px)',
                    'WebkitBackdropFilter': 'blur(10px)'
                })
            ], lg=4, md=12, className='mb-4'),

            dbc.Col([
                # Chart Section
                html.Div([
                    html.Div(id='stock-chart-container',
                        className='chart-container',
                        style={'minHeight': '480px'})
                ], style={
                    'backgroundColor': COLORS['card'],
                    'borderRadius': '12px',
                    'padding': '24px',
                    'border': f'1px solid {COLORS["border"]}',
                    'backdropFilter': 'blur(10px)',
                    'WebkitBackdropFilter': 'blur(10px)',
                    'marginBottom': '20px'
                }),

                # Company Info Section
                html.Div(id='company-info-container',
                    className='company-info-container')
            ], lg=8, md=12)
        ], className='g-4'),

        # Update Interval
        dcc.Interval(id='watchlist-interval', interval=30*1000, n_intervals=0)
    ], fluid=True, className='py-4 dark-theme-container', style={
        'maxWidth': '1600px',
        'minHeight': '100vh'
    })


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

        # Create chart container with dark glassmorphism styling
        chart_container = html.Div([
            html.Div(f"{clicked_stock} Stock Price", style={
                'fontSize': '1.3rem',
                'fontWeight': '600',
                'color': COLORS['text'],
                'marginBottom': '16px'
            }),
            dcc.Graph(
                id='stock-chart',
                figure=chart,
                style={'height': '440px', 'width': '100%'},
                config={
                    'displayModeBar': True,
                    'responsive': True,
                    'displaylogo': False,
                    'modeBarButtonsToRemove': ['lasso2d', 'select2d']
                }
            )
        ], style={
            'backgroundColor': 'transparent',
            'borderRadius': '12px'
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
            html.Span("📋", style={'fontSize': '32px', 'marginBottom': '12px', 'display': 'block'}),
            html.H4("Create your first watchlist", style={
                'fontWeight': '600',
                'color': COLORS['text'],
                'marginBottom': '8px',
                'fontSize': '1.1rem'
            }),
            html.P("Track your favorite stocks in one place.", style={
                'color': COLORS['text_muted'],
                'fontSize': '0.9rem',
                'marginBottom': '20px'
            })
        ], style={'textAlign': 'center'}),
        dbc.Input(id='new-watchlist-input', type='text',
                placeholder='Enter watchlist name...', className='mb-3',
                style={
                    'backgroundColor': 'rgba(15, 23, 42, 0.5)',
                    'border': f'1px solid {COLORS["border"]}',
                    'borderRadius': '8px',
                    'color': COLORS['text'],
                    'padding': '12px 16px'
                }),
        dbc.Button('Create Watchlist', id='create-watchlist-button',
                className='w-100', style={
                    'borderRadius': '8px',
                    'padding': '12px 20px',
                    'fontWeight': '500',
                    'backgroundColor': COLORS['primary'],
                    'border': 'none',
                    'color': '#0f172a'
                })
    ], style={
        'backgroundColor': 'rgba(30, 41, 59, 0.5)',
        'borderRadius': '12px',
        'padding': '24px 20px',
        'border': f'1px solid {COLORS["border"]}',
        'textAlign': 'center'
    })


def create_watchlist_content(watchlist):
    return html.Div([
        # Header
        html.Div([
            html.Div([
                html.Div(style={
                    'width': '3px',
                    'height': '18px',
                    'background': f'linear-gradient(180deg, {COLORS["primary"]} 0%, {COLORS["primary_dark"]} 100%)',
                    'borderRadius': '2px',
                    'marginRight': '10px'
                }),
                html.H5(watchlist.name, className="mb-0",
                    style={
                        'fontWeight': '600',
                        'color': COLORS['text'],
                        'fontSize': '1rem'
                    })
            ], style={'display': 'flex', 'alignItems': 'center'})
        ], style={
            'padding': '16px 20px',
            'background': 'rgba(15, 23, 42, 0.5)',
            'borderBottom': f'1px solid {COLORS["border"]}'
        }),

        # Content
        html.Div([
            html.Div([
                html.Div([
                    # Left side: Stock info
                    html.Div([
                        html.Span(stock.symbol,
                                style={
                                    'fontWeight': '700',
                                    'fontSize': '1rem',
                                    'color': COLORS['primary'],
                                    'marginRight': '10px',
                                    'cursor': 'pointer'
                                }),
                        html.Span(f"{stock.name}",
                                style={
                                    'fontSize': '0.85rem',
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
                            size='sm',
                            style={
                                'borderRadius': '6px',
                                'padding': '6px 12px',
                                'fontWeight': '500',
                                'fontSize': '0.8rem',
                                'backgroundColor': 'rgba(56, 189, 248, 0.1)',
                                'border': f'1px solid rgba(56, 189, 248, 0.3)',
                                'color': COLORS['primary']
                            }
                        ),
                        dbc.Button(
                            'Remove',
                            id={'type': 'remove-from-watchlist', 'index': stock.id},
                            size='sm',
                            style={
                                'borderRadius': '6px',
                                'padding': '6px 12px',
                                'fontWeight': '500',
                                'fontSize': '0.8rem',
                                'backgroundColor': 'rgba(248, 113, 113, 0.1)',
                                'border': f'1px solid rgba(248, 113, 113, 0.3)',
                                'color': COLORS['negative']
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
                    'padding': '12px 16px',
                    'borderBottom': f'1px solid {COLORS["border"]}',
                    'transition': 'background-color 0.2s ease'
                }) for stock in watchlist.stocks
            ]) if watchlist.stocks else
            html.Div([
                html.Div([
                    html.Span("📊", style={'fontSize': '28px', 'marginBottom': '10px', 'display': 'block'}),
                    html.P("No stocks added yet",
                        style={
                            'fontSize': '0.95rem',
                            'fontWeight': '500',
                            'color': COLORS['text'],
                            'marginBottom': '4px'
                        }),
                    html.P("Search for stocks and add them here.",
                        style={
                            'fontSize': '0.85rem',
                            'color': COLORS['text_muted'],
                            'margin': '0'
                        })
                ], style={'textAlign': 'center'})
            ], style={'padding': '30px 16px'})
        ])
    ], style={
        'border': f'1px solid {COLORS["border"]}',
        'borderRadius': '12px',
        'backgroundColor': 'rgba(30, 41, 59, 0.5)',
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
            
            # Add gradient area fill with cyan/sky blue color
            chart.add_trace(go.Scatter(
                x=df['date'],
                y=df['close'],
                mode='lines',
                line=dict(color='#38bdf8', width=2.5, shape='spline'),
                fill='tozeroy',
                fillcolor='rgba(56, 189, 248, 0.1)',
                name=f"{stock_symbol}",
                hovertemplate='<b>%{x}</b><br>$%{y:.2f}<extra></extra>'
            ))

            chart.update_layout(
                title=None,
                xaxis_title=None,
                yaxis_title=dict(text="Price ($)", font=dict(size=12, color=COLORS['text_muted'])),
                template="plotly_dark",
                margin=dict(l=60, r=30, t=40, b=50),
                hovermode="x unified",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color=COLORS['text'], family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"),
                height=440,
                autosize=True,
                showlegend=False,
                hoverlabel=dict(
                    bgcolor='rgba(30, 41, 59, 0.95)',
                    font_size=14,
                    font_family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
                    bordercolor='rgba(56, 189, 248, 0.3)',
                    font_color=COLORS['text']
                )
            )

            # Style axes for dark theme
            chart.update_xaxes(
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(148, 163, 184, 0.1)',
                showline=False,
                tickfont=dict(size=11, color=COLORS['text_muted']),
                rangeselector=dict(
                    buttons=list([
                        dict(count=1, label="1M", step="month", stepmode="backward"),
                        dict(count=3, label="3M", step="month", stepmode="backward"),
                        dict(count=6, label="6M", step="month", stepmode="backward"),
                        dict(count=1, label="YTD", step="year", stepmode="todate"),
                        dict(label="1Y", step="all")
                    ]),
                    bgcolor='rgba(30, 41, 59, 0.8)',
                    activecolor=COLORS['primary'],
                    bordercolor='rgba(148, 163, 184, 0.2)',
                    borderwidth=1,
                    font=dict(color=COLORS['text_secondary'], size=12),
                    x=0.02,
                    xanchor='left',
                    y=1.12
                ),
                rangeslider=dict(visible=False)
            )
            
            chart.update_yaxes(
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(148, 163, 184, 0.1)',
                showline=False,
                tickfont=dict(size=11, color=COLORS['text_muted']),
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

            # Determine price change styling for dark theme
            price_change_style = {
                'display': 'inline-flex',
                'alignItems': 'center',
                'gap': '3px',
                'padding': '4px 10px',
                'borderRadius': '6px',
                'fontWeight': '600',
                'fontSize': '0.9rem',
                'verticalAlign': 'middle'
            }
            if change_value > 0:
                price_change_style['backgroundColor'] = 'rgba(74, 222, 128, 0.15)'
                price_change_style['color'] = COLORS['positive']
                arrow = "↑"
            elif change_value < 0:
                price_change_style['backgroundColor'] = 'rgba(248, 113, 113, 0.15)'
                price_change_style['color'] = COLORS['negative']
                arrow = "↓"
            else:
                price_change_style['backgroundColor'] = 'rgba(148, 163, 184, 0.1)'
                price_change_style['color'] = COLORS['text_muted']
                arrow = ""

            # Create dark glassmorphism layout
            stock_info = html.Div([
                # Company Header Card with dark styling
                html.Div([
                    html.Div([
                        # Left side: Logo and Company Info
                        html.Div([
                            # Logo with dark theme styling
                            html.Img(
                                src=display_logo,
                                alt=stock_symbol,
                                style=CUSTOM_STYLES['stock_logo'],
                                className='company-logo'
                            ) if display_logo else html.Div(
                                html.Span(stock_symbol[0].upper(),
                                        style={
                                            'fontSize': '24px',
                                            'fontWeight': '700',
                                            'color': '#0f172a'
                                        }),
                                style={
                                    'background': f'linear-gradient(135deg, {COLORS["primary"]} 0%, {COLORS["primary_dark"]} 100%)',
                                    'borderRadius': '12px',
                                    'display': 'flex',
                                    'alignItems': 'center',
                                    'justifyContent': 'center',
                                    'width': '56px',
                                    'height': '56px',
                                    'marginRight': '16px',
                                    'boxShadow': '0 4px 15px rgba(56, 189, 248, 0.3)'
                                }
                            ),
                            # Company Info
                            html.Div([
                                html.H2(stock_symbol, style={
                                    'margin': '0 0 4px 0',
                                    'fontWeight': '700',
                                    'fontSize': '1.8rem',
                                    'letterSpacing': '-0.5px',
                                    'background': 'linear-gradient(135deg, #38bdf8 0%, #0ea5e9 100%)',
                                    'WebkitBackgroundClip': 'text',
                                    'WebkitTextFillColor': 'transparent',
                                    'backgroundClip': 'text'
                                }),
                                html.P(company_name, style={
                                    'margin': '0',
                                    'fontSize': '0.95rem',
                                    'color': COLORS['text_muted'],
                                    'fontWeight': '400'
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
                                style={
                                    'borderRadius': '8px',
                                    'padding': '10px 20px',
                                    'fontWeight': '500',
                                    'fontSize': '0.9rem',
                                    'backgroundColor': 'rgba(74, 222, 128, 0.1)',
                                    'border': '1px solid rgba(74, 222, 128, 0.3)',
                                    'color': COLORS['positive'],
                                    'whiteSpace': 'nowrap',
                                    'transition': 'all 0.3s ease'
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
                    'backgroundColor': COLORS['card'],
                    'borderRadius': '12px',
                    'padding': '20px',
                    'marginBottom': '16px',
                    'border': f'1px solid {COLORS["border"]}',
                    'backdropFilter': 'blur(10px)',
                    'WebkitBackdropFilter': 'blur(10px)'
                }),

                # Company Details Card with dark theme styling
                html.Div([
                    # Section title
                    html.Div("Stock Details", style={
                        'fontSize': '0.9rem',
                        'color': COLORS['primary'],
                        'textTransform': 'uppercase',
                        'letterSpacing': '1px',
                        'marginBottom': '16px',
                        'fontWeight': '600'
                    }),
                    
                    # Info grid
                    html.Div([
                        # Current Price
                        html.Div([
                            html.Div("Current Price", style={
                                'fontSize': '0.75rem',
                                'color': COLORS['text_muted'],
                                'textTransform': 'uppercase',
                                'letterSpacing': '0.5px',
                                'marginBottom': '6px'
                            }),
                            html.Div([
                                html.Span(f"${current_price:.2f}", style={
                                    'fontSize': '1.4rem',
                                    'fontWeight': '700',
                                    'color': COLORS['text'],
                                    'marginRight': '10px',
                                    'fontFamily': "'Monaco', 'Courier New', monospace"
                                }),
                                html.Span([
                                    html.Span(f"{arrow} ", style={'fontSize': '0.75rem'}),
                                    html.Span(f"{dollar_change:+.2f} ({change_str})")
                                ], style=price_change_style)
                            ])
                        ], style={
                            'backgroundColor': 'rgba(30, 41, 59, 0.5)',
                            'padding': '12px 16px',
                            'borderRadius': '8px',
                            'borderLeft': f'3px solid {COLORS["primary"]}'
                        }),
                        
                        # Previous Close
                        html.Div([
                            html.Div("Previous Close", style={
                                'fontSize': '0.75rem',
                                'color': COLORS['text_muted'],
                                'textTransform': 'uppercase',
                                'letterSpacing': '0.5px',
                                'marginBottom': '6px'
                            }),
                            html.Div(f"${previous_close:.2f}", style={
                                'fontSize': '1.1rem',
                                'fontWeight': '600',
                                'color': COLORS['text'],
                                'fontFamily': "'Monaco', 'Courier New', monospace"
                            })
                        ], style={
                            'backgroundColor': 'rgba(30, 41, 59, 0.5)',
                            'padding': '12px 16px',
                            'borderRadius': '8px',
                            'borderLeft': f'3px solid {COLORS["primary"]}'
                        }),
                        
                        # 52-Week Range
                        html.Div([
                            html.Div("52-Week Range", style={
                                'fontSize': '0.75rem',
                                'color': COLORS['text_muted'],
                                'textTransform': 'uppercase',
                                'letterSpacing': '0.5px',
                                'marginBottom': '6px'
                            }),
                            html.Div(fifty_two_week_range, style={
                                'fontSize': '1.1rem',
                                'fontWeight': '600',
                                'color': COLORS['text'],
                                'fontFamily': "'Monaco', 'Courier New', monospace"
                            })
                        ], style={
                            'backgroundColor': 'rgba(30, 41, 59, 0.5)',
                            'padding': '12px 16px',
                            'borderRadius': '8px',
                            'borderLeft': f'3px solid {COLORS["primary"]}'
                        }),
                        
                        # Market Cap
                        html.Div([
                            html.Div("Market Cap", style={
                                'fontSize': '0.75rem',
                                'color': COLORS['text_muted'],
                                'textTransform': 'uppercase',
                                'letterSpacing': '0.5px',
                                'marginBottom': '6px'
                            }),
                            html.Div(market_cap_str, style={
                                'fontSize': '1.1rem',
                                'fontWeight': '600',
                                'color': COLORS['text'],
                                'fontFamily': "'Monaco', 'Courier New', monospace"
                            })
                        ], style={
                            'backgroundColor': 'rgba(30, 41, 59, 0.5)',
                            'padding': '12px 16px',
                            'borderRadius': '8px',
                            'borderLeft': f'3px solid {COLORS["primary"]}'
                        }),
                        
                        # Exchange
                        html.Div([
                            html.Div("Exchange", style={
                                'fontSize': '0.75rem',
                                'color': COLORS['text_muted'],
                                'textTransform': 'uppercase',
                                'letterSpacing': '0.5px',
                                'marginBottom': '6px'
                            }),
                            html.Div(company_details.get('exchange', "N/A") if company_details else "N/A", style={
                                'fontSize': '1.1rem',
                                'fontWeight': '600',
                                'color': COLORS['text'],
                                'fontFamily': "'Monaco', 'Courier New', monospace"
                            })
                        ], style={
                            'backgroundColor': 'rgba(30, 41, 59, 0.5)',
                            'padding': '12px 16px',
                            'borderRadius': '8px',
                            'borderLeft': f'3px solid {COLORS["primary"]}'
                        }),
                        
                        # Website
                        html.Div([
                            html.Div("Website", style={
                                'fontSize': '0.75rem',
                                'color': COLORS['text_muted'],
                                'textTransform': 'uppercase',
                                'letterSpacing': '0.5px',
                                'marginBottom': '6px'
                            }),
                            html.A(website_display.replace('https://', '').replace('http://', ''),
                                href=website,
                                target="_blank",
                                style={
                                    'color': COLORS['primary'],
                                    'textDecoration': 'none',
                                    'fontSize': '1rem',
                                    'fontWeight': '500'
                                }) if website else html.Span("N/A", style={'color': COLORS['text_muted'], 'fontSize': '1rem'})
                        ], style={
                            'backgroundColor': 'rgba(30, 41, 59, 0.5)',
                            'padding': '12px 16px',
                            'borderRadius': '8px',
                            'borderLeft': f'3px solid {COLORS["primary"]}'
                        })
                    ], style={
                        'display': 'grid',
                        'gridTemplateColumns': 'repeat(auto-fit, minmax(150px, 1fr))',
                        'gap': '12px',
                        'marginBottom': '20px'
                    }),
                    
                    # Description section
                    html.Div([
                        html.Div("About", style={
                            'fontSize': '0.9rem',
                            'color': COLORS['primary'],
                            'textTransform': 'uppercase',
                            'letterSpacing': '1px',
                            'marginBottom': '12px',
                            'fontWeight': '600'
                        }),
                        html.P(company_details.get('description', "No description available.") if company_details else "No description available.", style={
                            'color': COLORS['text_secondary'],
                            'lineHeight': '1.6',
                            'fontSize': '0.9rem',
                            'margin': '0'
                        })
                    ]) if company_details and company_details.get('description') else html.Div()
                ], style={
                    'backgroundColor': COLORS['card'],
                    'borderRadius': '12px',
                    'padding': '24px',
                    'border': f'1px solid {COLORS["border"]}',
                    'backdropFilter': 'blur(10px)',
                    'WebkitBackdropFilter': 'blur(10px)'
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
                        'fontSize': '0.9rem',
                        'margin': '0'
                    })
            ], style={'textAlign': 'center'})
        ], style={
            'borderRadius': '12px',
            'padding': '30px 24px',
            'border': f'1px solid rgba(248, 113, 113, 0.3)',
            'backgroundColor': 'rgba(248, 113, 113, 0.1)',
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