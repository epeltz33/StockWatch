
from flask.cli import with_appcontext
import click
from app.models import User, Watchlist
from app.extensions import db
from app.utils.cache_monitor import test_cache_functionality, verify_historical_data_cache


@click.command('delete-user')
@click.argument('email')
@with_appcontext
def delete_user(email):
    user = User.query.filter_by(email=email).first()
    if user:
        Watchlist.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        click.echo(f"User with email {
                   email} and all associated data has been deleted")
    else:
        click.echo(f"No user found with email {email}")

# new cache testing command


@click.command('test-cache')
@click.argument('symbol', default='AAPL')
@with_appcontext
def test_cache(symbol):
    """Test the caching system with a given stock symbol."""
    click.echo(f"Testing cache functionality for {symbol}...")
    test_cache_functionality(symbol)
    verify_historical_data_cache(symbol)
