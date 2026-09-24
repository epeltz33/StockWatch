from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from app.extensions import db
from app.models import Transaction, User
from app.services.portfolio_services import (
    InsufficientSharesError,
    PortfolioError,
    delete_transaction,
    get_portfolio_summary,
    get_positions,
    list_transactions,
    record_transaction,
)
from app.services.stock_services import Quote


@pytest.fixture
def user(app):
    u = User(username="trader", email="trader@example.com")
    u.set_password("password123")
    db.session.add(u)
    db.session.commit()
    return u


def quotes_for(prices):
    """Build a get_quotes return value; symbols with no price are omitted,
    exactly as the real batched fetch omits symbols it has no data for."""
    return {
        symbol: Quote(symbol=symbol, price=price)
        for symbol, price in prices.items()
        if price is not None
    }


@pytest.fixture(autouse=True)
def no_live_prices():
    """Portfolio tests never hit the market-data API unless they patch it."""
    with patch("app.services.portfolio_services.get_quotes", return_value={}):
        with patch("app.services.portfolio_services.get_company_details", return_value=None):
            yield


def buy(user, symbol, qty, price, when):
    return record_transaction(user.id, symbol, "BUY", qty, price, when)


def sell(user, symbol, qty, price, when):
    return record_transaction(user.id, symbol, "SELL", qty, price, when)


def test_single_buy_creates_position(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))

    positions = get_positions(user.id)
    assert len(positions) == 1
    p = positions[0]
    assert p.symbol == "AAPL"
    assert p.quantity == Decimal("10")
    assert p.avg_cost == Decimal("150.00")
    assert p.cost_basis == Decimal("1500.00")
    assert p.realized_pl == Decimal("0")
    assert p.current_price is None
    assert p.market_value is None


