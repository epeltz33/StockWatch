"""A stand-in for the Polygon REST client, built on the demo's sample bars.

Implements the four client methods stock_services calls, re-dating the
sample history so its newest bar is the latest completed session. Every call
is counted, and ``fail`` makes every call raise, so tests can check both how
many provider requests an interaction costs and what the UI does when the
provider is down.
"""

from collections import Counter
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services import sample_data
from app.services.stock_services import get_most_recent_trading_day

ET = ZoneInfo("America/New_York")

# A ticker with a very long name, for layout checks
LONG_NAME_SYMBOL = "LONGCO"
LONG_NAME = "Consolidated Transcontinental Semiconductor & Infrastructure Holdings Corporation"


class ProviderDown(Exception):
    pass


def _weekdays_ending(last: date, count: int) -> list[date]:
    days = []
    day = last
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return list(reversed(days))


def _midnight_ms(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=ET).timestamp() * 1000)


class FakePolygonClient:
    def __init__(self, session: str | None = None):
        self.session = date.fromisoformat(session or get_most_recent_trading_day())
        self.calls: Counter = Counter()
        self.fail = False
        self._history = {}
        for symbol in (*sample_data.SYMBOLS, LONG_NAME_SYMBOL):
            source = sample_data.HISTORY["AAPL" if symbol == LONG_NAME_SYMBOL else symbol]
            dates = _weekdays_ending(self.session, len(source))
            self._history[symbol] = [
                {**bar, "date": day.isoformat()} for bar, day in zip(source, dates, strict=True)
            ]

    def _record(self, name):
        self.calls[name] += 1
        if self.fail:
            raise ProviderDown(f"provider unavailable ({name})")

    @property
    def total_calls(self) -> int:
        return sum(self.calls.values())

    def _bar(self, symbol, day_str):
        return next((b for b in self._history.get(symbol, []) if b["date"] == day_str), None)

    # --- the client surface stock_services uses ----------------------------

    def get_grouped_daily_aggs(self, date_str, adjusted=True):
        self._record("grouped")
        results = []
        for symbol in self._history:
            bar = self._bar(symbol, date_str)
            if bar:
                results.append(
                    SimpleNamespace(
                        ticker=symbol,
                        close=bar["close"],
                        timestamp=_midnight_ms(date.fromisoformat(date_str)) + 16 * 3600 * 1000,
                    )
                )
        return results

    def get_daily_open_close_agg(self, symbol, date_str):
        self._record("open_close")
        bar = self._bar(symbol, date_str)
        if bar is None:
            raise ProviderDown('{"status":"NOT_FOUND","message":"Data not found."}')
        return SimpleNamespace(close=bar["close"], from_=date_str)

    def get_aggs(self, ticker, multiplier, timespan, from_, to, **_kwargs):
        self._record(f"aggs_{timespan}")
        bars = self._history.get(ticker, [])
        if timespan == "day":
            return [
                SimpleNamespace(timestamp=_midnight_ms(date.fromisoformat(b["date"])), **_ohlcv(b))
                for b in bars
                if from_ <= b["date"] <= to
            ]
        # Intraday: the sample session's bars, moved onto the requested day
        if from_ != self.session.isoformat() or ticker not in self._history:
            return []
        source = sample_data.INTRADAY["AAPL" if ticker == LONG_NAME_SYMBOL else ticker]
        out = []
        for b in source:
            stamp = datetime.fromisoformat(b["datetime"])
            moved = datetime.combine(self.session, stamp.timetz())
            out.append(SimpleNamespace(timestamp=int(moved.timestamp() * 1000), **_ohlcv(b)))
        return out

    def get_ticker_details(self, symbol):
        self._record("details")
        if symbol == LONG_NAME_SYMBOL:
            return SimpleNamespace(
                name=LONG_NAME,
                description="A fictional company with an unusually long name.",
                market_cap=12_345_678_901,
                primary_exchange="XNYS",
                homepage_url=None,
                list_date="2001-02-03",
                branding=None,
            )
        details = sample_data.details(symbol)
        if details is None:
            raise ProviderDown('{"status":"NOT_FOUND"}')
        return SimpleNamespace(
            name=details["name"],
            description=details["description"],
            market_cap=details["market_cap"],
            primary_exchange=details["exchange"],
            homepage_url=details["website"],
            list_date=details["list_date"],
            branding=None,
        )


def _ohlcv(bar):
    return {k: bar[k] for k in ("open", "high", "low", "close", "volume")}
