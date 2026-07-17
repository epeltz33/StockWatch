from datetime import date

import click
from flask.cli import with_appcontext

from app.extensions import db
from app.models import Stock, User, Watchlist

DEMO_EMAIL = "demo@stockwatch.dev"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "Demo123!"
DEMO_WATCHLIST = "Demo Portfolio"
DEMO_STOCKS = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
}

# (symbol, side, quantity, price, executed date). Chosen to demo non-trivial
# average-cost math: AAPL has two buys at different prices plus a partial
# sell; NVDA has a profitable partial sell; MSFT is a simple hold.
DEMO_TRANSACTIONS = [
    ("AAPL", "BUY", "10", "150.00", date(2024, 1, 5)),
    ("MSFT", "BUY", "8", "310.00", date(2024, 2, 12)),
    ("NVDA", "BUY", "30", "45.50", date(2024, 3, 1)),
    ("AAPL", "BUY", "5", "185.00", date(2024, 9, 3)),
    ("NVDA", "SELL", "10", "120.00", date(2025, 5, 15)),
    ("AAPL", "SELL", "5", "225.00", date(2025, 6, 20)),
]


@click.command("delete-user")
@click.argument("email")
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

    # Seed portfolio transactions only when the ledger is empty, so a demo
    # visitor's own experiments never get mixed with or duplicated by reseeds
    seeded_transactions = 0
    if user.transactions.count() == 0:
        from app.services.portfolio_services import record_transaction

        for symbol, side, quantity, price, executed_at in DEMO_TRANSACTIONS:
            record_transaction(user.id, symbol, side, quantity, price, executed_at)
            seeded_transactions += 1

    if created_user:
        click.echo(f"Demo user created: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    else:
        click.echo(f"Demo user already exists ({DEMO_EMAIL})")
    if created_watchlist:
        click.echo(f"Demo watchlist created: {DEMO_WATCHLIST}")
    if added_symbols:
        click.echo(f"Added stocks to demo watchlist: {', '.join(added_symbols)}")
    if seeded_transactions:
        click.echo(f"Seeded {seeded_transactions} demo portfolio transactions")
