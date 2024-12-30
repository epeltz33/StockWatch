import os
import sys
import pytest
from pathlib import Path

# Add the project root directory to Python path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from app import create_app
from app.extensions import db, cache

@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'CACHE_TYPE': 'SimpleCache',
        'CACHE_DEFAULT_TIMEOUT': 300,
        'CACHE_TIMEOUTS': {
            'price': 300,
            'details': 86400,
            'historical': 3600,
            'fallback': 600
        }
    })

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()

@pytest.fixture
def runner(app):
    """Create a CLI test runner."""
    return app.test_cli_runner()

@pytest.fixture
def test_cache(app):
    """Create a test cache instance."""
    with app.app_context():
        cache.init_app(app)
        yield cache