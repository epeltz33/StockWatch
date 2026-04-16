import dash
from dash import html, dcc, Input, Output, State, callback_context, no_update, ALL
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from plotly.subplots import make_subplots
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

PERIODS = ['1D', '5D', '1M', '6M', 'YTD', '1Y', '5Y', '10Y', 'MAX']


def filter_data_for_period(df, period):
    """Filter OHLCV dataframe to the selected time period.

    Period definitions (calendar-day based, using daily bars):
    - 1D: last 1 calendar day (may show 1-2 bars depending on weekends)
    - 5D: last 7 calendar days (~5 trading days)
    - 1M: last 30 calendar days
    - 6M: last 182 calendar days
    - YTD: from January 1 of the current year
    - 1Y: last 365 calendar days
    - 5Y: last 1,825 calendar days
    - 10Y: last 3,650 calendar days
    - MAX: all available data

    Percent change formula used downstream:
        (last_close - first_close_in_range) / first_close_in_range * 100
    """
    if df.empty:
        return df

    now = datetime.now()

    period_days = {
        '1D': 1,
        '5D': 7,
        '1M': 30,
        '6M': 182,
        '1Y': 365,
        '5Y': 365 * 5,
        '10Y': 365 * 10,
    }

    if period == 'MAX':
        return df
    elif period == 'YTD':
        cutoff = datetime(now.year, 1, 1).strftime('%Y-%m-%d')
    elif period in period_days:
        cutoff = (now - timedelta(days=period_days[period])).strftime('%Y-%m-%d')
    else:
        return df

    filtered = df[df['date'] >= cutoff]
    # Degrade gracefully: if filtering yields fewer than 2 bars, show the last 2
    if len(filtered) < 2:
        return df.tail(2)
    return filtered


def calculate_period_change(df):
    """(last_close - first_close) / first_close * 100 over the filtered range."""
    if df.empty or len(df) < 1:
        return 0.0
    first_close = df['close'].iloc[0]
    last_close = df['close'].iloc[-1]
    if first_close == 0:
        return 0.0
    return ((last_close - first_close) / first_close) * 100


def create_stock_chart_figure(df, symbol):
    """Price line + area (top) and volume bars (bottom) with shared x-axis.

    Y-axes are placed on the right. Plotly's built-in rangeselector is omitted
    so that the custom Dash period buttons are the sole period control.
    """
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.85, 0.15],
    )

    # --- price line with area fill ---
    fig.add_trace(go.Scatter(
        x=df['date'],
        y=df['close'],
        mode='lines',
        line=dict(color='#38bdf8', width=2, shape='spline'),
        fill='tozeroy',
        fillcolor='rgba(56, 189, 248, 0.08)',
        name='Price',
        hovertemplate='<b>%{x}</b><br>$%{y:.2f}<extra></extra>',
    ), row=1, col=1)

    # --- volume bars (subtle, no axis labels) ---
    if 'volume' in df.columns and df['volume'].notna().any():
        colors = ['rgba(148, 163, 184, 0.20)' if i == 0
                  else 'rgba(74, 222, 128, 0.20)' if df['close'].iloc[i] >= df['close'].iloc[i - 1]
                  else 'rgba(248, 113, 113, 0.20)'
                  for i in range(len(df))]

        fig.add_trace(go.Bar(
            x=df['date'],
            y=df['volume'],
            marker_color=colors,
            name='Volume',
            hovertemplate='Vol: %{y:,.0f}<extra></extra>',
        ), row=2, col=1)

    fig.update_layout(
        title=None,
        template='plotly_dark',
        margin=dict(l=10, r=55, t=10, b=25),
        hovermode='x unified',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(
            color=COLORS['text'],
            family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        ),
        height=440,
        autosize=True,
        showlegend=False,
        hoverlabel=dict(
            bgcolor='rgba(30, 41, 59, 0.95)',
            font_size=13,
            font_family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            bordercolor='rgba(56, 189, 248, 0.3)',
            font_color=COLORS['text'],
        ),
        bargap=0.3,
    )

    # price y-axis (right)
    fig.update_yaxes(
        showgrid=True, gridwidth=1, gridcolor='rgba(148, 163, 184, 0.08)',
        showline=False, tickfont=dict(size=11, color=COLORS['text_muted']),
        tickprefix='$', tickformat=',.0f', side='right',
        row=1, col=1,
    )
    # volume y-axis — hidden tick labels, just the bars for visual context
    fig.update_yaxes(
        showgrid=False, showline=False, showticklabels=False,
        row=2, col=1,
    )
    # price x-axis — hide ticks (shared with volume below)
    fig.update_xaxes(
        showgrid=True, gridwidth=1, gridcolor='rgba(148, 163, 184, 0.08)',
        showline=False, showticklabels=False,
        row=1, col=1,
    )
    # volume x-axis — show date ticks here only
    fig.update_xaxes(
        showgrid=False, showline=False,
        tickfont=dict(size=10, color=COLORS['text_muted']),
        row=2, col=1,
    )

    return fig


