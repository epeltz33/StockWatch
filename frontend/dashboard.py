import dash
from dash import html, dcc, Input, Output, State, callback_context, no_update, ALL
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pandas as pd
from app import db
from flask_login import current_user
from app.models import Watchlist, Stock
from app.services.stock_services import (
    get_stock_data,
    get_stock_price,
    get_company_details,
    get_intraday_stock_data,
)
from sqlalchemy.exc import SQLAlchemyError
import logging
import json

# Figure palette only — UI chrome is styled by assets/custom.css classes.
# Gain/loss color is reserved for market data; accent is UI-interactive only.
COLORS = {
    'text': '#E8ECF4',
    'text_secondary': '#A9B2C3',
    'text_muted': '#77839B',
    'gain': '#2FBF71',
    'loss': '#F0544F',
    'flat': '#77839B',
    'accent': '#5B8DEF',
    'grid': 'rgba(49, 64, 92, 0.35)',
    'spike': 'rgba(121, 139, 169, 0.55)',
    'hover_bg': 'rgba(18, 24, 38, 0.96)',
    'hover_border': '#31405C',
    'volume_flat': 'rgba(119, 131, 155, 0.30)',
    'volume_up': 'rgba(47, 191, 113, 0.35)',
    'volume_down': 'rgba(240, 84, 79, 0.35)',
}

FONT_UI = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
FONT_DATA = "'IBM Plex Mono', 'SF Mono', Menlo, Consolas, monospace"

ACCENT = '#5B8DEF'
ADD_TO_WATCHLIST_LABEL = '＋ Watchlist'

PERIODS = ['1D', '5D', '1M', '6M', 'YTD', '1Y', '5Y', '10Y', 'MAX']
PERIOD_DISPLAY_LABELS = {
    '1D': 'Today',
}
PERIOD_BUTTON_TITLES = {
    '1D': 'Intraday prices for the latest regular session (9:30 AM–4:00 PM ET)',
    '5D': 'Daily bars for the last ~5 trading days',
    '1M': 'Daily bars for the last month',
    '6M': 'Daily bars for the last 6 months',
    'YTD': 'Daily bars since January 1',
    '1Y': 'Daily bars for the last year',
    '5Y': 'Daily bars for the last 5 years',
    '10Y': 'Daily bars for the last 10 years',
    'MAX': 'All available daily history',
}


def period_display_label(period):
    """Return the user-facing label for a chart period button."""
    return PERIOD_DISPLAY_LABELS.get(period, period)


def period_button_title(period):
    """Return hover text describing what each period button shows."""
    return PERIOD_BUTTON_TITLES.get(period, f'{period} chart')


