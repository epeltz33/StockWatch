from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import logging
import os
from dotenv import load_dotenv
from polygon import RESTClient
from app.extensions import db, cache
from app.models import Stock
from app.utils.cache_manager import StockCache
from sqlalchemy.exc import IntegrityError

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EASTERN_TZ = ZoneInfo("America/New_York")
MARKET_OPEN_ET = time(9, 30)
MARKET_CLOSE_ET = time(16, 0)

api_key = os.getenv('POLYGON_API_KEY')
polygon_client = RESTClient(api_key) if api_key else None


def _get_client() -> RESTClient:
    """Return a Polygon RESTClient, creating it if necessary."""
    global polygon_client
    if polygon_client is None:
        key = os.getenv('POLYGON_API_KEY')
        if not key:
            raise RuntimeError('Polygon API key not configured')
        polygon_client = RESTClient(key)
    return polygon_client


def is_rate_limit_error(exc: Exception) -> bool:
    """Return True when an exception indicates Polygon rate limiting."""
    message = str(exc).lower()
    return '429' in message or 'too many' in message


def get_stock_price(symbol: str) -> Optional[float]:
    """Get current stock price from Polygon API (cached for 5 minutes)."""
    stock_cache = StockCache(cache)
    cached_price = stock_cache.get_cached_data(symbol, "price")
    if cached_price is not None:
        return cached_price

    try:
        date = get_most_recent_trading_day()
        client = _get_client()
        resp = client.get_daily_open_close_agg(symbol, date)
        price = resp.close if resp else None
        if price is not None:
            stock_cache.set_cached_data(symbol, "price", price)
        return price
    except Exception as e:
        logger.error(f"Error fetching stock price for {symbol}: {str(e)}")
        return None


def get_stock_data(symbol: str, from_date: str, to_date: str) -> List[Dict[str, Any]]:
    """Get historical OHLCV data from Polygon API (cached for 1 hour)."""
    stock_cache = StockCache(cache)
    cached_data = stock_cache.get_cached_data(
        symbol, "historical", start_date=from_date, end_date=to_date
    )
    if cached_data is not None:
        return cached_data

    try:
        client = _get_client()
        aggs = client.get_aggs(
            ticker=symbol,
            multiplier=1,
            timespan="day",
            from_=from_date,
            to=to_date,
            adjusted=True,
            sort="asc",
            limit=50000,
        )

        historical_data = []
        for agg in aggs or []:
            historical_data.append({
                'date': datetime.fromtimestamp(agg.timestamp / 1000).strftime('%Y-%m-%d'),
                'open': agg.open,
                'high': agg.high,
                'low': agg.low,
                'close': agg.close,
                'volume': agg.volume,
            })

        if historical_data:
            stock_cache.set_cached_data(
                symbol, "historical", historical_data,
                start_date=from_date, end_date=to_date,
            )
        return historical_data
    except Exception as e:
        logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
        return []


def get_intraday_stock_data(
    symbol: str,
    max_lookback_days: int = 7,
    aggregate_configs=None,
) -> List[Dict[str, Any]]:
    """Fetch regular-session intraday bars for the latest available session (cached 5 min)."""
    stock_cache = StockCache(cache)
    cached_data = stock_cache.get_cached_data(symbol, "intraday")
    if cached_data is not None:
        return cached_data

    aggregate_configs = aggregate_configs or ((1, "minute"), (5, "minute"))
    try:
        candidate_date = datetime.now(EASTERN_TZ).date()
        attempted_weekdays = 0

        while attempted_weekdays < max_lookback_days:
            if candidate_date.weekday() >= 5:
                candidate_date -= timedelta(days=1)
                continue

            attempted_weekdays += 1
            date_str = candidate_date.strftime('%Y-%m-%d')
            for multiplier, timespan in aggregate_configs:
                try:
                    client = _get_client()
                    aggs = client.get_aggs(
                        ticker=symbol,
                        multiplier=multiplier,
                        timespan=timespan,
                        from_=date_str,
                        to=date_str,
                        adjusted=True,
                        sort="asc",
                        limit=50000,
                    )
                except Exception as e:
                    logger.warning(
                        f"Intraday {multiplier}-{timespan} data unavailable for "
                        f"{symbol} on {date_str}: {str(e)}"
                    )
                    continue

                intraday_data = []
                for agg in aggs or []:
                    bar_dt = datetime.fromtimestamp(
                        agg.timestamp / 1000, tz=ZoneInfo("UTC")
                    ).astimezone(EASTERN_TZ)
                    if MARKET_OPEN_ET <= bar_dt.time() <= MARKET_CLOSE_ET:
                        intraday_data.append({
                            'datetime': bar_dt.isoformat(),
                            'date': bar_dt.strftime('%Y-%m-%d'),
                            'time': bar_dt.strftime('%H:%M'),
                            'open': agg.open,
                            'high': agg.high,
                            'low': agg.low,
                            'close': agg.close,
                            'volume': agg.volume,
                            'resolution': 'intraday',
                            'interval': f"{multiplier}-{timespan}",
                        })

                if intraday_data:
                    stock_cache.set_cached_data(symbol, "intraday", intraday_data)
                    return intraday_data

            candidate_date -= timedelta(days=1)

        return []
    except Exception as e:
        logger.error(f"Error fetching intraday data for {symbol}: {str(e)}")
        return []


def _as_text(value: Any, default: str = 'N/A') -> str:
    return value if isinstance(value, str) else default


def _as_number(value: Any) -> Optional[float]:
    return value if isinstance(value, (int, float)) else None


