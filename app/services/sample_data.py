"""Fixed synthetic market data behind the public demo at /demo/.

Everything here is generated at import time from the constants below: no
market-data provider, no database, no clock. Each price path is a seeded
Brownian bridge between fixed start and end prices, so the same numbers come
out on every machine and every run — the demo, its tests, and the README
screenshots all agree. Every figure the demo shows (quotes, market caps,
portfolio cost basis and P/L) is derived from these same bars, so the chart,
watchlist, details, and portfolio can never disagree.

The tickers are real so the demo reads naturally; the prices are not. The UI
labels every demo view "Sample data · Not live prices".
"""

import math
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.services.stock_services import Quote

ET = ZoneInfo("America/New_York")

# The sample's latest completed session. Chart periods, quotes, and the
# portfolio valuation are all "as of" this close.
AS_OF = date(2026, 9, 18)
HISTORY_START = date(2020, 7, 1)
INTRADAY_BAR_MINUTES = 5
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)


@dataclass(frozen=True)
class SampleCompany:
    symbol: str
    name: str
    start_price: float
    end_price: float
    daily_vol: float
    avg_volume: int
    shares_outstanding: int
    list_date: str
    website: str
    description: str
    seed: int


COMPANIES = (
    SampleCompany(
        symbol="AAPL",
        name="Apple Inc.",
        start_price=91.03,
        end_price=231.48,
        daily_vol=0.017,
        avg_volume=58_000_000,
        shares_outstanding=14_840_000_000,
        list_date="1980-12-12",
        website="https://www.apple.com",
        description=(
            "Apple designs and sells smartphones, personal computers, tablets, "
            "wearables, and accessories, and runs a services business that "
            "includes its App Store, payments, cloud storage, and streaming."
        ),
        seed=80,
    ),
    SampleCompany(
        symbol="MSFT",
        name="Microsoft Corporation",
        start_price=204.70,
        end_price=441.96,
        daily_vol=0.015,
        avg_volume=24_000_000,
        shares_outstanding=7_433_000_000,
        list_date="1986-03-13",
        website="https://www.microsoft.com",
        description=(
            "Microsoft develops and licenses software, cloud services, and "
            "devices, including Windows, Microsoft 365, the Azure cloud "
            "platform, LinkedIn, and Xbox gaming."
        ),
        seed=68,
    ),
    SampleCompany(
        symbol="NVDA",
        name="NVIDIA Corporation",
        start_price=9.48,
        end_price=132.75,
        daily_vol=0.029,
        avg_volume=310_000_000,
        shares_outstanding=24_300_000_000,
        list_date="1999-01-22",
        website="https://www.nvidia.com",
        description=(
            "NVIDIA designs graphics processors and accelerated-computing "
            "platforms used in gaming, professional visualization, data "
            "centers, and automotive systems."
        ),
        seed=44,
    ),
)
SYMBOLS = tuple(company.symbol for company in COMPANIES)
_COMPANIES = {company.symbol: company for company in COMPANIES}

WATCHLIST_ID = 1
WATCHLIST_NAME = "Sample watchlist"

# (symbol, side, quantity, trade date). Fills are the sample close on the
# trade date, so the ledger lines up with the chart. Mirrors the seeded demo
# account: two AAPL buys at different prices plus a partial sell exercise the
# average-cost math, NVDA has a profitable partial sell, MSFT is a simple hold.
TRANSACTION_PLAN = (
    ("AAPL", "BUY", "10", date(2024, 1, 5)),
    ("MSFT", "BUY", "8", date(2024, 2, 12)),
    ("NVDA", "BUY", "30", date(2024, 3, 1)),
    ("AAPL", "BUY", "5", date(2024, 9, 3)),
    ("NVDA", "SELL", "10", date(2025, 5, 15)),
    ("AAPL", "SELL", "5", date(2025, 6, 20)),
)