def _period_btn_style(is_active):
    """Return inline style dict for a period pill button."""
    return {
        'borderRadius': '20px',
        'padding': '5px 12px',
        'fontSize': '0.78rem',
        'fontWeight': '600' if is_active else '500',
        'backgroundColor': 'rgba(56, 189, 248, 0.15)' if is_active else 'transparent',
        'border': f'1px solid {COLORS["primary"]}' if is_active else f'1px solid {COLORS["border"]}',
        'color': COLORS['primary'] if is_active else COLORS['text_muted'],
        'cursor': 'pointer',
        'lineHeight': '1.4',
        'outline': 'none',
    }


def _period_badge(pct_change):
    """Return (children_list, style_dict) for the active period badge."""
    if pct_change > 0:
        bg = COLORS['positive_light']
        color = COLORS['positive']
        text = f"+{pct_change:,.2f}%"
    elif pct_change < 0:
        bg = COLORS['negative_light']
        color = COLORS['negative']
        text = f"{pct_change:,.2f}%"
    else:
        bg = 'rgba(148, 163, 184, 0.1)'
        color = COLORS['text_muted']
        text = "0.00%"

    children = [
        # small caret pointing up toward the button
        html.Div(style={
            'width': '0', 'height': '0',
            'borderLeft': '5px solid transparent',
            'borderRight': '5px solid transparent',
            'borderBottom': f'5px solid {bg}',
            'margin': '3px auto 0 auto',
        }),
        html.Div(text, style={
            'backgroundColor': bg,
            'color': color,
            'borderRadius': '10px',
            'padding': '1px 8px',
            'fontSize': '0.7rem',
            'fontWeight': '600',
            'whiteSpace': 'nowrap',
        }),
    ]
    style = {'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'}
    return children, style


def build_period_toolbar(active_period, pct_change):
    """Build the period-selector toolbar (buttons row + badge under active)."""
    cols = []
    for period in PERIODS:
        is_active = period == active_period

        badge_children, badge_style = (
            _period_badge(pct_change) if is_active else ([], {'display': 'none'})
        )

        cols.append(html.Div([
            html.Button(
                period,
                id={'type': 'period-btn', 'index': period},
                n_clicks=0,
                style=_period_btn_style(is_active),
            ),
            html.Div(
                badge_children,
                id={'type': 'period-badge', 'index': period},
                style=badge_style,
            ),
        ], style={
            'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center',
        }))

    return html.Div(cols, style={
        'display': 'flex',
        'gap': '4px',
        'justifyContent': 'flex-end',
        'flexWrap': 'wrap',
        'alignItems': 'flex-start',
    })


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
                            dbc.themes.BOOTSTRAP,
                            'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap',
                            '/assets/custom.css'],
                        assets_folder='assets',
                        suppress_callback_exceptions=True)

    dash_app.layout = create_layout()

    register_callbacks(dash_app)

    return dash_app