def _append_api_key(url: Optional[str]) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None
    separator = '?' if '?' not in url else '&'
    return f"{url}{separator}apiKey={api_key}"


def get_company_details(symbol: str) -> Optional[Dict[str, Any]]:
    """Get company details from Polygon API (cached for 24 hours)."""
    stock_cache = StockCache(cache)
    cached_details = stock_cache.get_cached_data(symbol, "details")
    if cached_details is not None:
        return cached_details

    try:
        client = _get_client()
        ticker_details = client.get_ticker_details(symbol)
        if not ticker_details:
            return None

        icon_url = None
        logo_url = None

        if hasattr(ticker_details, 'branding'):
            branding = ticker_details.branding
            if isinstance(branding, dict):
                icon_url = branding.get('icon_url')
                logo_url = branding.get('logo_url')
            elif branding is not None:
                icon_url = getattr(branding, 'icon_url', None)
                logo_url = getattr(branding, 'logo_url', None)
                if icon_url is not None and not isinstance(icon_url, str):
                    icon_url = None
                if logo_url is not None and not isinstance(logo_url, str):
                    logo_url = None

        if not icon_url and hasattr(ticker_details, 'results'):
            results = ticker_details.results
            if hasattr(results, 'branding'):
                branding = results.branding
                if isinstance(branding, dict):
                    icon_url = branding.get('icon_url')
                    logo_url = branding.get('logo_url')
                elif branding is not None:
                    icon_url = getattr(branding, 'icon_url', None)
                    logo_url = getattr(branding, 'logo_url', None)
                    if icon_url is not None and not isinstance(icon_url, str):
                        icon_url = None
                    if logo_url is not None and not isinstance(logo_url, str):
                        logo_url = None

        icon_url = _append_api_key(icon_url)
        logo_url = _append_api_key(logo_url)

        name = symbol
        if hasattr(ticker_details, 'name'):
            name = ticker_details.name
        elif hasattr(ticker_details, 'results') and hasattr(ticker_details.results, 'name'):
            name = ticker_details.results.name

        market_cap = getattr(ticker_details, 'market_cap', None)
        if market_cap is None and hasattr(ticker_details, 'results'):
            market_cap = getattr(ticker_details.results, 'market_cap', None)

        website = getattr(ticker_details, 'homepage_url', None)
        if website is None and hasattr(ticker_details, 'results'):
            website = getattr(ticker_details.results, 'homepage_url', None)

        list_date = getattr(ticker_details, 'list_date', None)
        if list_date is None and hasattr(ticker_details, 'results'):
            list_date = getattr(ticker_details.results, 'list_date', None)

        exchange = getattr(ticker_details, 'primary_exchange', None)
        if exchange is None and hasattr(ticker_details, 'results'):
            exchange = getattr(ticker_details.results, 'primary_exchange', None)

        description = ""
        raw_description = getattr(ticker_details, 'description', None)
        if not isinstance(raw_description, str) and hasattr(ticker_details, 'results'):
            raw_description = getattr(ticker_details.results, 'description', None)
        if isinstance(raw_description, str) and raw_description:
            description = raw_description[:150]
            if len(raw_description) > 150:
                description += "..."

        name = _as_text(name, symbol)
        market_cap = _as_number(market_cap)
        website = _as_text(website, '') or None
        list_date = _as_text(list_date, '') or None
        exchange = _as_text(exchange, '') or None

        details = {
            'name': name,
            'description': description,
            'market_cap': market_cap,
            'icon_url': icon_url,
            'logo_url': logo_url,
            'website': website,
            'list_date': list_date,
            'exchange': exchange,
            'primary_exchange': exchange,
            'sector': _as_text(getattr(ticker_details, 'sector', 'N/A')),
            'industry': _as_text(getattr(ticker_details, 'industry', 'N/A')),
        }
        stock_cache.set_cached_data(symbol, "details", details)
        return details
    except Exception as e:
        logger.error(f"Error fetching company details for {symbol}: {str(e)}")
        return None


def get_most_recent_trading_day() -> str:
    """Calculate the most recent trading day."""
    now = datetime.now()
    market_close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)

    if now <= market_close_time and now.weekday() < 5:
        most_recent_trading_day = now - timedelta(days=1) if now.weekday() > 0 else now
    else:
        days_to_subtract = 1
        if now.weekday() == 5:
            days_to_subtract = 1
        elif now.weekday() == 6:
            days_to_subtract = 2
        most_recent_trading_day = now - timedelta(days=days_to_subtract)

    if most_recent_trading_day.weekday() == 5:
        most_recent_trading_day -= timedelta(days=1)
    elif most_recent_trading_day.weekday() == 6:
        most_recent_trading_day -= timedelta(days=2)

    return most_recent_trading_day.strftime('%Y-%m-%d')


def get_all_stocks() -> List[Stock]:
    """Get all stocks from the database."""
    return Stock.query.all()


def get_stock_by_symbol(symbol: str) -> Optional[Stock]:
    """Get a stock by its symbol from the database."""
    return Stock.query.filter_by(symbol=symbol).first()


def create_stock(symbol: str, name: str) -> Optional[Stock]:
    """Create a new stock entry in the database."""
    stock = Stock(symbol=symbol, name=name)
    db.session.add(stock)
    try:
        db.session.commit()
        return stock
    except IntegrityError:
        db.session.rollback()
        logger.error(f"Failed to create stock {symbol}: IntegrityError")
        return None


def delete_stock(symbol: str) -> bool:
    """Delete a stock from the database."""
    stock = get_stock_by_symbol(symbol)
    if stock:
        try:
            db.session.delete(stock)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete stock {symbol}: {str(e)}")
            return False
    return False