class _Rng:
    """Seeded normal draws built only on random.random().

    Python guarantees random() reproduces the same sequence for the same seed
    across versions; gauss() and friends carry no such promise. Box-Muller on
    top of random() keeps the sample prices identical everywhere.
    """

    def __init__(self, seed: int):
        self._random = random.Random(seed)
        self._spare: float | None = None

    def normal(self) -> float:
        if self._spare is not None:
            value, self._spare = self._spare, None
            return value
        u1 = 1.0 - self._random.random()  # (0, 1]: log() stays finite
        u2 = self._random.random()
        radius = math.sqrt(-2.0 * math.log(u1))
        self._spare = radius * math.sin(2 * math.pi * u2)
        return radius * math.cos(2 * math.pi * u2)


def _weekdays(start: date, end: date) -> list[date]:
    days = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _bridge(rng: _Rng, steps: int, start: float, end: float, vol: float) -> list[float]:
    """steps + 1 prices on a log-space Brownian bridge from start to end."""
    walk = [0.0]
    for _ in range(steps):
        walk.append(walk[-1] + rng.normal() * vol)
    target = math.log(end / start)
    drift = walk[-1] - target
    return [start * math.exp(w - drift * i / steps) for i, w in enumerate(walk)]


def _cents(value: float) -> float:
    return round(value, 2)


def _daily_bars(company: SampleCompany, rng: _Rng, sessions: list[date]) -> list[dict]:
    closes = _bridge(
        rng, len(sessions) - 1, company.start_price, company.end_price, company.daily_vol
    )
    bars = []
    previous_close = closes[0]
    for day, close in zip(sessions, closes, strict=True):
        gap = rng.normal() * company.daily_vol * 0.3
        open_ = previous_close * math.exp(gap)
        high = max(open_, close) * (1 + abs(rng.normal()) * company.daily_vol * 0.45)
        low = min(open_, close) * (1 - abs(rng.normal()) * company.daily_vol * 0.45)
        move = abs(math.log(close / previous_close)) / company.daily_vol
        volume = company.avg_volume * math.exp(rng.normal() * 0.22) * (0.75 + 0.25 * move)
        bars.append(
            {
                "date": day.isoformat(),
                "open": _cents(open_),
                "high": _cents(high),
                "low": _cents(low),
                "close": _cents(close),
                "volume": int(volume),
            }
        )
        previous_close = close
    return bars


def _intraday_bars(company: SampleCompany, rng: _Rng, session: dict) -> list[dict]:
    """5-minute bars for one session, from its open to its close.

    The bars start at the daily bar's open, end at its close, and their volume
    sums to the daily volume; the daily high/low are then widened to cover
    the bars, so 1D and the daily chart describe the same session.
    """
    minutes = (
        datetime.combine(AS_OF, SESSION_CLOSE) - datetime.combine(AS_OF, SESSION_OPEN)
    ).seconds // 60
    count = minutes // INTRADAY_BAR_MINUTES
    step_vol = company.daily_vol / math.sqrt(count) * 0.8
    path = _bridge(rng, count, session["open"], session["close"], step_vol)

    # U-shaped volume profile: busy open and close, quiet midday
    weights = [1 + 1.6 * ((i - (count - 1) / 2) / ((count - 1) / 2)) ** 2 for i in range(count)]
    weights = [w * math.exp(rng.normal() * 0.15) for w in weights]
    scale = session["volume"] / sum(weights)
    volumes = [int(w * scale) for w in weights]
    volumes[-1] += session["volume"] - sum(volumes)

    bars = []
    start = datetime.combine(AS_OF, SESSION_OPEN, ET)
    for i in range(count):
        bar_open, bar_close = path[i], path[i + 1]
        wiggle = company.daily_vol * 0.12
        stamp = start + timedelta(minutes=INTRADAY_BAR_MINUTES * i)
        bars.append(
            {
                "datetime": stamp.isoformat(),
                "date": stamp.strftime("%Y-%m-%d"),
                "time": stamp.strftime("%H:%M"),
                "open": _cents(bar_open),
                "high": _cents(max(bar_open, bar_close) * (1 + abs(rng.normal()) * wiggle)),
                "low": _cents(min(bar_open, bar_close) * (1 - abs(rng.normal()) * wiggle)),
                "close": _cents(bar_close),
                "volume": volumes[i],
                "resolution": "intraday",
                "interval": f"{INTRADAY_BAR_MINUTES}-minute",
            }
        )
    bars[0]["open"] = session["open"]
    bars[-1]["close"] = session["close"]
    session["high"] = max(session["high"], max(bar["high"] for bar in bars))
    session["low"] = min(session["low"], min(bar["low"] for bar in bars))
    return bars


