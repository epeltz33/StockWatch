"""The demo's fixed synthetic data is deterministic and internally consistent:
every number the demo shows derives from the same bars."""

from datetime import date
from decimal import Decimal

import pytest

from app.services import sample_data
from app.services.portfolio_services import summarize_transactions
from frontend.data_sources import SampleSource


def test_generation_is_deterministic():
    again_history, again_intraday = sample_data._generate()
    assert again_history == sample_data.HISTORY
    assert again_intraday == sample_data.INTRADAY


@pytest.mark.parametrize("symbol", sample_data.SYMBOLS)
def test_daily_bars_are_weekday_sessions_ending_at_the_as_of_close(symbol):
    bars = sample_data.HISTORY[symbol]
    days = [date.fromisoformat(b["date"]) for b in bars]

    assert days == sorted(set(days))
    assert all(day.weekday() < 5 for day in days)
    assert days[0] == sample_data.HISTORY_START and days[-1] == sample_data.AS_OF
    for bar in bars:
        assert bar["low"] <= min(bar["open"], bar["close"])
        assert bar["high"] >= max(bar["open"], bar["close"])
        assert bar["volume"] > 0


@pytest.mark.parametrize("symbol", sample_data.SYMBOLS)
def test_intraday_session_matches_the_daily_bar(symbol):
    session = sample_data.HISTORY[symbol][-1]
    bars = sample_data.INTRADAY[symbol]

    assert bars[0]["time"] == "09:30"
    assert bars[0]["open"] == session["open"]
    assert bars[-1]["close"] == session["close"]
    assert sum(b["volume"] for b in bars) == session["volume"]
    assert min(b["low"] for b in bars) >= session["low"]
    assert max(b["high"] for b in bars) <= session["high"]


@pytest.mark.parametrize("symbol", sample_data.SYMBOLS)
def test_quotes_and_market_caps_come_from_the_bars(symbol):
    bars = sample_data.HISTORY[symbol]
    quote = sample_data.QUOTES[symbol]
    company = next(c for c in sample_data.COMPANIES if c.symbol == symbol)

    assert quote.price == bars[-1]["close"]
    assert quote.prev_close == bars[-2]["close"]
    assert quote.change == pytest.approx(quote.price - quote.prev_close)
    assert quote.session_date == sample_data.AS_OF.isoformat()
    assert quote.fetched_at is None  # never fetched: the UI says "sample"
    assert sample_data.details(symbol)["market_cap"] == round(
        quote.price * company.shares_outstanding
    )


def test_sample_trades_fill_at_the_chart_close_on_their_dates():
    for txn in sample_data.TRANSACTIONS:
        close = sample_data.close_on(txn.stock.symbol, txn.executed_at)
        assert txn.price == Decimal(f"{close:.2f}")


def test_sample_portfolio_uses_the_real_accounting_and_is_fully_priced():
    summary = SampleSource().portfolio_summary()
    direct = summarize_transactions(sample_data.TRANSACTIONS, quote_fn=sample_data.quotes)

    assert summary["market_value"] == direct["market_value"]
    assert (summary["priced_count"], summary["unpriced_count"]) == (3, 0)
    assert summary["price_dates"] == [sample_data.AS_OF.isoformat()]
    by_symbol = {p.symbol: p for p in summary["positions"]}
    # AAPL: two buys and a partial sell under average cost
    aapl = by_symbol["AAPL"]
    buys = [t for t in sample_data.TRANSACTIONS if t.stock.symbol == "AAPL" and t.side == "BUY"]
    expected_avg = sum(t.quantity * t.price for t in buys) / sum(t.quantity for t in buys)
    assert aapl.quantity == Decimal("10")
    assert aapl.avg_cost == expected_avg
    assert aapl.current_price == Decimal(str(sample_data.QUOTES["AAPL"].price))


def test_unknown_symbols_have_no_sample_data():
    assert sample_data.history("TSLA") == []
    assert sample_data.details("TSLA") is None
    assert sample_data.quotes(["TSLA", "aapl"]).keys() == {"AAPL"}