def empty_state(icon, message, sub=None):
    """Muted placeholder shown before a container has been populated by a callback."""
    children = [
        html.Div(icon, style={
            'fontSize': '2.2rem', 'marginBottom': '12px', 'opacity': '0.6',
        }),
        html.Div(message, style={
            'fontSize': '0.95rem', 'fontWeight': '500', 'color': COLORS['text_secondary'],
        }),
    ]
    if sub:
        children.append(html.Div(sub, style={
            'fontSize': '0.85rem', 'color': COLORS['text_muted'], 'marginTop': '6px',
        }))
    return html.Div(children, style={
        'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center',
        'justifyContent': 'center', 'textAlign': 'center',
        'padding': '40px 20px', 'minHeight': '160px',
    })


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
                    dcc.Loading(
                        id='loading-stock-data',
                        type='circle',
                        color=COLORS['primary'],
                        children=html.Div(id='stock-data'),
                    ),
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
                    dcc.Loading(
                        id='loading-watchlist',
                        type='circle',
                        color=COLORS['primary'],
                        children=html.Div(
                            id='watchlist-section',
                            children=empty_state(
                                '\u2605',
                                'No watchlist selected',
                                'Create one above or pick an existing watchlist.',
                            ),
                        ),
                    ),
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
                    dcc.Loading(
                        id='loading-chart',
                        type='circle',
                        color=COLORS['primary'],
                        children=html.Div(
                            id='stock-chart-container',
                            className='chart-container',
                            style={'minHeight': '480px'},
                            children=empty_state(
                                '\U0001F4C8',
                                'Search a ticker to begin',
                                'Try AAPL, MSFT, or SNDK — press Enter to search.',
                            ),
                        ),
                    ),
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
                dcc.Loading(
                    id='loading-company-info',
                    type='circle',
                    color=COLORS['primary'],
                    children=html.Div(
                        id='company-info-container',
                        className='company-info-container',
                    ),
                ),
            ], lg=8, md=12)
        ], className='g-4'),

        # Data stores for chart period selection
        dcc.Store(id='stock-ohlcv-store', data=None),
        dcc.Store(id='stock-symbol-store', data=None),

        # Toast feedback infrastructure
        dcc.Store(id='toast-trigger', data=None),
        html.Div(id='toast-container', style={
            'position': 'fixed',
            'top': '20px',
            'right': '20px',
            'zIndex': 1050,
            'pointerEvents': 'none',
        }),

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
        Output({'type': 'add-to-watchlist', 'index': ALL}, 'children'),
        Output('toast-trigger', 'data')],
        [Input('create-watchlist-button', 'n_clicks'),
        Input({'type': 'add-to-watchlist', 'index': ALL}, 'n_clicks'),
        Input({'type': 'remove-from-watchlist', 'index': ALL}, 'n_clicks'),
        Input({'type': 'delete-watchlist', 'index': ALL}, 'n_clicks'),
        Input('watchlist-dropdown', 'value')],
        [State('new-watchlist-input', 'value'),
        State({'type': 'add-to-watchlist', 'index': ALL}, 'id')]
    )
    def update_watchlist(create_clicks, add_clicks, remove_clicks, delete_clicks, selected_watchlist_id, new_watchlist_name, add_ids):
        ctx = callback_context
        triggered_id = ctx.triggered_id

        num_add_buttons = len(add_ids) if add_ids else 0
        no_update_list = [no_update] * num_add_buttons

        def toast(message, kind='info'):
            # nonce forces `toast-trigger` to register a change even if the
            # message text repeats between events.
            return {'message': message, 'type': kind, 'n': (ctx.triggered[0].get('value') if ctx.triggered else 0)}

        # If nothing triggered (initial load), do nothing
        if not triggered_id:
            return no_update, no_update, no_update_list, no_update

        # Determine the type of trigger (string or dict for pattern-matching)
        trigger_type = None
        if isinstance(triggered_id, dict) and 'type' in triggered_id:
            trigger_type = triggered_id.get('type')
        elif isinstance(triggered_id, str):
            trigger_type = triggered_id # e.g., 'create-watchlist-button', 'watchlist-dropdown'

        # --- Handle specific triggers ---

        # Case 1: Create Watchlist Button Clicked
        if trigger_type == 'create-watchlist-button':
            if not new_watchlist_name or not new_watchlist_name.strip():
                return no_update, no_update, no_update_list, toast('Watchlist name cannot be empty.', 'danger')
            try:
                name = new_watchlist_name.strip()
                watchlist = Watchlist(name=name, user_id=current_user.id)
                db.session.add(watchlist)
                db.session.commit()
                logger.info(f"Created watchlist '{name}' with id {watchlist.id}")
                return (update_watchlist_section(watchlist.id), watchlist.id,
                        no_update_list, toast(f'Created watchlist "{name}".', 'success'))
            except SQLAlchemyError as e:
                db.session.rollback()
                logger.error(f"Error creating watchlist: {str(e)}")
                return no_update, no_update, no_update_list, toast('Could not create watchlist.', 'danger')

        # Case 2: Add Stock Button Clicked
        elif trigger_type == 'add-to-watchlist':
            stock_symbol = triggered_id['index']

            button_index = next((i for i, btn_id in enumerate(add_ids)
                            if btn_id['index'] == stock_symbol), None)

            if button_index is None or not add_clicks or button_index >= len(add_clicks) or not add_clicks[button_index]:
                logger.info(f"Add to watchlist ignored for {stock_symbol} - no valid click detected")
                return no_update, no_update, no_update_list, no_update

            if not selected_watchlist_id:
                logger.warning(f"Attempted to add {stock_symbol} but no watchlist selected.")
                return no_update, no_update, no_update_list, toast('Select a watchlist first.', 'danger')

            logger.info(f"Adding stock {stock_symbol} to watchlist {selected_watchlist_id}")
            try:
                watchlist = Watchlist.query.get(selected_watchlist_id)
                if not watchlist:
                    return no_update, no_update, no_update_list, toast('Watchlist not found.', 'danger')

                existing_stock = Stock.query.filter_by(symbol=stock_symbol).first()
                if existing_stock and existing_stock in watchlist.stocks:
                    return (no_update, no_update, no_update_list,
                            toast(f'{stock_symbol} is already in "{watchlist.name}".', 'info'))

                stock = existing_stock or create_new_stock(stock_symbol)
                if not stock:
                    return no_update, no_update, no_update_list, toast(f'Could not add {stock_symbol}.', 'danger')

                watchlist.stocks.append(stock)
                db.session.commit()
                logger.info(f"Successfully added {stock_symbol} to watchlist {selected_watchlist_id}")

                # Reset every "Add" button text to its default — the watchlist
                # list is fully re-rendered below, and this keeps the search-
                # results "Add" button honest on repeat adds.
                reset_texts = ['Add'] * num_add_buttons
                return (update_watchlist_section(selected_watchlist_id), selected_watchlist_id,
                        reset_texts, toast(f'Added {stock_symbol} to "{watchlist.name}".', 'success'))

            except Exception as e:
                db.session.rollback()
                logger.error(f"Error adding stock {stock_symbol} to watchlist {selected_watchlist_id}: {str(e)}")
                return no_update, no_update, no_update_list, toast(f'Could not add {stock_symbol}.', 'danger')

        elif trigger_type == 'remove-from-watchlist':
            stock_id = triggered_id['index']
            if not selected_watchlist_id:
                return no_update, no_update, no_update_list, no_update

            logger.info(f"Removing stock id {stock_id} from watchlist {selected_watchlist_id}")
            try:
                stock = Stock.query.get(stock_id)
                watchlist = Watchlist.query.get(selected_watchlist_id)
                if watchlist and stock and stock in watchlist.stocks:
                    watchlist.stocks.remove(stock)
                    db.session.commit()
                    logger.info(f"Removed stock id {stock_id} from watchlist {selected_watchlist_id}")
                    return (update_watchlist_section(selected_watchlist_id), selected_watchlist_id,
                            no_update_list, toast(f'Removed {stock.symbol} from "{watchlist.name}".', 'success'))
                return (update_watchlist_section(selected_watchlist_id), selected_watchlist_id,
                        no_update_list, no_update)
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error removing stock id {stock_id}: {str(e)}")
                return no_update, no_update, no_update_list, toast('Could not remove stock.', 'danger')

        elif trigger_type == 'delete-watchlist':
            watchlist_id = triggered_id['index']
            logger.info(f"Deleting watchlist {watchlist_id}")
            try:
                watchlist = Watchlist.query.get(watchlist_id)
                if watchlist and watchlist.user_id == current_user.id:
                    name = watchlist.name
                    db.session.delete(watchlist)
                    db.session.commit()
                    return (update_watchlist_section(None), None,
                            no_update_list, toast(f'Deleted watchlist "{name}".', 'success'))
                return (update_watchlist_section(None), None,
                        no_update_list, toast('Watchlist not found.', 'danger'))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error deleting watchlist {watchlist_id}: {str(e)}")
                return no_update, no_update, no_update_list, toast('Could not delete watchlist.', 'danger')

        elif trigger_type == 'watchlist-dropdown':
            logger.info(f"Watchlist dropdown changed to: {selected_watchlist_id}")
            return (update_watchlist_section(selected_watchlist_id), selected_watchlist_id,
                    no_update_list, no_update)

        logger.debug(f"update_watchlist: No specific action taken for trigger {triggered_id}")
        return no_update, no_update, no_update_list, no_update

    # --- Toast renderer ---
    @dash_app.callback(
        Output('toast-container', 'children'),
        Input('toast-trigger', 'data'),
        prevent_initial_call=True,
    )
    def render_toast(payload):
        if not payload or not payload.get('message'):
            return no_update
        kind = payload.get('type', 'info')
        icon_map = {'success': 'success', 'danger': 'danger', 'info': 'primary', 'warning': 'warning'}
        header_map = {'success': 'Success', 'danger': 'Error', 'info': 'Notice', 'warning': 'Warning'}
        return dbc.Toast(
            payload['message'],
            id={'type': 'toast-instance', 'index': payload.get('n', 0)},
            header=header_map.get(kind, 'Notice'),
            icon=icon_map.get(kind, 'primary'),
            is_open=True,
            dismissable=True,
            duration=3500,
            style={'pointerEvents': 'auto'},
        )

    @dash_app.callback(
        [Output('stock-data', 'children'),
        Output('stock-chart-container', 'children'),
        Output('stock-input', 'value'),
        Output('stock-ohlcv-store', 'data'),
        Output('stock-symbol-store', 'data')],
        [Input({'type': 'load-watchlist-stock', 'index': ALL}, 'n_clicks'),
        Input('search-button', 'n_clicks'),
        Input('stock-input', 'n_submit')],
        [State({'type': 'load-watchlist-stock', 'index': ALL}, 'id'),
        State('stock-input', 'value')]
    )
    def update_stock_data(watchlist_clicks, search_clicks, search_submit, watchlist_stock_ids, search_input):
        ctx = callback_context
        trigger_source = None # To track 'watchlist' or 'search'
        clicked_stock = None

        # Check if the callback was triggered by anything
        if not ctx.triggered or not ctx.triggered[0]:
            return no_update, no_update, no_update, no_update, no_update

        # Get the specific property and value that triggered the callback
        triggered_prop = ctx.triggered[0]['prop_id']
        triggered_value = ctx.triggered[0]['value']

        # --- Check for valid click triggers ---

        # Scenario 1: A watchlist stock span was clicked
        if triggered_prop.endswith('.n_clicks') and '"type":"load-watchlist-stock"' in triggered_prop:
            if triggered_value is not None and triggered_value > 0:
                json_part = triggered_prop.split('.')[0]
                try:
                    clicked_stock_info = json.loads(json_part)
                    clicked_stock = clicked_stock_info.get('index')
                    trigger_source = 'watchlist'
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse watchlist trigger prop_id: {triggered_prop}")
                    return no_update, no_update, no_update, no_update, no_update

        elif triggered_prop in ('search-button.n_clicks', 'stock-input.n_submit'):
            if triggered_value is not None and triggered_value > 0:
                if search_input:
                    clicked_stock = search_input.strip().upper()
                    trigger_source = 'search'
                    logger.info(f"Search triggered ({triggered_prop}) for: {clicked_stock}")

        # --- Process if a valid click was identified ---

        if not clicked_stock or not trigger_source:
            return no_update, no_update, no_update, no_update, no_update

        stock_info, df = fetch_and_display_stock_data(clicked_stock)

        if df.empty:
            chart_container = html.Div(
                f"No chart data available for {clicked_stock}",
                style={'color': COLORS['text_muted'], 'padding': '40px', 'textAlign': 'center'},
            )
            stock_input_update = clicked_stock if trigger_source == 'search' else no_update
            return stock_info, chart_container, stock_input_update, no_update, no_update

        # Default period is 1Y; build initial chart and toolbar
        default_period = '1Y'
        filtered_df = filter_data_for_period(df, default_period)
        pct_change = calculate_period_change(filtered_df)
        chart_fig = create_stock_chart_figure(filtered_df, clicked_stock)
        toolbar = build_period_toolbar(default_period, pct_change)

        chart_container = html.Div([
            # Top row: title (left) + period buttons (right)
            html.Div([
                html.Div(f"{clicked_stock} Stock Price", style={
                    'fontSize': '1.3rem',
                    'fontWeight': '600',
                    'color': COLORS['text'],
                }),
                toolbar,
            ], style={
                'display': 'flex',
                'justifyContent': 'space-between',
                'alignItems': 'flex-start',
                'flexWrap': 'wrap',
                'gap': '10px',
                'marginBottom': '8px',
            }),
            dcc.Graph(
                id='stock-chart',
                figure=chart_fig,
                style={'height': '440px', 'width': '100%'},
                config={
                    'displayModeBar': 'hover',
                    'responsive': True,
                    'displaylogo': False,
                    'modeBarButtonsToRemove': [
                        'lasso2d', 'select2d', 'autoScale2d', 'toggleSpikelines',
                        'hoverClosestCartesian', 'hoverCompareCartesian',
                    ],
                },
            ),
        ], style={'backgroundColor': 'transparent', 'borderRadius': '12px'})

        stock_input_update = clicked_stock if trigger_source == 'search' else no_update
        return stock_info, chart_container, stock_input_update, df.to_dict('records'), clicked_stock

    # --- Period-button callback: filter data and update chart + badge ---
    @dash_app.callback(
        [Output('stock-chart', 'figure'),
         Output({'type': 'period-btn', 'index': ALL}, 'style'),
         Output({'type': 'period-badge', 'index': ALL}, 'children'),
         Output({'type': 'period-badge', 'index': ALL}, 'style')],
        Input({'type': 'period-btn', 'index': ALL}, 'n_clicks'),
        [State('stock-ohlcv-store', 'data'),
         State('stock-symbol-store', 'data'),
         State({'type': 'period-btn', 'index': ALL}, 'id')],
        prevent_initial_call=True,
    )
    def update_chart_period(n_clicks_list, stored_data, symbol, btn_ids):
        ctx = callback_context
        if not ctx.triggered or not stored_data:
            raise dash.exceptions.PreventUpdate

        triggered_id = ctx.triggered_id
        if not triggered_id or not isinstance(triggered_id, dict):
            raise dash.exceptions.PreventUpdate

        active_period = triggered_id['index']
        df = pd.DataFrame(stored_data)
        filtered_df = filter_data_for_period(df, active_period)
        pct_change = calculate_period_change(filtered_df)
        fig = create_stock_chart_figure(filtered_df, symbol)

        btn_styles = []
        badge_children_list = []
        badge_styles = []
        for btn_id in btn_ids:
            period = btn_id['index']
            is_active = period == active_period
            btn_styles.append(_period_btn_style(is_active))

            if is_active:
                children, style = _period_badge(pct_change)
            else:
                children, style = [], {'display': 'none'}
            badge_children_list.append(children)
            badge_styles.append(style)

        return fig, btn_styles, badge_children_list, badge_styles


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

    if watchlist_id:
        watchlist = Watchlist.query.get(watchlist_id)
        if watchlist:
            return create_watchlist_content(watchlist)
        else:
            return html.P(
                "Select a watchlist to view stocks or create a new watchlist.")
    else:
        return html.P(
            "Select a watchlist to view stocks or create a new watchlist.")


