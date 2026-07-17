from decimal import Decimal
from unittest.mock import patch

from app.cli import DEMO_EMAIL, DEMO_PASSWORD, DEMO_TRANSACTIONS, DEMO_WATCHLIST
from app.models import Stock, Transaction, User, Watchlist


def seed(runner):
    """Run seed-demo-user without hitting the live market-data API."""
    with patch("app.services.portfolio_services.get_company_details", return_value=None):
        return runner.invoke(args=["seed-demo-user"])


def test_seed_demo_user_creates_account(runner):
    result = seed(runner)
    assert result.exit_code == 0
    assert "Demo user created" in result.output

    user = User.query.filter_by(email=DEMO_EMAIL).first()
    assert user is not None
    assert user.check_password(DEMO_PASSWORD)

    watchlist = Watchlist.query.filter_by(user_id=user.id, name=DEMO_WATCHLIST).first()
    assert watchlist is not None
    assert {stock.symbol for stock in watchlist.stocks} == {"AAPL", "MSFT", "GOOGL"}


def test_seed_demo_user_seeds_portfolio_transactions(runner):
    result = seed(runner)
    assert result.exit_code == 0
    assert f"Seeded {len(DEMO_TRANSACTIONS)} demo portfolio transactions" in result.output

    user = User.query.filter_by(email=DEMO_EMAIL).first()
    txns = Transaction.query.filter_by(user_id=user.id).all()
    assert len(txns) == len(DEMO_TRANSACTIONS)
    # Spot-check one row survived the Decimal round trip exactly
    aapl_buys = [
        t for t in txns if t.stock.symbol == "AAPL" and t.side == "BUY" and t.quantity == 10
    ]
    assert len(aapl_buys) == 1
    assert Decimal(aapl_buys[0].price) == Decimal("150.00")


def test_seed_demo_user_is_idempotent(runner):
    seed(runner)
    result = seed(runner)

    assert result.exit_code == 0
    assert "Demo user already exists" in result.output
    assert "Seeded" not in result.output
    assert User.query.filter_by(email=DEMO_EMAIL).count() == 1
    # 3 watchlist stocks + NVDA created by the transaction seed
    assert Stock.query.count() == 4

    user = User.query.filter_by(email=DEMO_EMAIL).first()
    assert Transaction.query.filter_by(user_id=user.id).count() == len(DEMO_TRANSACTIONS)
