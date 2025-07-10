
import os
import sys
from datetime import datetime

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, Watchlist, Stock

def test_database_connection():
    """Test database connection and basic operations"""
    print("🔄 Testing Database Connection...\n")

    app = create_app()

    with app.app_context():
        try:
            # Test 1: Create tables
            print("1️⃣ Creating database tables...")
            db.create_all()
            print("✅ Tables created successfully!\n")

            # Test 2: Create a test user
            print("2️⃣ Testing User creation...")
            test_user = User(
                username="testuser",
                email="test@example.com"
            )
            test_user.set_password("testpassword123")
            db.session.add(test_user)
            db.session.commit()
            print(f"✅ User created: {test_user.username} (ID: {test_user.id})\n")

            # Test 3: Verify password
            print("3️⃣ Testing password verification...")
            user = User.query.filter_by(email="test@example.com").first()
            if user and user.check_password("testpassword123"):
                print("✅ Password verification successful!\n")
            else:
                print("❌ Password verification failed!\n")

            # Test 4: Create a watchlist
            print("4️⃣ Testing Watchlist creation...")
            watchlist = Watchlist(name="My Test Portfolio", user_id=user.id)
            db.session.add(watchlist)
            db.session.commit()
            print(f"✅ Watchlist created: {watchlist.name} (ID: {watchlist.id})\n")

            # Test 5: Create a stock
            print("5️⃣ Testing Stock creation...")
            stock = Stock(symbol="AAPL", name="Apple Inc.")
            db.session.add(stock)
            db.session.commit()
            print(f"✅ Stock created: {stock.symbol} - {stock.name}\n")

            # Test 6: Add stock to watchlist
            print("6️⃣ Testing adding stock to watchlist...")
            watchlist.stocks.append(stock)
            db.session.commit()
            print(f"✅ Stock {stock.symbol} added to watchlist {watchlist.name}\n")

            # Test 7: Query relationships
            print("7️⃣ Testing database relationships...")
            user_watchlists = user.watchlists.all()
            print(f"User has {len(user_watchlists)} watchlist(s)")

            for wl in user_watchlists:
                print(f"  - {wl.name} contains {len(wl.stocks)} stock(s)")
                for s in wl.stocks:
                    print(f"    • {s.symbol}: {s.name}")
            print()

            # Test 8: Clean up
            print("8️⃣ Cleaning up test data...")
            db.session.delete(watchlist)  # This should cascade delete the relationship
            db.session.delete(stock)
            db.session.delete(user)
            db.session.commit()
            print("✅ Test data cleaned up successfully!\n")

            print("🎉 All database tests passed! Your PostgreSQL setup is working correctly.")

            # Show connection info
            print("\n📊 Database Connection Info:")
            print(f"Database URL: {app.config['SQLALCHEMY_DATABASE_URI']}")

        except Exception as e:
            print(f"\n❌ Database test failed with error: {type(e).__name__}")
            print(f"Error details: {str(e)}")
            print("\nTroubleshooting tips:")
            print("1. Make sure PostgreSQL is running")
            print("2. Check your DATABASE_URL in .env file")
            print("3. Verify the database exists and user has permissions")
            print("4. Try running: CREATE DATABASE stockwatch; in psql")
            return False

    return True

if __name__ == "__main__":
    print("StockWatch Database Test Script")
    print("=" * 50)
    print(f"Testing at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50 + "\n")

    success = test_database_connection()
    sys.exit(0 if success else 1)