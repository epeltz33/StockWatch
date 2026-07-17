from app.cli import DEMO_EMAIL, DEMO_PASSWORD, DEMO_WATCHLIST
from app.models import Stock, User, Watchlist


def test_seed_demo_user_creates_account(runner):
    result = runner.invoke(args=["seed-demo-user"])
    assert result.exit_code == 0
    assert "Demo user created" in result.output

    user = User.query.filter_by(email=DEMO_EMAIL).first()
    assert user is not None
    assert user.check_password(DEMO_PASSWORD)

    watchlist = Watchlist.query.filter_by(user_id=user.id, name=DEMO_WATCHLIST).first()
    assert watchlist is not None
    assert {stock.symbol for stock in watchlist.stocks} == {"AAPL", "MSFT", "GOOGL"}


def test_seed_demo_user_is_idempotent(runner):
    runner.invoke(args=["seed-demo-user"])
    result = runner.invoke(args=["seed-demo-user"])

    assert result.exit_code == 0
    assert "Demo user already exists" in result.output
    assert User.query.filter_by(email=DEMO_EMAIL).count() == 1
    assert Stock.query.count() == 3
