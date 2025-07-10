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
    """Create a simple, clean stock information card"""
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

    return html.Div([
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
            'color': COLORS['text']
        }),
        html.Div(change_display, style=change_style) if change is not None else html.Div()
    ], style={
        'backgroundColor': 'white',
        'borderRadius': '8px',
        'padding': '15px',
        'textAlign': 'center',
        'boxShadow': '0 2px 4px rgba(0,0,0,0.05)',
        'height': '100%',
        'minHeight': '120px'
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
        # Welcome Section with enhanced spacing
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.H2(id='welcome-message',
                            className='text-center mb-0'),
                ], className='stock-dashboard')
            ], width=12)
        ], className='mb-5'),

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
                ], className='mb-4'),

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
                ])
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

        # Get the number of 'add-to-watchlist' buttons dynamically based on the State
        # This is important because the number of these buttons can change.
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

        # Case 3: Remove Stock Button Clicked
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
        stock_info, chart = fetch_and_display_stock_data(clicked_stock

        # Create chart container
        chart_container = html.Div([
            dcc.Graph(
                id='stock-chart',
                figure=chart,
                style={'height': '500px', 'width': '100%'},
                config={'displayModeBar': True, 'responsive': True}
            )
        ], style={
            'backgroundColor': 'white',
            'borderRadius': '10px',
            'padding': '10px',
            'boxShadow': '0 2px 4px rgba(0,0,0,0.05)',
            'marginBottom': '20px'
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
        html.H4("You don't have any watchlists yet."),
        dbc.Input(id='new-watchlist-input', type='text',
                placeholder='Enter a new watchlist name...', className='mb-2'),
        dbc.Button('Create Watchlist', id='create-watchlist-button',
                color='primary', className='mb-4')
    ])


def create_watchlist_content(watchlist):
    return dbc.Card([
        dbc.CardHeader([
            html.H5(watchlist.name, className="mb-0",
                style={'fontWeight': '600', 'letterSpacing': '-0.3px'})
        ], style={'padding': '20px 24px', 'backgroundColor': '#f8f9fa'}),

        dbc.CardBody([
            dbc.ListGroup([
                dbc.ListGroupItem(
                    html.Div([
                        # Left side: Stock info
                        html.Div([
                            html.Span(stock.symbol,
                                    style={
                                        'fontWeight': '700',
                                        'fontSize': '18px',
                                        'display': 'inline-block',
                                        'marginRight': '12px',
                                        'letterSpacing': '-0.3px'
                                    }),
                            html.Span(f"{stock.name}",
                                    className='text-muted',
                                    style={
                                        'fontSize': '14px',
                                        'fontWeight': '400'
                                    })
                        ], style={
                            'flex': '1',
                            'minWidth': '0',  # Allows text truncation
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
                                className='me-2',
                                style={
                                    'borderRadius': '6px',
                                    'padding': '6px 16px',
                                    'fontWeight': '500'
                                }
                            ),
                            dbc.Button(
                                'Remove',
                                id={'type': 'remove-from-watchlist', 'index': stock.id},
                                color='danger',
                                size='sm',
                                style={
                                    'borderRadius': '6px',
                                    'padding': '6px 16px',
                                    'fontWeight': '500'
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
                        'gap': '20px'
                    }),
                    className='border-0 border-bottom',
                    style={'padding': '16px 20px'}
                ) for stock in watchlist.stocks
            ], flush=True, className='border-0') if watchlist.stocks else
            html.Div([
                html.P("No stocks added yet.",
                    className="text-center text-muted mb-2",
                    style={'fontSize': '16px'}),
                html.P("Search for stocks above and add them to your watchlist.",
                    className="text-center text-muted mb-0",
                    style={'fontSize': '14px'})
            ], style={'padding': '40px 20px'})
        ], className='p-0')
    ], className='shadow-sm')

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

            # Add selector buttons
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

            # Create clean, professional layout matching the screenshot
            stock_info = html.Div([
                # Company Header Section
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            # Logo
                            html.Img(
                                src=display_logo,
                                alt=stock_symbol,
                                style={
                                    'height': '60px',
                                    'width': '60px',
                                    'objectFit': 'contain',
                                    'marginRight': '20px'
                                },
                                className='company-logo'
                            ) if display_logo else html.Div(
                                html.Span(stock_symbol[0].upper(),
                                        style={
                                            'fontSize': '28px',
                                            'fontWeight': 'bold',
                                            'color': 'white',
                                            'backgroundColor': COLORS['primary'],
                                            'borderRadius': '8px',
                                            'display': 'flex',
                                            'alignItems': 'center',
                                            'justifyContent': 'center',
                                            'width': '60px',
                                            'height': '60px',
                                            'marginRight': '20px'
                                        })
                            ),

                            # Company Info
                            html.Div([
                                html.H2(stock_symbol, style={
                                    'margin': '0',
                                    'fontWeight': '700',
                                    'fontSize': '28px',
                                    'letterSpacing': '-0.5px'
                                }),
                                html.P(company_name, style={
                                    'margin': '0',
                                    'fontSize': '18px',
                                    'color': '#6c757d'
                                })
                            ])
                        ], style={
                            'display': 'flex',
                            'alignItems': 'center'
                        })
                    ])
                ], style={
                    'border': 'none',
                    'boxShadow': '0 1px 3px rgba(0,0,0,0.12)',
                    'marginBottom': '20px'
                }),

                # Add to Watchlist Button
                html.Div([
                    dbc.Button(
                        "Add to Watchlist",
                        id={'type': 'add-to-watchlist', 'index': stock_symbol},
                        color='success',
                        size='lg',
                        style={'width': '100%'}
                    )
                ], style={'marginBottom': '20px'}),

                # All Company Information in Clean Table Format
                dbc.Card([
                    dbc.CardBody([
                        html.Table([
                            html.Tbody([
                                # Current Price Row
                                html.Tr([
                                    html.Td("Current Price", style={
                                        'fontWeight': '500',
                                        'color': '#6c757d',
                                        'width': '40%',
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6',
                                        'backgroundColor': '#f8f9fa'
                                    }),
                                    html.Td([
                                        html.Span(f"${current_price:.2f}", style={
                                            'fontSize': '20px',
                                            'fontWeight': '600',
                                            'marginRight': '15px'
                                        }),
                                        html.Span(f"{dollar_change:+.2f} ({change_str})", style={
                                            'color': COLORS['positive'] if change_value > 0 else COLORS['negative'] if change_value < 0 else '#6c757d',
                                            'fontWeight': '500'
                                        })
                                    ], style={
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6'
                                    })
                                ]),

                                # Previous Close Row
                                html.Tr([
                                    html.Td("Previous Close", style={
                                        'fontWeight': '500',
                                        'color': '#6c757d',
                                        'width': '40%',
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6',
                                        'backgroundColor': '#f8f9fa'
                                    }),
                                    html.Td(f"${previous_close:.2f}", style={
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6',
                                        'fontSize': '16px'
                                    })
                                ]),

                                # 52-Week Range Row
                                html.Tr([
                                    html.Td("52-Week Range", style={
                                        'fontWeight': '500',
                                        'color': '#6c757d',
                                        'width': '40%',
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6',
                                        'backgroundColor': '#f8f9fa'
                                    }),
                                    html.Td(fifty_two_week_range, style={
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6',
                                        'fontSize': '16px'
                                    })
                                ]),

                                # Description Row
                                html.Tr([
                                    html.Td("Description", style={
                                        'fontWeight': '500',
                                        'color': '#6c757d',
                                        'width': '40%',
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6',
                                        'backgroundColor': '#f8f9fa',
                                        'verticalAlign': 'top'
                                    }),
                                    html.Td(company_details.get('description', "N/A") if company_details else "N/A", style={
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6',
                                        'fontSize': '16px',
                                        'lineHeight': '1.6'
                                    })
                                ]),

                                # Market Capitalization Row
                                html.Tr([
                                    html.Td("Market Capitalization", style={
                                        'fontWeight': '500',
                                        'color': '#6c757d',
                                        'width': '40%',
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6',
                                        'backgroundColor': '#f8f9fa'
                                    }),
                                    html.Td(market_cap_str, style={
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6',
                                        'fontSize': '16px'
                                    })
                                ]),

                                # Website Row
                                html.Tr([
                                    html.Td("Website", style={
                                        'fontWeight': '500',
                                        'color': '#6c757d',
                                        'width': '40%',
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6',
                                        'backgroundColor': '#f8f9fa'
                                    }),
                                    html.Td([
                                        html.A(website_display.replace('https://', '').replace('http://', ''),
                                            href=website,
                                            target="_blank",
                                            style={
                                                'color': COLORS['primary'],
                                                'textDecoration': 'none',
                                                'fontSize': '16px'
                                            }) if website else website_display
                                    ], style={
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6'
                                    })
                                ]),

                                # List Date Row
                                html.Tr([
                                    html.Td("List Date", style={
                                        'fontWeight': '500',
                                        'color': '#6c757d',
                                        'width': '40%',
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6',
                                        'backgroundColor': '#f8f9fa'
                                    }),
                                    html.Td(list_date_display, style={
                                        'padding': '16px',
                                        'borderBottom': '1px solid #dee2e6',
                                        'fontSize': '16px'
                                    })
                                ]),

                                # Listing Exchange Row
                                html.Tr([
                                    html.Td("Listing Exchange", style={
                                        'fontWeight': '500',
                                        'color': '#6c757d',
                                        'width': '40%',
                                        'padding': '16px',
                                        'backgroundColor': '#f8f9fa'
                                    }),
                                    html.Td(company_details.get('exchange', "N/A") if company_details else "N/A", style={
                                        'padding': '16px',
                                        'fontSize': '16px'
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
                    'border': 'none',
                    'boxShadow': '0 1px 3px rgba(0,0,0,0.12)',
                    'borderRadius': '8px',
                    'overflow': 'hidden'
                })
            ])

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