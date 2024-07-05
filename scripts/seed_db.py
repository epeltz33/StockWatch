import sys
import os

from app import create_app
from app.extensions import db
from app.models import User, Stock, Watchlist
from sqlalchemy.exc import IntegrityError, DataError


# set the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)


def seed_database():
    app = create_app()
    with app.app_context():
        # Check if data already exists
        if User.query.first() is not None:
            print("Database already contains data. Skipping seed.")
            return

        try:
            # Create some users
            user1 = User(username='testuser1', email='test1@example.com')
            user1.set_password('password123')
            user2 = User(username='testuser2', email='test2@example.com')
            user2.set_password('password456')

            # Create some stocks
            stock1 = Stock(symbol='AAPL', name='Apple Inc.')
            stock2 = Stock(symbol='GOOGL', name='Alphabet Inc.')
            stock3 = Stock(symbol='MSFT', name='Microsoft Corporation')

            # Create a watchlist for user1
            watchlist1 = Watchlist(name='Tech Stocks', user=user1)
            watchlist1.stocks.extend([stock1, stock2])

            # Add everything to the session and commit
            db.session.add_all([user1, user2, stock1, stock2, stock3, watchlist1])
            db.session.commit()

            print("Database seeded successfully!")
        except (IntegrityError, DataError) as e:
            db.session.rollback()
            print(f"Error seeding database: {str(e)}")
            print("Please ensure that your database schema is up to date.")


if __name__ == '__main__':
    seed_database()