def filter_data_for_period(df, period):
    """Filter OHLCV dataframe to the selected time period.

    Period definitions (calendar-day based, using daily bars):
    - 1D: not used here; the chart callback loads dedicated intraday bars instead
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

    if period == '1D':
        return df

    period_days = {
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


def calculate_fifty_two_week_range(df):
    """Return formatted 52-week low/high from the last year of daily bars."""
    filtered = filter_data_for_period(df, '1Y')
    if filtered.empty or 'close' not in filtered.columns:
        return "N/A"

    if 'low' in filtered.columns and 'high' in filtered.columns:
        low = filtered['low'].min()
        high = filtered['high'].max()
    else:
        low = filtered['close'].min()
        high = filtered['close'].max()

    return f"${low:.2f} - ${high:.2f}"


def calculate_intraday_period_change(df):
    """Return regular-session 1D performance from first bar open to latest close."""
    if df.empty or len(df) < 1 or 'open' not in df.columns or 'close' not in df.columns:
        return 0.0
    session_open = df['open'].iloc[0]
    latest_close = df['close'].iloc[-1]
    if session_open == 0:
        return 0.0
    return ((latest_close - session_open) / session_open) * 100


def period_price_change(df, is_intraday=False):
    """Return (absolute $ change, % change) over the filtered range.

    Daily ranges compare first close to last close; intraday compares the
    session open to the latest close (same base as calculate_intraday_period_change).
    """
    if df.empty or 'close' not in df.columns:
        return 0.0, 0.0
    if is_intraday:
        if 'open' not in df.columns:
            return 0.0, 0.0
        base = df['open'].iloc[0]
    else:
        base = df['close'].iloc[0]
    last = df['close'].iloc[-1]
    if base == 0:
        return 0.0, 0.0
    return last - base, ((last - base) / base) * 100


def _price_axis_range(df):
    """Return a padded price range so chart movement is readable."""
    price_columns = [col for col in ['low', 'high', 'close'] if col in df.columns]
    if not price_columns:
        return None

    prices = pd.concat([pd.to_numeric(df[col], errors='coerce') for col in price_columns]).dropna()
    if prices.empty:
        return None

    min_price = prices.min()
    max_price = prices.max()
    price_span = max_price - min_price
    if price_span == 0:
        padding = max(abs(max_price) * 0.005, 0.5)
    else:
        padding = max(price_span * 0.15, 0.25)
    lower_bound = min_price - padding
    if min_price > 0:
        lower_bound = max(lower_bound, min_price * 0.9)
    return [lower_bound, max_price + padding]


def _price_tick_format(price_range):
    """Use cents for tight ranges and whole dollars for wider ranges."""
    if not price_range:
        return ',.0f'
    return ',.2f' if (price_range[1] - price_range[0]) < 20 else ',.0f'


def _date_axis_tick_format(period):
    """Return a readable date tick format for each daily chart period."""
    if period in ('5D', '1M'):
        return '%b %-d'
    if period in ('5Y', '10Y', 'MAX'):
        return '%Y'
    return '%b %Y'


def _date_axis_tick_spacing(period):
    """Return a stable date tick spacing for each daily chart period."""
    if period == '5D':
        return 24 * 60 * 60 * 1000
    if period == '1M':
        return 7 * 24 * 60 * 60 * 1000
    if period in ('5Y', '10Y', 'MAX'):
        return 'M12'
    return 'M1'


def _hex_to_rgba(hex_color, alpha):
    """'#RRGGBB' -> 'rgba(r, g, b, a)'."""
    hex_color = hex_color.lstrip('#')
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f'rgba({r}, {g}, {b}, {alpha})'


def _direction_color(df, is_intraday):
    """Gain green when the period is up, loss red when down, muted when flat."""
    abs_change, _ = period_price_change(df, is_intraday=is_intraday)
    if abs_change > 0:
        return COLORS['gain']
    if abs_change < 0:
        return COLORS['loss']
    return COLORS['flat']


def create_stock_chart_figure(df, symbol, period=None):
    """Price line + gradient band (top) and volume bars (bottom), shared x-axis.

    The line, gradient, and volume tints take the period's gain/loss color so
    the chart itself reads direction. Y-axes sit on the right; the custom Dash
    period buttons are the sole period control (no Plotly rangeselector).
    """
    is_intraday = period == '1D'

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.85, 0.15],
    )

    if df.empty:
        message = f"No intraday data available for {symbol}" if is_intraday else f"No chart data available for {symbol}"
        fig.add_annotation(
            text=message,
            x=0.5,
            y=0.5,
            xref='paper',
            yref='paper',
            showarrow=False,
            font=dict(size=14, color=COLORS['text_muted']),
        )
        fig.update_layout(
            title=None,
            template='plotly_dark',
            margin=dict(l=10, r=55, t=10, b=25),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color=COLORS['text'], family=FONT_UI),
            height=440,
            autosize=True,
            showlegend=False,
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return fig

    x_col = 'datetime' if is_intraday and 'datetime' in df.columns else 'date'
    price_hovertemplate = (
        '<b>%{x|%I:%M %p}</b><br>$%{y:.2f}<extra></extra>'
        if is_intraday
        else '<b>%{x|%b %d, %Y}</b><br>$%{y:.2f}<extra></extra>'
    )

    line_color = _direction_color(df, is_intraday)
    price_range = _price_axis_range(df)

    # --- price line (kept as fig.data[0]) ---
    fig.add_trace(go.Scatter(
        x=df[x_col],
        y=df['close'],
        mode='lines',
        line=dict(color=line_color, width=2, shape='spline'),
        name='Price',
        hovertemplate=price_hovertemplate,
    ), row=1, col=1)

    # --- gradient band between the visible lower bound and the price line ---
    # Plotly's fill gradient spans the fill's bounding box, so an invisible
    # baseline at the clamped axis floor keeps the fade inside the visible band
    # instead of stretching down to zero.
    if len(df) >= 2:
        baseline_y = price_range[0] if price_range else float(df['close'].min())
        fig.add_trace(go.Scatter(
            x=df[x_col],
            y=[baseline_y] * len(df),
            mode='lines',
            line=dict(width=0),
            hoverinfo='skip',
            showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df[x_col],
            y=df['close'],
            mode='lines',
            line=dict(width=0, shape='spline'),
            fill='tonexty',
            fillgradient=dict(
                type='vertical',
                colorscale=[
                    [0.0, _hex_to_rgba(line_color, 0.0)],
                    [1.0, _hex_to_rgba(line_color, 0.22)],
                ],
            ),
            hoverinfo='skip',
            showlegend=False,
        ), row=1, col=1)

    # --- volume bars (subtle, no axis labels) ---
    if 'volume' in df.columns and df['volume'].notna().any():
        colors = [COLORS['volume_flat'] if i == 0
                  else COLORS['volume_up'] if df['close'].iloc[i] >= df['close'].iloc[i - 1]
                  else COLORS['volume_down']
                  for i in range(len(df))]

        fig.add_trace(go.Bar(
            x=df[x_col],
            y=df['volume'],
            marker_color=colors,
            name='Volume',
            hovertemplate=(
                '<b>%{x|%I:%M %p}</b><br>Vol: %{y:,.0f}<extra></extra>'
                if is_intraday
                else 'Vol: %{y:,.0f}<extra></extra>'
            ),
        ), row=2, col=1)

    fig.update_layout(
        title=None,
        template='plotly_dark',
        margin=dict(l=10, r=55, t=10, b=25),
        hovermode='x unified',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=COLORS['text'], family=FONT_UI),
        height=440,
        autosize=True,
        showlegend=False,
        hoverlabel=dict(
            bgcolor=COLORS['hover_bg'],
            font_size=13,
            font_family=FONT_DATA,
            bordercolor=COLORS['hover_border'],
            font_color=COLORS['text'],
        ),
        bargap=0.3,
    )

    price_yaxis_options = dict(
        showgrid=True, gridwidth=1, gridcolor=COLORS['grid'],
        showline=False, tickfont=dict(size=11, color=COLORS['text_muted'], family=FONT_DATA),
        tickprefix='$', tickformat=',.0f', side='right',
        row=1, col=1,
    )
    if price_range:
        price_yaxis_options.update(range=price_range, tickformat=_price_tick_format(price_range))
    # price y-axis (right)
    fig.update_yaxes(**price_yaxis_options)
    # volume y-axis — hidden tick labels, just the bars for visual context
    fig.update_yaxes(
        showgrid=False, showline=False, showticklabels=False,
        row=2, col=1,
    )

    spike_options = dict(
        showspikes=True, spikemode='across', spikesnap='cursor',
        spikethickness=1, spikedash='dot', spikecolor=COLORS['spike'],
    )
    # price x-axis — hide ticks (shared with volume below), crosshair spike on
    fig.update_xaxes(
        showgrid=True, gridwidth=1, gridcolor=COLORS['grid'],
        showline=False, showticklabels=False,
        row=1, col=1,
        **spike_options,
    )
    # volume x-axis — show date ticks here only
    xaxis_options = dict(
        showgrid=False, showline=False,
        tickfont=dict(size=10, color=COLORS['text_muted'], family=FONT_DATA),
        row=2, col=1,
        **spike_options,
    )
    if is_intraday:
        xaxis_options.update(type='date', tickformat='%I:%M %p')
    else:
        xaxis_options.update(
            type='date',
            tickformat=_date_axis_tick_format(period),
            dtick=_date_axis_tick_spacing(period),
        )
    fig.update_xaxes(**xaxis_options)

    return fig


def _period_btn_class(is_active):
    """Return the CSS class string for a period button."""
    return 'period-btn period-btn--active' if is_active else 'period-btn'


def build_period_toolbar(active_period):
    """Build the segmented period-selector control."""
    return html.Div(
        [
            html.Button(
                period_display_label(period),
                id={'type': 'period-btn', 'index': period},
                n_clicks=0,
                title=period_button_title(period),
                className=_period_btn_class(period == active_period),
            )
            for period in PERIODS
        ],
        className='period-seg',
        role='group',
    )


def build_change_readout(abs_change, pct_change, period):
    """Chip + period tag shown next to the price, colored by direction."""
    if abs_change > 0:
        chip_class, arrow, sign = 'change-chip change-chip--up', '▲', '+'
    elif abs_change < 0:
        chip_class, arrow, sign = 'change-chip change-chip--down', '▼', '-'
    else:
        chip_class, arrow, sign = 'change-chip change-chip--flat', '', ''

    label = f"{sign}${abs(abs_change):,.2f} ({pct_change:+.2f}%)"
    chip_children = ([html.Span(arrow, className='chip-arrow')] if arrow else []) + [label]

    return [
        html.Span(chip_children, className=chip_class),
        html.Span(period_display_label(period), className='readout-period'),
    ]


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_dash_app(flask_app):
    dash_app = dash.Dash(__name__, server=flask_app, url_base_pathname='/dash/',
                        external_stylesheets=[
                            dbc.themes.BOOTSTRAP,
                            'https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap'],
                        assets_folder='assets',
                        suppress_callback_exceptions=True)

    dash_app.layout = create_layout()

    register_callbacks(dash_app)

    return dash_app


def empty_state(icon, message, sub=None):
    """Muted placeholder shown before a container has been populated by a callback."""
    children = [
        html.Div(icon, className='empty-state-icon'),
        html.Div(message, className='empty-state-title'),
    ]
    if sub:
        children.append(html.Div(sub, className='empty-state-sub'))
    return html.Div(children, className='empty-state')


def create_layout():
    return dbc.Container([
        # Search toolbar
        html.Div([
            dbc.InputGroup([
                dbc.Input(id='stock-input',
                        type='text',
                        placeholder='Search ticker — e.g. AAPL',
                        autoComplete='off'),
                dbc.Button('Search', id='search-button', className='sw-btn--primary'),
            ], className='search-group'),
        ], className='toolbar'),

        # Chart hero
        html.Div([
            dcc.Loading(
                id='loading-chart',
                type='circle',
                color=ACCENT,
                children=html.Div(
                    id='stock-chart-container',
                    className='chart-container',
                    children=empty_state(
                        '\U0001F4C8',
                        'Search a ticker to begin',
                        'Try AAPL, MSFT, or SNDK — press Enter to search.',
                    ),
                ),
            ),
        ], className='sw-card chart-card'),

        # Details (left) + watchlists (right)
        dbc.Row([
            dbc.Col(
                dcc.Loading(
                    id='loading-stock-data',
                    type='circle',
                    color=ACCENT,
                    children=html.Div(id='stock-data'),
                ),
                lg=8, md=12, className='mb-4',
            ),
            dbc.Col(
                html.Div([
                    html.H2('Watchlists', className='panel-title'),
                    dcc.Dropdown(id='watchlist-dropdown',
                            options=[],
                            placeholder='Select a watchlist',
                            className='mb-3 dark-dropdown'),
                    dbc.InputGroup([
                        dbc.Input(id='new-watchlist-input',
                                type='text',
                                placeholder='New watchlist name'),
                        dbc.Button('Create', id='create-watchlist-button', className='sw-btn--ghost'),
                    ], className='mb-3'),
                    dcc.Loading(
                        id='loading-watchlist',
                        type='circle',
                        color=ACCENT,
                        children=html.Div(
                            id='watchlist-section',
                            children=empty_state(
                                '★',
                                'No watchlist selected',
                                'Create one above or pick an existing watchlist.',
                            ),
                        ),
                    ),
                ], className='sw-card watchlist-card'),
                lg=4, md=12, className='mb-4',
            ),
        ], className='g-4'),

        # Data stores for chart period selection
        dcc.Store(id='stock-ohlcv-store', data=None),
        dcc.Store(id='stock-intraday-store', data=None),
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
    ], fluid=True, className='py-2 sw-page')


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
                reset_texts = [ADD_TO_WATCHLIST_LABEL] * num_add_buttons
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
        Output('stock-intraday-store', 'data'),
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
            return no_update, no_update, no_update, no_update, no_update, no_update

        # Get the specific property and value that triggered the callback
        triggered_prop = ctx.triggered[0]['prop_id']
        triggered_value = ctx.triggered[0]['value']

        # --- Check for valid click triggers ---

        # Scenario 1: A watchlist stock button was clicked
        if triggered_prop.endswith('.n_clicks') and '"type":"load-watchlist-stock"' in triggered_prop:
            if triggered_value is not None and triggered_value > 0:
                json_part = triggered_prop.split('.')[0]
                try:
                    clicked_stock_info = json.loads(json_part)
                    clicked_stock = clicked_stock_info.get('index')
                    trigger_source = 'watchlist'
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse watchlist trigger prop_id: {triggered_prop}")
                    return no_update, no_update, no_update, no_update, no_update, no_update

        elif triggered_prop in ('search-button.n_clicks', 'stock-input.n_submit'):
            if triggered_value is not None and triggered_value > 0:
                if search_input:
                    clicked_stock = search_input.strip().upper()
                    trigger_source = 'search'
                    logger.info(f"Search triggered ({triggered_prop}) for: {clicked_stock}")

        # --- Process if a valid click was identified ---

        if not clicked_stock or not trigger_source:
            return no_update, no_update, no_update, no_update, no_update, no_update

        stock_info, df = fetch_and_display_stock_data(clicked_stock)

        if df.empty:
            chart_container = empty_state(
                '⚠',
                f'No chart data available for {clicked_stock}',
                'Check the ticker symbol, or wait a moment if data is rate-limited.',
            )
            stock_input_update = clicked_stock if trigger_source == 'search' else no_update
            details = stock_info if not isinstance(stock_info, dict) else no_update
            return details, chart_container, stock_input_update, no_update, no_update, no_update

        intraday_data = []

        # Default period is 1Y; build initial chart, price readout, and toolbar
        default_period = '1Y'
        filtered_df = filter_data_for_period(df, default_period)
        abs_change, pct_change = period_price_change(filtered_df)
        chart_fig = create_stock_chart_figure(filtered_df, clicked_stock, period=default_period)

        chart_container = html.Div([
            stock_info['header'],
            html.Div([
                html.Div([
                    html.Div([
                        html.Span(f"${stock_info['price']:,.2f}", className='price-lg'),
                        html.Div(
                            build_change_readout(abs_change, pct_change, default_period),
                            id='chart-change-readout',
                            className='readout',
                        ),
                    ], className='price-row'),
                    html.Span('At close', className='price-caption'),
                ]),
                build_period_toolbar(default_period),
            ], className='chart-controls'),
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
        ])

        stock_input_update = clicked_stock if trigger_source == 'search' else no_update
        return (stock_info['details'], chart_container, stock_input_update,
                df.to_dict('records'), intraday_data, clicked_stock)

    # --- Period-button callback: filter data and update chart + readout ---
    # `stock-intraday-store` is also written by `update_stock_data`; declaring
    # this Output as a duplicate lets both callbacks target the same store
    # without Dash raising DuplicateCallback at registration time.
    @dash_app.callback(
        [Output('stock-chart', 'figure'),
         Output({'type': 'period-btn', 'index': ALL}, 'className'),
         Output('chart-change-readout', 'children'),
         Output('stock-intraday-store', 'data', allow_duplicate=True)],
        Input({'type': 'period-btn', 'index': ALL}, 'n_clicks'),
        [State('stock-ohlcv-store', 'data'),
         State('stock-intraday-store', 'data'),
         State('stock-symbol-store', 'data'),
         State({'type': 'period-btn', 'index': ALL}, 'id')],
        prevent_initial_call=True,
    )
    def update_chart_period(n_clicks_list, stored_data, intraday_data, symbol, btn_ids):
        ctx = callback_context
        if not ctx.triggered or not stored_data:
            raise dash.exceptions.PreventUpdate

        triggered_id = ctx.triggered_id
        if not triggered_id or not isinstance(triggered_id, dict):
            raise dash.exceptions.PreventUpdate

        # Re-rendering the chart container recreates the period buttons, which
        # fires this callback with n_clicks=0. Only act on a real click.
        if not ctx.triggered[0].get('value'):
            raise dash.exceptions.PreventUpdate

        active_period = triggered_id['index']
        intraday_update = no_update
        if active_period == '1D':
            if not intraday_data and symbol:
                intraday_data = get_intraday_stock_data(symbol)
                intraday_update = intraday_data
            filtered_df = pd.DataFrame(intraday_data or [])
            abs_change, pct_change = period_price_change(filtered_df, is_intraday=True)
        else:
            df = pd.DataFrame(stored_data)
            filtered_df = filter_data_for_period(df, active_period)
            abs_change, pct_change = period_price_change(filtered_df)
        fig = create_stock_chart_figure(filtered_df, symbol, period=active_period)

        btn_classes = [
            _period_btn_class(btn_id['index'] == active_period) for btn_id in btn_ids
        ]
        readout = build_change_readout(abs_change, pct_change, active_period)

        return fig, btn_classes, readout, intraday_update


def create_new_stock(stock_symbol):
    try:
        logger.info(f"Creating new stock: {stock_symbol}")
        company_details = get_company_details(stock_symbol)
        stock_name = company_details.get('name', stock_symbol) if company_details else stock_symbol
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
        return empty_state('\U0001F512', 'Please log in to view your watchlists.')

    watchlists = current_user.watchlists.all()
    if not watchlists:
        return create_empty_watchlist_section()

    if watchlist_id:
        watchlist = Watchlist.query.get(watchlist_id)
        if watchlist:
            return create_watchlist_content(watchlist)

    return empty_state(
        '★',
        'No watchlist selected',
        'Pick a watchlist above to view its stocks.',
    )


def create_empty_watchlist_section():
    return empty_state(
        '\U0001F4CB',
        'No watchlists yet',
        'Create your first watchlist above to start tracking stocks.',
    )


def create_watchlist_content(watchlist):
    stocks = list(watchlist.stocks)

    rows = [
        html.Div([
            html.Div([
                html.Span(stock.symbol, className='watchlist-ticker'),
                html.Span(stock.name or '', className='watchlist-company'),
            ], className='watchlist-row-info'),
            html.Div([
                dbc.Button(
                    'View',
                    id={'type': 'load-watchlist-stock', 'index': stock.symbol},
                    size='sm',
                    className='sw-btn--ghost sw-btn--sm',
                ),
                dbc.Button(
                    'Remove',
                    id={'type': 'remove-from-watchlist', 'index': stock.id},
                    size='sm',
                    className='sw-btn--danger sw-btn--sm',
                ),
            ], className='row-actions'),
        ], className='watchlist-row')
        for stock in stocks
    ]

    return html.Div([
        html.Div([
            html.H5(watchlist.name, className='watchlist-name'),
            dbc.Button(
                'Delete',
                id={'type': 'delete-watchlist', 'index': watchlist.id},
                size='sm',
                className='sw-btn--danger sw-btn--sm',
            ),
        ], className='watchlist-panel-header'),
        html.Div(rows) if rows else empty_state(
            '\U0001F4CA',
            'No stocks added yet',
            'Search for stocks and add them here.',
        ),
    ], className='watchlist-panel')


def _format_market_cap(market_cap):
    """Compact terminal-style market cap: $3.45T / $12.30B / $450.00M."""
    if not isinstance(market_cap, (int, float)) or market_cap <= 0:
        return "N/A"
    if market_cap >= 1e12:
        return f"${market_cap / 1e12:,.2f}T"
    if market_cap >= 1e9:
        return f"${market_cap / 1e9:,.2f}B"
    if market_cap >= 1e6:
        return f"${market_cap / 1e6:,.2f}M"
    return f"${market_cap:,.2f}"


def _stat_cell(label, value_children, large=False):
    value_class = 'stat-value stat-value--lg' if large else 'stat-value'
    return html.Div([
        html.Div(label, className='stat-label'),
        html.Div(value_children, className=value_class),
    ], className='stat-cell')


def fetch_and_display_stock_data(stock_symbol):
    """Fetch history + details for a symbol.

    Returns (info, df): on success `info` is a dict with 'header' (chart-card
    header row), 'details' (stat grid + about card), and 'price'; on failure
    `info` is a renderable error/warning component and `df` is empty.
    """
    try:
        # Fetch up to 10 years of daily OHLCV data so all period buttons
        # (1D through MAX) can slice from the same dataset.
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=365 * 10)).strftime('%Y-%m-%d')
        historical_data = get_stock_data(stock_symbol, start_date, end_date)

        if not historical_data:
            return html.Div([
                html.P(f"No historical data available for {stock_symbol}"),
                html.P(
                    "Market data may be temporarily rate-limited. "
                    "Please wait a moment and try again."
                ),
            ], className='warn-panel'), pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(historical_data)

        if 'close' not in df.columns:
            return html.Div([
                html.P(f"Insufficient data for {stock_symbol}"),
                html.P("The market data response was missing price history."),
            ], className='warn-panel'), pd.DataFrame()

        # Get current price from service function
        current_price = get_stock_price(stock_symbol)

        # Ensure we have a valid current price
        if current_price is None and not df.empty:
            current_price = df['close'].iloc[-1]
        elif current_price is None:
            current_price = 0

        # Calculate day-over-day change against the previous close
        previous_close = current_price  # Default fallback
        change_str = "0.00%"
        change_value = 0
        dollar_change = 0

        if len(df) > 1 and current_price is not None:
            previous_close = df['close'].iloc[-2]
            # Avoid division by zero
            if previous_close != 0:
                change_value = ((current_price - previous_close) / previous_close) * 100
                dollar_change = current_price - previous_close
                change_str = f"{change_value:+.2f}%"

        # Get company details
        company_details = get_company_details(stock_symbol)
        company_name = company_details.get('name', stock_symbol) if company_details else stock_symbol

        # Choose the best logo - prefer icon_url if available
        icon_url = company_details.get('icon_url', "") if company_details else ""
        logo_url = company_details.get('logo_url', "") if company_details else ""
        display_logo = icon_url or logo_url

        # Calculate 52-week range from the last year of data, not the full history.
        fifty_two_week_range = calculate_fifty_two_week_range(df)

        market_cap_str = _format_market_cap(
            company_details.get('market_cap') if company_details else None
        )
        website = company_details.get('website', None) if company_details else None
        exchange = company_details.get('exchange', None) if company_details else None
        description = company_details.get('description', '') if company_details else ''

        # Day-change chip for the details grid
        if change_value > 0:
            day_chip_class, day_arrow = 'change-chip change-chip--sm change-chip--up', '▲'
        elif change_value < 0:
            day_chip_class, day_arrow = 'change-chip change-chip--sm change-chip--down', '▼'
        else:
            day_chip_class, day_arrow = 'change-chip change-chip--sm change-chip--flat', ''

        day_chip = html.Span(
            ([html.Span(day_arrow, className='chip-arrow')] if day_arrow else [])
            + [f"{dollar_change:+.2f} ({change_str})"],
            className=day_chip_class,
        )

        # --- Chart-card header: identity + add-to-watchlist ---
        logo_content = (
            html.Img(src=display_logo, alt=f"{stock_symbol} logo")
            if display_logo
            else html.Span(stock_symbol[0].upper(), className='logo-monogram')
        )
        header = html.Div([
            html.Div([
                html.Div(logo_content, className='logo-frame'),
                html.Div([
                    html.H2(stock_symbol, className='chart-symbol'),
                    html.P(company_name, className='chart-company-name'),
                ], style={'minWidth': '0'}),
            ], className='chart-title-group'),
            dbc.Button(
                ADD_TO_WATCHLIST_LABEL,
                id={'type': 'add-to-watchlist', 'index': stock_symbol},
                className='sw-btn--ghost',
            ),
        ], className='chart-header')

        # --- Details card: stat grid + about ---
        website_value = (
            html.A(
                website.replace('https://', '').replace('http://', ''),
                href=website,
                target='_blank',
                rel='noopener noreferrer',
            )
            if website else 'N/A'
        )

        details = html.Div([
            html.H2('Stock Details', className='panel-title'),
            html.Div([
                _stat_cell('Current Price', [
                    html.Span(f"${current_price:,.2f}", style={'marginRight': '8px'}),
                    day_chip,
                ], large=True),
                _stat_cell('Previous Close', f"${previous_close:,.2f}"),
                _stat_cell('52-Week Range', fifty_two_week_range),
                _stat_cell('Market Cap', market_cap_str),
                _stat_cell('Exchange', exchange or 'N/A'),
                _stat_cell('Website', website_value),
            ], className='stat-grid'),
            html.Div([
                html.H2('About', className='panel-title'),
                html.P(description, className='about-text'),
            ]) if description else html.Div(),
        ], className='sw-card')

        return {'header': header, 'details': details, 'price': current_price}, df

    except Exception as e:
        logger.error(f"Error fetching stock data: {str(e)}")
        return html.Div([
            html.H4(f"Unable to load data for {stock_symbol}"),
            html.P("Please check the ticker symbol and try again."),
        ], className='error-panel'), pd.DataFrame()
