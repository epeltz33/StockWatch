from flask.cli import with_appcontext
import click
from app.models import User, Watchlist, Stock
from app.extensions import db

DEMO_EMAIL = "demo@stockwatch.dev"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "Demo123!"
DEMO_WATCHLIST = "Demo Portfolio"
DEMO_STOCKS = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
}


@click.command('delete-user')
@click.argument('email')
@with_appcontext
def delete_user(email):
    user = User.query.filter_by(email=email).first()
    if user:
        Watchlist.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        click.echo(f"User with email {email} and all associated data has been deleted")
    else:
        click.echo(f"No user found with email {email}")


@click.command('test-cache')
@click.argument('symbol')
@with_appcontext
def test_cache(symbol):
    """CLI command to test cache functionality."""
    from app.utils.cache_monitor import test_cache_functionality

    test_cache_functionality(symbol)
    click.echo(f"Cache test completed for {symbol}")


@click.command("seed-demo-user")
@with_appcontext
def seed_demo_user():
    """Create or repair the public demo account with a pre-populated watchlist.

    Idempotent: safe to run on every deploy. If the user already exists from a
    previous deploy (possibly without the seeded watchlist), this still ensures
    the Demo Portfolio watchlist and its stocks are present.
    """
    user = User.query.filter_by(email=DEMO_EMAIL).first()
    created_user = False
    if not user:
        user = User(username=DEMO_USERNAME, email=DEMO_EMAIL)
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        db.session.flush()
        created_user = True

    watchlist = Watchlist.query.filter_by(user_id=user.id, name=DEMO_WATCHLIST).first()
    created_watchlist = False
    if not watchlist:
        watchlist = Watchlist(name=DEMO_WATCHLIST, user_id=user.id)
        db.session.add(watchlist)
        db.session.flush()
        created_watchlist = True

    added_symbols = []
    for symbol, name in DEMO_STOCKS.items():
        stock = Stock.query.filter_by(symbol=symbol).first()
        if not stock:
            stock = Stock(symbol=symbol, name=name)
            db.session.add(stock)
            db.session.flush()
        if stock not in watchlist.stocks:
            watchlist.stocks.append(stock)
            added_symbols.append(symbol)

    db.session.commit()

    if created_user:
        click.echo(f"Demo user created: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    else:
        click.echo(f"Demo user already exists ({DEMO_EMAIL})")
    if created_watchlist:
        click.echo(f"Demo watchlist created: {DEMO_WATCHLIST}")
    if added_symbols:
        click.echo(f"Added stocks to demo watchlist: {', '.join(added_symbols)}")
