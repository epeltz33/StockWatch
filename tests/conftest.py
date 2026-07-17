import sys
from pathlib import Path

import pytest

# Add the project root directory to Python path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from app import create_app  # noqa: E402
from app.extensions import cache, db  # noqa: E402


@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "CACHE_TYPE": "SimpleCache",
            "CACHE_DEFAULT_TIMEOUT": 300,
            "CACHE_TIMEOUTS": {"price": 300, "details": 86400, "historical": 3600, "fallback": 600},
            # CSRF and rate limiting are exercised by dedicated tests; keep
            # them off for the rest of the suite
            "WTF_CSRF_ENABLED": False,
            "RATELIMIT_ENABLED": False,
        }
    )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _make_app(overrides):
    config = {
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "CACHE_TYPE": "SimpleCache",
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
    }
    config.update(overrides)
    return create_app(config)


@pytest.fixture
def app_with_csrf():
    """App with CSRF enforcement on, for testing token rejection."""
    app = _make_app({"WTF_CSRF_ENABLED": True})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def app_with_rate_limit():
    """App with rate limiting on, for testing 429 responses."""
    app = _make_app({"RATELIMIT_ENABLED": True})
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