def test_two_buys_weighted_average_cost(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    buy(user, "AAPL", "5", "180.00", date(2024, 2, 5))

    p = get_positions(user.id)[0]
    # (10*150 + 5*180) / 15 = 2400 / 15 = 160 exactly
    assert p.quantity == Decimal("15")
    assert p.avg_cost == Decimal("160")
    assert p.cost_basis == Decimal("2400")


def test_partial_sell_realizes_pl_and_keeps_avg_cost(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    buy(user, "AAPL", "5", "180.00", date(2024, 2, 5))
    sell(user, "AAPL", "5", "200.00", date(2024, 3, 5))

    p = get_positions(user.id)[0]
    assert p.quantity == Decimal("10")
    # Average cost is unchanged by sells
    assert p.avg_cost == Decimal("160")
    # Realized: (200 - 160) * 5 = 200
    assert p.realized_pl == Decimal("200")


def test_sell_to_zero_removes_position_but_keeps_realized_pl(user):
    buy(user, "NVDA", "30", "45.50", date(2024, 3, 1))
    sell(user, "NVDA", "30", "120.00", date(2025, 5, 15))

    assert get_positions(user.id) == []
    summary = get_portfolio_summary(user.id)
    # (120.00 - 45.50) * 30 = 74.50 * 30 = 2235.00
    assert summary["realized_pl"] == Decimal("2235.00")


def test_oversell_raises(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    with pytest.raises(InsufficientSharesError):
        sell(user, "AAPL", "11", "200.00", date(2024, 2, 5))
    # Ledger unchanged
    assert Transaction.query.filter_by(user_id=user.id).count() == 1


def test_sell_with_no_position_raises(user):
    with pytest.raises(InsufficientSharesError):
        sell(user, "AAPL", "1", "200.00", date(2024, 2, 5))


def test_backdated_sell_that_breaks_later_sell_raises(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    sell(user, "AAPL", "10", "200.00", date(2024, 6, 1))
    # Inserting a sell before June would make the June sell an oversell
    with pytest.raises(InsufficientSharesError):
        sell(user, "AAPL", "5", "180.00", date(2024, 3, 1))


def test_unrealized_pl_with_live_price(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))

    with patch(
        "app.services.portfolio_services.get_quotes",
        return_value=quotes_for({"AAPL": 175.50}),
    ):
        p = get_positions(user.id)[0]

    assert p.current_price == Decimal("175.50")
    assert p.market_value == Decimal("1755.00")
    assert p.unrealized_pl == Decimal("255.00")
    # 255 / 1500 * 100 = 17%
    assert p.unrealized_pl_pct == Decimal("17")


def test_missing_price_degrades_gracefully(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    buy(user, "MSFT", "8", "310.00", date(2024, 2, 5))

    # MSFT has no quote available from the provider
    with patch(
        "app.services.portfolio_services.get_quotes",
        return_value=quotes_for({"AAPL": 200.00}),
    ):
        summary = get_portfolio_summary(user.id)

    # MSFT is excluded from market value/unrealized but kept in cost basis
    assert summary["market_value"] == Decimal("2000.00")
    assert summary["cost_basis"] == Decimal("3980.00")
    assert summary["unrealized_pl"] == Decimal("500.00")
    assert len(summary["allocations"]) == 1
    assert summary["allocations"][0]["symbol"] == "AAPL"


def test_allocation_weights_sum_to_one(user):
    buy(user, "AAPL", "10", "100.00", date(2024, 1, 5))
    buy(user, "MSFT", "10", "300.00", date(2024, 1, 5))

    with patch(
        "app.services.portfolio_services.get_quotes",
        return_value=quotes_for({"AAPL": 100.00, "MSFT": 100.00}),
    ):
        summary = get_portfolio_summary(user.id)

    weights = [a["weight"] for a in summary["allocations"]]
    assert sum(weights) == Decimal("1")
    assert all(w == Decimal("0.5") for w in weights)


def test_transactions_replay_in_date_order_not_insert_order(user):
    # Inserted out of order: the sell is recorded first by date but the buy
    # backing it is inserted afterwards with an earlier executed_at
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    sell(user, "AAPL", "5", "200.00", date(2024, 6, 1))
    buy(user, "AAPL", "5", "100.00", date(2024, 2, 1))  # backdated buy

    p = get_positions(user.id)[0]
    # Replay order: buy 10@150, buy 5@100 (avg (1500+500)/15 = 133.33...),
    # then sell 5 → qty 10
    assert p.quantity == Decimal("10")
    assert p.avg_cost == Decimal("2000") / Decimal("15")


def test_delete_transaction_rejects_removal_that_breaks_ledger(user):
    first_buy = buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    sell(user, "AAPL", "10", "200.00", date(2024, 6, 1))

    with pytest.raises(InsufficientSharesError):
        delete_transaction(user.id, first_buy.id)
    assert Transaction.query.filter_by(user_id=user.id).count() == 2


def test_delete_transaction_happy_path_and_ownership(user):
    txn = buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))

    other = User(username="other", email="other@example.com")
    other.set_password("password123")
    db.session.add(other)
    db.session.commit()

    # Wrong owner: nothing deleted
    assert delete_transaction(other.id, txn.id) is False
    assert Transaction.query.count() == 1

    assert delete_transaction(user.id, txn.id) is True
    assert Transaction.query.count() == 0


def test_validation_rejects_bad_inputs(user):
    with pytest.raises(PortfolioError):
        record_transaction(user.id, "AAPL", "HOLD", "1", "100", date(2024, 1, 5))
    with pytest.raises(PortfolioError):
        record_transaction(user.id, "AAPL", "BUY", "0", "100", date(2024, 1, 5))
    with pytest.raises(PortfolioError):
        record_transaction(user.id, "AAPL", "BUY", "1", "-5", date(2024, 1, 5))
    with pytest.raises(PortfolioError):
        record_transaction(user.id, "BAD SYMBOL!", "BUY", "1", "100", date(2024, 1, 5))
    with pytest.raises(PortfolioError):
        record_transaction(user.id, "AAPL", "BUY", "abc", "100", date(2024, 1, 5))


def test_list_transactions_most_recent_first(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    buy(user, "MSFT", "8", "310.00", date(2024, 2, 12))
    buy(user, "NVDA", "30", "45.50", date(2024, 3, 1))

    txns = list_transactions(user.id)
    assert [t.stock.symbol for t in txns] == ["NVDA", "MSFT", "AAPL"]

    limited = list_transactions(user.id, limit=2)
    assert len(limited) == 2


def test_get_positions_prices_every_holding_in_one_batch(user):
    """One batched quote call for the whole portfolio, not one call per symbol:
    the per-symbol path trips the provider's rate limit and silently drops
    positions out of market value and allocations."""
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    buy(user, "MSFT", "8", "310.00", date(2024, 1, 6))
    buy(user, "NVDA", "3", "900.00", date(2024, 1, 7))

    batched = Mock(return_value=quotes_for({"AAPL": 200.0, "MSFT": 320.0, "NVDA": 950.0}))
    with patch("app.services.portfolio_services.get_quotes", batched):
        positions = get_positions(user.id)

    assert batched.call_count == 1
    assert set(batched.call_args[0][0]) == {"AAPL", "MSFT", "NVDA"}
    assert [p.current_price for p in positions] == [
        Decimal("200.0"),
        Decimal("320.0"),
        Decimal("950.0"),
    ]


def test_get_portfolio_summary_prices_every_holding_in_one_batch(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    buy(user, "MSFT", "8", "310.00", date(2024, 1, 6))

    batched = Mock(return_value=quotes_for({"AAPL": 200.0, "MSFT": 320.0}))
    with patch("app.services.portfolio_services.get_quotes", batched):
        summary = get_portfolio_summary(user.id)

    assert batched.call_count == 1
    assert summary["market_value"] == Decimal("4560.0")


def test_get_positions_makes_no_quote_call_for_an_empty_portfolio(user):
    batched = Mock(return_value={})
    with patch("app.services.portfolio_services.get_quotes", batched):
        assert get_positions(user.id) == []

    batched.assert_not_called()


def test_summary_counts_priced_and_unpriced_holdings(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    buy(user, "MSFT", "8", "310.00", date(2024, 2, 5))
    buy(user, "NVDA", "3", "900.00", date(2024, 3, 5))

    with patch(
        "app.services.portfolio_services.get_quotes",
        return_value=quotes_for({"AAPL": 200.00, "NVDA": 950.00}),
    ):
        summary = get_portfolio_summary(user.id)

    assert summary["holding_count"] == 3
    assert summary["priced_count"] == 2
    assert summary["unpriced_count"] == 1
    assert summary["is_partial"] is True
    # Totals cover the priced holdings only, and say so via is_partial
    assert summary["market_value"] == Decimal("4850.00")
    assert summary["priced_cost_basis"] == Decimal("4200.00")
    assert summary["unrealized_pl"] == Decimal("650.00")


def test_fully_priced_summary_is_not_partial(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))

    with patch(
        "app.services.portfolio_services.get_quotes",
        return_value=quotes_for({"AAPL": 200.00}),
    ):
        summary = get_portfolio_summary(user.id)

    assert (summary["priced_count"], summary["unpriced_count"]) == (1, 0)
    assert summary["is_partial"] is False


def test_no_priced_holdings_reports_value_and_return_as_unavailable(user):
    """With every quote missing, $0.00 market value and a -100% return would
    read as a total loss. They are unavailable, not zero."""
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    buy(user, "MSFT", "8", "310.00", date(2024, 2, 5))
    sell(user, "AAPL", "5", "200.00", date(2024, 3, 5))

    summary = get_portfolio_summary(user.id)  # autouse fixture: no quotes

    assert summary["holding_count"] == 2
    assert summary["priced_count"] == 0
    assert summary["is_partial"] is False
    assert summary["market_value"] is None
    assert summary["unrealized_pl"] is None
    assert summary["unrealized_pl_pct"] is None
    assert summary["allocations"] == []
    # Figures that need no prices are still reported
    assert summary["cost_basis"] == Decimal("3230.00")
    assert summary["realized_pl"] == Decimal("250.00")


def test_empty_portfolio_is_worth_zero_not_unavailable(user):
    summary = get_portfolio_summary(user.id)

    assert summary["holding_count"] == 0
    assert summary["market_value"] == Decimal("0")
    assert summary["is_partial"] is False


def test_positions_record_the_session_of_their_price(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))

    quote = Quote(symbol="AAPL", price=200.0, session_date="2026-06-30")
    with patch("app.services.portfolio_services.get_quotes", return_value={"AAPL": quote}):
        summary = get_portfolio_summary(user.id)

    assert summary["positions"][0].price_date == "2026-06-30"
    assert summary["price_dates"] == ["2026-06-30"]
