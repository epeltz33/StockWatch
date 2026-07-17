# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (Pipenv is the source of truth; requirements.txt is a generated mirror for CI/Render)
pipenv install

# Run the dev server (FLASK_APP is set via .flaskenv, no extra flags needed)
pipenv run flask run --port 8080

# Run the full test suite
pipenv run pytest

# Run a single test file / test
pipenv run pytest tests/test_stock_integration.py
pipenv run pytest tests/test_stock_integration.py::test_name -q

# Database migrations (Alembic via Flask-Migrate)
pipenv run flask db migrate -m "description"
pipenv run flask db upgrade

# Seed/repair the demo account (idempotent — safe to rerun on every deploy)
pipenv run flask seed-demo-user

# Local PostgreSQL for prod parity (published on host port 15433, not 5432)
docker compose up -d
docker compose down
```

No SQLite/Postgres switch flag is needed — `config.py` picks PostgreSQL automatically when `DATABASE_URL` is set and falls back to a local `app.db` SQLite file otherwise.

## Architecture

**Flask application factory + blueprints**, with a Dash app mounted inside the same Flask process.

- `app/__init__.py` — `create_app()` factory. Initializes extensions (`db`, `migrate`, `login`, `cache` from `app/extensions.py`), registers blueprints, then imports and mounts the Dash app from `frontend/dashboard.py` at `/dash/`. Blueprint and Dash registration are each wrapped in try/except so a failure in one subsystem doesn't take down the whole app — check console output for `✗ Failed to register ...` when something isn't showing up.
- `app/blueprints/` — `auth`, `stock`, `user`, `main`. Route handlers only; business logic lives in `app/services/`.
- `app/services/stock_services.py` — all external market-data logic. Wraps the Massive.com (formerly Polygon.io) `RESTClient` — the PyPI package (`polygon-api-client`), import path (`from polygon import RESTClient`), and env var (`POLYGON_API_KEY`) all still use the pre-rename name; this is expected, not a bug to fix. Every fetch function (`get_stock_price`, `get_stock_data`, `get_intraday_stock_data`, `get_company_details`) checks `StockCache` first and only calls the API on a miss.
- `app/utils/cache_manager.py` — `StockCache` wraps Flask-Caching with per-data-type TTLs (`price`/`intraday`: 5 min, `historical`: 1 hour, `details`: 24 hours). Cache keys are `stock:{symbol}:{data_type}[:kwarg=val...]`. When changing cache behavior, edit `DEFAULT_TIMEOUTS` here rather than hardcoding timeouts at call sites.
- `app/models.py` — `User` (Flask-Login `UserMixin`), `Watchlist`, `Stock`, joined by the `watchlist_stocks` association table with `ondelete='CASCADE'`. Deleting a user cascades to their watchlists (`cascade='all, delete-orphan'` on `User.watchlists`); deleting a watchlist cascades to the association rows only, not to `Stock` rows themselves (stocks are shared/global, not owned by a watchlist).
- `frontend/dashboard.py` — Plotly Dash app (`create_dash_app`), mounted at `/dash/` inside the Flask server rather than run standalone. Chart callbacks distinguish an intraday "Today" view (uses `get_intraday_stock_data`, session-bar bars) from 5D–MAX ranges (uses `get_stock_data`, daily OHLCV).
- `app/cli.py` — custom `flask` CLI commands (`delete-user`, `test-cache`, `seed-demo-user`), registered onto `app.cli` in `create_app()`. `seed-demo-user` is intentionally idempotent (checked via `filter_by` before insert) since it runs on every production deploy.
- Two WSGI entry points exist: `wsgi.py` (used by Gunicorn in production/`run.sh`, enforces required env vars when `_is_production()` detects Render/DigitalOcean/`FLASK_ENV=production`) and `app.py` (simpler fallback). Both degrade to a minimal error-reporting Flask app with a `/health` endpoint if `create_app()` raises, instead of crashing outright — useful for diagnosing prod startup failures via the `/health` response body.

## Testing

`tests/conftest.py` builds the app with an in-memory SQLite DB (`sqlite:///:memory:`) and `SimpleCache`, tearing down tables after each test. Use the `app`, `client`, `runner`, and `test_cache` fixtures rather than hitting the real database or Massive.com API in tests.

## Deployment

Two deploy targets are maintained in parallel: `render.yaml` (primary — migrations run in the *start* command, not build, since Render's internal DB hostname is only reachable at runtime) and `app.yaml` for DigitalOcean (migrations run during build via `build.sh`). Required prod env vars: `DATABASE_URL`, `SECRET_KEY`, `POLYGON_API_KEY`.