def _generate() -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    sessions = _weekdays(HISTORY_START, AS_OF)
    history: dict[str, list[dict]] = {}
    intraday: dict[str, list[dict]] = {}
    for company in COMPANIES:
        rng = _Rng(company.seed)
        bars = _daily_bars(company, rng, sessions)
        intraday[company.symbol] = _intraday_bars(company, rng, bars[-1])
        history[company.symbol] = bars
    return history, intraday


HISTORY, INTRADAY = _generate()


def history(symbol: str) -> list[dict]:
    """Daily OHLCV bars, oldest first; [] for symbols outside the sample."""
    return [dict(bar) for bar in HISTORY.get(symbol, [])]


def intraday(symbol: str) -> list[dict]:
    """5-minute bars for the AS_OF session; [] outside the sample."""
    return [dict(bar) for bar in INTRADAY.get(symbol, [])]


def close_on(symbol: str, day: date) -> float:
    for bar in HISTORY[symbol]:
        if bar["date"] == day.isoformat():
            return bar["close"]
    raise KeyError(f"No sample session for {symbol} on {day}")


def _quote(symbol: str) -> Quote:
    bars = HISTORY[symbol]
    price, prev_close = bars[-1]["close"], bars[-2]["close"]
    change = round(price - prev_close, 2)
    return Quote(
        symbol=symbol,
        price=price,
        prev_close=prev_close,
        change=change,
        change_pct=change / prev_close * 100,
        session_date=bars[-1]["date"],
        price_timestamp=datetime.combine(AS_OF, SESSION_CLOSE, ET).isoformat(),
        # Never fetched from anywhere: the UI says "sample" instead of a time
        fetched_at=None,
    )


QUOTES = {symbol: _quote(symbol) for symbol in SYMBOLS}


def quotes(symbols) -> dict[str, Quote]:
    """Same contract as stock_services.get_quotes, from the fixed sample."""
    wanted = {s.strip().upper() for s in symbols if isinstance(s, str)}
    return {symbol: QUOTES[symbol] for symbol in SYMBOLS if symbol in wanted}


def details(symbol: str) -> dict | None:
    """Company details shaped like stock_services.get_company_details."""
    company = _COMPANIES.get(symbol)
    if company is None:
        return None
    return {
        "name": company.name,
        "description": company.description,
        # Consistent with the sample price rather than any real valuation
        "market_cap": round(QUOTES[symbol].price * company.shares_outstanding),
        "icon_url": None,
        "logo_url": None,
        "website": company.website,
        "list_date": company.list_date,
        "exchange": "XNAS",
        "primary_exchange": "XNAS",
        "sector": "N/A",
        "industry": "N/A",
    }


@dataclass(frozen=True)
class SampleStock:
    id: int
    symbol: str
    name: str


@dataclass(frozen=True)
class SampleTransaction:
    """Shaped like models.Transaction for portfolio_services' replay."""

    id: int
    stock: SampleStock
    side: str
    quantity: Decimal
    price: Decimal
    executed_at: date


STOCKS = tuple(
    SampleStock(id=i, symbol=company.symbol, name=company.name)
    for i, company in enumerate(COMPANIES, start=1)
)
_STOCKS = {stock.symbol: stock for stock in STOCKS}

TRANSACTIONS = tuple(
    SampleTransaction(
        id=i,
        stock=_STOCKS[symbol],
        side=side,
        quantity=Decimal(quantity),
        price=Decimal(f"{close_on(symbol, day):.2f}"),
        executed_at=day,
    )
    for i, (symbol, side, quantity, day) in enumerate(TRANSACTION_PLAN, start=1)
)