def create_empty_watchlist_section():
    return html.Div([
        html.Span("📋", style={'fontSize': '32px', 'marginBottom': '12px', 'display': 'block'}),
        html.P("Create your first watchlist above to start tracking stocks.", style={
            'color': COLORS['text_muted'],
            'fontSize': '0.9rem'
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
            ], style={'display': 'flex', 'alignItems': 'center'}),
            dbc.Button(
                'Delete',
                id={'type': 'delete-watchlist', 'index': watchlist.id},
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
            'padding': '16px 20px',
            'background': 'rgba(15, 23, 42, 0.5)',
            'borderBottom': f'1px solid {COLORS["border"]}',
            'display': 'flex',
            'justifyContent': 'space-between',
            'alignItems': 'center'
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
        # Fetch up to 10 years of daily OHLCV data so all period buttons
        # (1D through MAX) can slice from the same dataset.
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=365 * 10)).strftime('%Y-%m-%d')
        historical_data = get_stock_data(stock_symbol, start_date, end_date)

        if not historical_data:
            return html.Div(f"No historical data available for {stock_symbol}",
                        className="alert alert-warning m-3 p-3"), pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(historical_data)

        if 'close' in df.columns:
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

            return stock_info, df
        else:
            return html.Div(f"Insufficient data for {stock_symbol}", className="alert alert-warning m-3 p-3"), pd.DataFrame()

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
        }), pd.DataFrame()

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