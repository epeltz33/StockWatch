from flask.cli import with_appcontext
import click
from app.models import User
from app.extensions import db


@click.command('delete-user')
@click.argument('email')
@with_appcontext
def delete_user(email):
    user = User.query.filter_by(email=email).first()
    if user:
        db.session.delete(user)
        db.session.commit()
        click.echo(f"User with email {email} has been deleted.")
    else:
        click.echo(f"No user found with email {email}")
