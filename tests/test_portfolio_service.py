from datetime import date
from decimal import Decimal
from unittest.mock import patch

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


@pytest.fixture
def user(app):
    u = User(username="trader", email="trader@example.com")
    u.set_password("password123")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture(autouse=True)
def no_live_prices():
    """Portfolio tests never hit the market-data API unless they patch it."""
    with patch("app.services.portfolio_services.get_stock_price", return_value=None):
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

    with patch("app.services.portfolio_services.get_stock_price", return_value=175.50):
        p = get_positions(user.id)[0]

    assert p.current_price == Decimal("175.50")
    assert p.market_value == Decimal("1755.00")
    assert p.unrealized_pl == Decimal("255.00")
    # 255 / 1500 * 100 = 17%
    assert p.unrealized_pl_pct == Decimal("17")


def test_missing_price_degrades_gracefully(user):
    buy(user, "AAPL", "10", "150.00", date(2024, 1, 5))
    buy(user, "MSFT", "8", "310.00", date(2024, 2, 5))

    def price_for(symbol):
        return 200.00 if symbol == "AAPL" else None

    with patch("app.services.portfolio_services.get_stock_price", side_effect=price_for):
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

    with patch("app.services.portfolio_services.get_stock_price", return_value=100.00):
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
