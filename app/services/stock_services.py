import logging
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from polygon import RESTClient
from sqlalchemy.exc import IntegrityError

from app.extensions import cache, db
from app.models import Stock
from app.utils.cache_manager import StockCache

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EASTERN_TZ = ZoneInfo("America/New_York")
MARKET_OPEN_ET = time(9, 30)
MARKET_CLOSE_ET = time(16, 0)
# v2: branding URLs are stored raw (no apiKey query param); bumping the
# version abandons older cached entries that embedded the key.
DETAILS_CACHE_VERSION = "raw-branding-v2"

api_key = os.getenv("POLYGON_API_KEY")
polygon_client = RESTClient(api_key) if api_key else None


def _get_client() -> RESTClient:
    """Return a Polygon RESTClient, creating it if necessary."""
    global polygon_client
    if polygon_client is None:
        key = os.getenv("POLYGON_API_KEY")
        if not key:
            raise RuntimeError("Polygon API key not configured")
        polygon_client = RESTClient(key)
    return polygon_client


@dataclass
class Quote:
    """Latest session close for a symbol plus its change against the prior session.

    ``prev_close``/``change``/``change_pct`` are None when the prior session
    could not be fetched — the price is still usable, so callers must render
    the change as unavailable rather than as zero.

    These are closing prices, never live ticks: ``session_date`` names the
    New York trading session the price closed ('YYYY-MM-DD'),
    ``price_timestamp`` is the provider's own timestamp for that bar when it
    sends one, and ``fetched_at`` is when the value came back from the
    provider. A cached quote keeps its original ``fetched_at``, so the UI can
    show how old the data really is rather than when the page last redrew.
    """

    symbol: str
    price: float
    prev_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    session_date: str | None = None
    price_timestamp: str | None = None
    fetched_at: str | None = None


@dataclass
class QuoteBatch:
    """Quotes for a batch plus the symbols the provider failed to answer for.

    ``errors`` holds symbols that are missing because a provider call failed
    (network, rate limit, plan), as opposed to symbols the provider simply has
    no data for. The UI uses the difference to keep the last good view and
    offer a retry instead of blanking prices that are merely unreachable.
    """

    quotes: dict[str, Quote] = field(default_factory=dict)
    errors: set[str] = field(default_factory=set)

    @property
    def failed(self) -> bool:
        return bool(self.errors)


