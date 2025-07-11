import os
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app import create_app, db
from app.models import User, Watchlist, Stock

def create_tables_safe():
    """Create tables without dropping existing ones"""
    print("Creating database tables (safe mode)...")

    app = create_app()

    with app.app_context():
        try:
            # Create all tables (won't affect existing ones)
            print("\nCreating tables...")
            db.create_all()
            print("✓ Tables created successfully!")

            # Test the connection
            print("\nTesting database connection...")
            result = db.session.execute(db.text("SELECT 1"))
            print("✓ Database connection successful!")

            print("\n" + "="*60)
            print("SUCCESS: Database is ready!")
            print("You can now register users and use the application.")
            print("="*60)

            return True

        except Exception as e:
            print(f"\n✗ ERROR: Failed to create tables: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    print("StockWatch Database Table Creator")
    print("="*60)
    create_tables_safe()