# Key for whole-market entries in StockCache (not a real ticker)
MARKET_CACHE_KEY = "__market__"
# Latest completed session plus earlier weekdays to try when a session has no
# data yet: an exchange holiday, or a close the provider hasn't published.
SESSION_LOOKBACK = 3
# Weekdays to step back when the session before the latest one is a holiday
PRIOR_SESSION_LOOKBACK = 2


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    """Upper-case, strip, and de-duplicate while preserving caller order."""
    normalized: list[str] = []
    for raw in symbols:
        if not isinstance(raw, str):
            continue
        symbol = raw.strip().upper()
        if symbol and symbol not in normalized:
            normalized.append(symbol)
    return normalized


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _timestamp_iso(value: Any) -> str | None:
    """Provider epoch milliseconds -> ISO 8601 in New York time, or None."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=EASTERN_TZ).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _is_not_found(error: Exception) -> bool:
    """True when the provider answered that it has no data (HTTP 404 body).

    Polygon raises BadResponse carrying the JSON body; NOT_FOUND means "no bar
    for that symbol/date" (unknown ticker, holiday), which is an answer rather
    than a failure. Everything else — rate limits, auth, network — is a failure.
    """
    return "NOT_FOUND" in str(error)


def _previous_trading_day(date_str: str) -> str:
    """The weekday before date_str. Holidays are not modelled here; callers
    that get no data for a date step back again (see _recent_sessions)."""
    day = datetime.strptime(date_str, "%Y-%m-%d").date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.strftime("%Y-%m-%d")


def _recent_sessions(count: int = SESSION_LOOKBACK) -> list[str]:
    """Most recent completed session first, then the weekdays before it."""
    sessions = [get_most_recent_trading_day()]
    while len(sessions) < count:
        sessions.append(_previous_trading_day(sessions[-1]))
    return sessions


def _grouped_session(date_str: str) -> dict[str, Any] | None:
    """Whole-market closes for one session from a single grouped-daily call.

    Returns ``{"closes": {ticker: close}, "timestamp": ms | None,
    "fetched_at": iso}``, or None when the provider call fails (the grouped
    endpoint is not on every API plan; callers fall back to per-symbol
    fetches). A session with no closes means the provider has no data for that
    date: an exchange holiday, or a close it hasn't published yet.

    Non-empty sessions are cached as one entry per date — not one entry per
    ticker, which would evict the rest of the bounded in-process cache — so a
    watchlist, chart, and portfolio priced a minute apart share one call.
    Empty sessions are not cached, so a close published a few minutes after
    4:00 PM ET is picked up on the next request.
    """
    stock_cache = StockCache(cache)
    cached = stock_cache.get_cached_data(MARKET_CACHE_KEY, "grouped", date=date_str)
    if isinstance(cached, dict):
        return cached

    try:
        client = _get_client()
        aggs = client.get_grouped_daily_aggs(date_str, adjusted=True)
    except Exception as e:
        logger.warning(f"Grouped daily aggregates unavailable for {date_str}: {str(e)}")
        return None

    closes: dict[str, float] = {}
    timestamp = None
    for agg in aggs or []:
        ticker = getattr(agg, "ticker", None)
        close = getattr(agg, "close", None)
        if isinstance(ticker, str) and isinstance(close, (int, float)):
            closes[ticker] = float(close)
            if timestamp is None:
                raw_ts = getattr(agg, "timestamp", None)
                if isinstance(raw_ts, (int, float)) and not isinstance(raw_ts, bool):
                    timestamp = raw_ts

    session = {"closes": closes, "timestamp": timestamp, "fetched_at": _utc_now_iso()}
    if closes:
        stock_cache.set_cached_data(MARKET_CACHE_KEY, "grouped", session, date=date_str)
    return session


def _fetch_grouped_quotes(symbols: list[str]) -> tuple[dict[str, Quote], bool, str | None]:
    """Quotes for as many of `symbols` as the grouped endpoint knows about.

    Returns (quotes, reachable, session_date). reachable is False when a
    grouped call for the latest session failed, which sends every symbol to the
    per-symbol path; session_date is the session the quotes close, if any.
    Normally two calls in total — latest session and prior session — however
    many symbols are requested, and none while those sessions are cached.
    Sessions with no data are stepped over, so a holiday never turns into a
    zero day change: if no prior session can be found the change stays None.
    """
    latest = latest_date = None
    for date_str in _recent_sessions():
        session = _grouped_session(date_str)
        if session is None:
            return {}, False, None
        if session["closes"]:
            latest, latest_date = session, date_str
            break
    if latest is None:
        return {}, True, None

    previous = None
    prior_date = latest_date
    for _ in range(PRIOR_SESSION_LOOKBACK):
        prior_date = _previous_trading_day(prior_date)
        session = _grouped_session(prior_date)
        if session is None:
            break
        if session["closes"]:
            previous = session
            break
    previous_closes = previous["closes"] if previous else {}

    quotes: dict[str, Quote] = {}
    for symbol in symbols:
        price = latest["closes"].get(symbol)
        if price is None:
            continue
        prev_close = previous_closes.get(symbol)
        change = change_pct = None
        if prev_close:
            change = price - prev_close
            change_pct = change / prev_close * 100
        quotes[symbol] = Quote(
            symbol=symbol,
            price=price,
            prev_close=prev_close,
            change=change,
            change_pct=change_pct,
            session_date=latest_date,
            price_timestamp=_timestamp_iso(latest.get("timestamp")),
            fetched_at=latest.get("fetched_at"),
        )
    return quotes, True, latest_date


def _fetch_single_quote(symbol: str, sessions: list[str]) -> tuple[Quote | None, bool]:
    """One-symbol fallback: (quote, ok). ok is False when a call failed.

    Price only: the day change would cost a second call per symbol, which is
    exactly what the batched path exists to avoid. Steps back over sessions the
    provider has no bar for (holiday, unpublished close), one call each.
    """
    for date_str in sessions:
        try:
            client = _get_client()
            resp = client.get_daily_open_close_agg(symbol, date_str)
        except Exception as e:
            if _is_not_found(e):
                continue
            logger.error(f"Error fetching stock price for {symbol}: {str(e)}")
            return None, False
        price = getattr(resp, "close", None) if resp else None
        if not isinstance(price, (int, float)):
            continue
        session_date = getattr(resp, "from_", None)
        return (
            Quote(
                symbol=symbol,
                price=float(price),
                session_date=session_date if isinstance(session_date, str) else date_str,
                fetched_at=_utc_now_iso(),
            ),
            True,
        )
    return None, True


def _cached_quote(stock_cache: StockCache, symbol: str) -> Quote | None:
    cached = stock_cache.get_cached_data(symbol, "quote")
    if not isinstance(cached, dict):
        return None
    try:
        return Quote(**cached)
    except TypeError:
        # Written by an incompatible release; treat as a miss and refetch
        return None


def get_quote_batch(symbols: Iterable[str]) -> QuoteBatch:
    """Price and day change for many symbols in one batch (cached 5 minutes).

    Symbols the provider has no data for are omitted from ``quotes``; symbols
    lost to a provider failure are also listed in ``errors``.
    """
    wanted = _normalize_symbols(symbols)
    batch = QuoteBatch()
    if not wanted:
        return batch

    stock_cache = StockCache(cache)
    missing: list[str] = []
    for symbol in wanted:
        quote = _cached_quote(stock_cache, symbol)
        if quote is None:
            missing.append(symbol)
        else:
            batch.quotes[symbol] = quote

    if not missing:
        return batch

    # Only cache what was asked for per symbol; the whole-market response is
    # cached once per session inside _grouped_session.
    grouped, reachable, session_date = _fetch_grouped_quotes(missing)
    still_missing = []
    for symbol in missing:
        quote = grouped.get(symbol)
        if quote is None:
            still_missing.append(symbol)
            continue
        batch.quotes[symbol] = quote
        stock_cache.set_cached_data(symbol, "quote", asdict(quote))

    if still_missing:
        # A symbol absent from a successful grouped response gets one call for
        # that session (OTC tickers are not in grouped results); when grouped
        # failed, step back over sessions the provider has no bar for.
        if session_date:
            sessions = [session_date]
        elif reachable:
            # Grouped works but has nothing recent; one call each is plenty
            sessions = _recent_sessions(1)
        else:
            sessions = _recent_sessions()
        for symbol in still_missing:
            quote, ok = _fetch_single_quote(symbol, sessions)
            if not ok:
                batch.errors.add(symbol)
            if quote is not None:
                batch.quotes[symbol] = quote
                stock_cache.set_cached_data(symbol, "quote", asdict(quote))

    return batch


def get_quotes(symbols: Iterable[str]) -> dict[str, Quote]:
    """Price and day change for many symbols in one batch (cached 5 minutes).

    Symbols the provider has no data for are omitted from the result, so
    callers should use .get(symbol) rather than assuming every input is keyed.
    """
    return get_quote_batch(symbols).quotes


def get_stock_price(symbol: str) -> float | None:
    """Get the latest session close (cached for 5 minutes).

    Thin wrapper over get_quotes; prefer get_quotes directly when pricing more
    than one symbol so the fetch stays a single batched call.
    """
    quote = get_quotes([symbol]).get(symbol.strip().upper() if isinstance(symbol, str) else symbol)
    return quote.price if quote else None


def get_stock_data(symbol: str, from_date: str, to_date: str) -> list[dict[str, Any]]:
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
            historical_data.append(
                {
                    # Daily bars are stamped at midnight New York time; read
                    # them in that zone, not the server's, or a US/Pacific
                    # host would shift every bar back a day.
                    "date": datetime.fromtimestamp(agg.timestamp / 1000, tz=EASTERN_TZ).strftime(
                        "%Y-%m-%d"
                    ),
                    "open": agg.open,
                    "high": agg.high,
                    "low": agg.low,
                    "close": agg.close,
                    "volume": agg.volume,
                }
            )

        if historical_data:
            stock_cache.set_cached_data(
                symbol,
                "historical",
                historical_data,
                start_date=from_date,
                end_date=to_date,
            )
        return historical_data
    except Exception as e:
        logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
        return []


def get_intraday_stock_data(
    symbol: str,
    max_lookback_days: int = 7,
    aggregate_configs=None,
) -> list[dict[str, Any]]:
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
            date_str = candidate_date.strftime("%Y-%m-%d")
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
                        intraday_data.append(
                            {
                                "datetime": bar_dt.isoformat(),
                                "date": bar_dt.strftime("%Y-%m-%d"),
                                "time": bar_dt.strftime("%H:%M"),
                                "open": agg.open,
                                "high": agg.high,
                                "low": agg.low,
                                "close": agg.close,
                                "volume": agg.volume,
                                "resolution": "intraday",
                                "interval": f"{multiplier}-{timespan}",
                            }
                        )

                if intraday_data:
                    stock_cache.set_cached_data(symbol, "intraday", intraday_data)
                    return intraday_data

            candidate_date -= timedelta(days=1)

        return []
    except Exception as e:
        logger.error(f"Error fetching intraday data for {symbol}: {str(e)}")
        return []


def _as_text(value: Any, default: str = "N/A") -> str:
    return value if isinstance(value, str) else default


def _as_number(value: Any) -> float | None:
    return value if isinstance(value, (int, float)) else None


def get_company_details(symbol: str) -> dict[str, Any] | None:
    """Get company details from Polygon API (cached for 24 hours)."""
    stock_cache = StockCache(cache)
    # Use a versioned key so cached 150-character descriptions from earlier
    # releases do not keep the expandable About section from showing all text.
    cached_details = stock_cache.get_cached_data(symbol, "details", version=DETAILS_CACHE_VERSION)
    if cached_details is not None:
        return cached_details

    try:
        client = _get_client()
        ticker_details = client.get_ticker_details(symbol)
        if not ticker_details:
            return None

        icon_url = None
        logo_url = None

        if hasattr(ticker_details, "branding"):
            branding = ticker_details.branding
            if isinstance(branding, dict):
                icon_url = branding.get("icon_url")
                logo_url = branding.get("logo_url")
            elif branding is not None:
                icon_url = getattr(branding, "icon_url", None)
                logo_url = getattr(branding, "logo_url", None)
                if icon_url is not None and not isinstance(icon_url, str):
                    icon_url = None
                if logo_url is not None and not isinstance(logo_url, str):
                    logo_url = None

        if not icon_url and hasattr(ticker_details, "results"):
            results = ticker_details.results
            if hasattr(results, "branding"):
                branding = results.branding
                if isinstance(branding, dict):
                    icon_url = branding.get("icon_url")
                    logo_url = branding.get("logo_url")
                elif branding is not None:
                    icon_url = getattr(branding, "icon_url", None)
                    logo_url = getattr(branding, "logo_url", None)
                    if icon_url is not None and not isinstance(icon_url, str):
                        icon_url = None
                    if logo_url is not None and not isinstance(logo_url, str):
                        logo_url = None

        # icon_url/logo_url are stored WITHOUT the API key; the /branding/
        # proxy route fetches them server-side so the key never reaches the
        # client.
        name = symbol
        if hasattr(ticker_details, "name"):
            name = ticker_details.name
        elif hasattr(ticker_details, "results") and hasattr(ticker_details.results, "name"):
            name = ticker_details.results.name

        market_cap = getattr(ticker_details, "market_cap", None)
        if market_cap is None and hasattr(ticker_details, "results"):
            market_cap = getattr(ticker_details.results, "market_cap", None)

        website = getattr(ticker_details, "homepage_url", None)
        if website is None and hasattr(ticker_details, "results"):
            website = getattr(ticker_details.results, "homepage_url", None)

        list_date = getattr(ticker_details, "list_date", None)
        if list_date is None and hasattr(ticker_details, "results"):
            list_date = getattr(ticker_details.results, "list_date", None)

        exchange = getattr(ticker_details, "primary_exchange", None)
        if exchange is None and hasattr(ticker_details, "results"):
            exchange = getattr(ticker_details.results, "primary_exchange", None)

        description = ""
        raw_description = getattr(ticker_details, "description", None)
        if not isinstance(raw_description, str) and hasattr(ticker_details, "results"):
            raw_description = getattr(ticker_details.results, "description", None)
        if isinstance(raw_description, str):
            description = raw_description.strip()

        name = _as_text(name, symbol)
        market_cap = _as_number(market_cap)
        website = _as_text(website, "") or None
        list_date = _as_text(list_date, "") or None
        exchange = _as_text(exchange, "") or None

        details = {
            "name": name,
            "description": description,
            "market_cap": market_cap,
            "icon_url": icon_url,
            "logo_url": logo_url,
            "website": website,
            "list_date": list_date,
            "exchange": exchange,
            "primary_exchange": exchange,
            "sector": _as_text(getattr(ticker_details, "sector", "N/A")),
            "industry": _as_text(getattr(ticker_details, "industry", "N/A")),
        }
        stock_cache.set_cached_data(symbol, "details", details, version=DETAILS_CACHE_VERSION)
        return details
    except Exception as e:
        logger.error(f"Error fetching company details for {symbol}: {str(e)}")
        return None


def get_most_recent_trading_day(now: datetime | None = None) -> str:
    """The latest weekday whose regular session has closed, in New York time.

    The market closes at 4:00 PM America/New_York, whatever the server's own
    timezone (Render runs in UTC). Before the close a weekday's session is still
    in progress, so the answer is the previous weekday — Monday morning gives
    Friday. From the close onward it is that same day. Weekends roll back to
    Friday. Exchange holidays aren't modelled: the provider has no data for
    them, and callers step back a session (see _recent_sessions) rather than
    report a price or change for a day that never traded.

    ``now`` is for tests; a naive value is taken as New York time.
    """
    if now is None:
        now = datetime.now(EASTERN_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=EASTERN_TZ)
    else:
        now = now.astimezone(EASTERN_TZ)

    day = now.date()
    if now.time() < MARKET_CLOSE_ET:
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.strftime("%Y-%m-%d")


def get_stock_by_symbol(symbol: str) -> Stock | None:
    """Get a stock by its symbol from the database."""
    return Stock.query.filter_by(symbol=symbol).first()


def create_stock(symbol: str, name: str) -> Stock | None:
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
