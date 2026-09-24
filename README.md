# 📈 StockWatch

[![CI](https://github.com/epeltz33/StockWatch/actions/workflows/ci.yml/badge.svg)](https://github.com/epeltz33/StockWatch/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**A deployed stock dashboard with interactive charts, per-user watchlists, and portfolio P/L tracking.** Built with **Flask** and **Plotly Dash**, backed by the [Massive.com](https://massive.com/) market API and **PostgreSQL**.

### What this project demonstrates

A full-stack web app taken end to end — designed, built, deployed, and running with a public, no-sign-up demo. It shows third-party API integration under rate limits, caching, authentication, schema migrations, a modular Flask + Dash architecture, and a test suite that drives the dashboard's callbacks over HTTP.

---

## 🔗 Try it

| | |
|---|---|
| **Demo (no sign-up)** | **[stockwatch-cqzs.onrender.com/demo/](https://stockwatch-cqzs.onrender.com/demo/)** |
| **App** | [stockwatch-cqzs.onrender.com](https://stockwatch-cqzs.onrender.com) — create an account, or use `demo@stockwatch.dev` / `Demo123!` |

The demo opens a populated dashboard straight away: three stocks with price history, a watchlist, and a portfolio, all from fixed sample data labelled **Sample data · Not live prices**. It is read-only and never calls the market-data API.

> ⏱️ Hosted on Render's free tier — the first visit after idle may take ~30s to cold-start, then responds normally.

---

## 🖼️ Screenshots

| Market view (demo) |
|---|
| ![Market view with chart, watchlist, and details](docs/screenshots/demo-market.png) |

| Portfolio (demo) |
|---|
| ![Portfolio with positions, allocation, and trade ledger](docs/screenshots/demo-portfolio.png) |

| Landing page | Watchlist management | Phone (390px) |
|---|---|---|
| ![Landing page with Explore demo](docs/screenshots/landing.png) | ![Creating a watchlist](docs/screenshots/watchlist-management.png) | ![Demo on a phone](docs/screenshots/demo-mobile.png) |

---

## ⭐ Highlights — why this matters

- **A demo that works in the first minute** — `/demo/` mounts the same dashboard on fixed synthetic data, so visitors explore charts, watchlists, and a portfolio with no account and no API dependency. The demo registers no editing callbacks, and the server rejects any other callback request with 403.
- **Honest numbers** — prices are labelled with the trading session they close (computed in New York time) and when they were retrieved; nothing claims to be live. Missing data reads as unavailable, never as a $0.00 price or a 0.00% day change. Header, details, watchlist, and portfolio use the same quote.
- **Real API integration under cost constraints** — one whole-market call per trading session prices every watchlist, chart, and portfolio symbol; responses are cached, a reload costs zero API calls, and a failed refresh keeps the last good prices with a retry.
- **Production-grade data practices** — Alembic migrations, SQLite locally and PostgreSQL in production, `Decimal` money math with an average-cost trade ledger.
- **Tested like it's used** — 220+ tests, including ones that post real Dash callback requests to prove the demo can't reach the provider, the database, or anyone's account.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🧪 **Sample demo** | Read-only dashboard at `/demo/` on deterministic sample data — opens on AAPL with its chart, a watchlist, and a portfolio |
| 🔐 **Authentication** | Registration and login via Flask-Login with hashed passwords, CSRF protection, and rate limiting |
| 📉 **Interactive charts** | Intraday bars for the latest session (1D) and daily history from 5D to MAX, with volume; periods the history can't cover are disabled |
| 📈 **Watchlists** | Multiple lists per user; each row shows closing price and day change, and the ticker itself selects the chart |
| 💼 **Portfolio tracking** | Buy/sell ledger with average-cost basis, realized and unrealized P/L, allocation, and priced/unpriced holding counts |
| 🏢 **Company details** | Last and previous close, day change, 52-week range, market cap, exchange, website, and description |
| 🕒 **Dated prices** | Each price names its session close and retrieval time; history-close fallbacks are labelled |
| ♻️ **Considerate refreshing** | Loads once, refreshes after edits or on demand, and every five minutes only while the Market view is open |
| 💾 **Remembers your view** | Ticker, watchlist, and chart period are kept for the browser session |
| ♿ **Accessible** | Keyboard operable with visible focus, labelled controls, confirmation before deletes, and WCAG AA text contrast |
| 📱 **Responsive** | Chart and details beside the watchlist on desktop; one column on tablet and phone, with no sideways scrolling |
| ⚡ **Caching** | 5-minute quotes, per-session market data, 1-hour history, 24-hour company details and logos |
| 🗄️ **Database migrations** | Schema versioning with Flask-Migrate / Alembic |

---

## 🧰 Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Flask, SQLAlchemy, Flask-Login, Gunicorn |
| **Frontend** | Plotly Dash, Dash Bootstrap Components |
| **Database** | PostgreSQL (production) · SQLite (development) |
| **API** | [Massive.com](https://massive.com/) |
| **Deployment** | Render, Docker Compose |

---

## 🏗️ Architecture

```text
┌──────────────┐      ┌───────────────────────────────┐      ┌──────────────┐
│   Browser    │◄────►│  Flask app                    │◄────►│  PostgreSQL  │
│              │      │   /       landing, auth       │      │              │
│              │      │   /dash/  Dash · LiveSource   │      └──────────────┘
│              │      │   /demo/  Dash · SampleSource │
└──────────────┘      └───────────────┬───────────────┘
                                      │ (LiveSource only)
                                      ▼
                              ┌───────────────┐
                              │ Massive.com   │
                              │ REST API      │
                              └───────────────┘
```

### Design decisions

- **One Dash page, mounted twice.** The dashboard's layout and callbacks are built from a *data source*: `/dash/` gets `LiveSource` (the signed-in user's account, priced by the API) and `/demo/` gets `SampleSource` (fixed sample data). The source is fixed on the server when each app is mounted, so nothing a browser sends can move the demo onto live or account data.
- **Deterministic sample data.** Sample prices are seeded Brownian bridges generated at import time; every demo figure — quotes, market caps, trade fills, portfolio P/L — derives from the same bars and runs through the real portfolio accounting.
- **Flask application factory + blueprints** keep routes, services, and models decoupled and independently testable.
- **Dash embedded in Flask** gives interactive charts without a separate JS build step. A few small clientside callbacks handle navigation, session storage, and click routing without server round trips.
- **Alembic migrations** keep schema changes reproducible across SQLite (dev) and PostgreSQL (prod).

### Project layout

```text
StockWatch/
├── app/
│   ├── blueprints/        # auth (login/register) · main (landing, redirects, logo proxy)
│   ├── services/          # stock_services (quotes, history, caching) · portfolio_services
│   │                      # (average-cost ledger) · sample_data (demo fixtures)
│   ├── utils/             # cache_manager
│   ├── models.py          # User, Watchlist, Stock, Transaction
│   └── templates/         # landing and auth pages (Jinja2)
├── frontend/
│   ├── dashboard.py       # Dash layout, callbacks, and mounting at /dash/ and /demo/
│   ├── data_sources.py    # LiveSource / SampleSource
│   ├── charts.py          # chart periods and the price figure
│   ├── stock_view.py      # stock header, quote, and details
│   ├── watchlist_panel.py # watchlist rows, status, refresh
│   ├── portfolio_tab.py   # portfolio section
│   ├── actions.py         # edits and confirmed deletes
│   ├── shell.py           # header, skeletons, dialog, page template
│   └── assets/            # stylesheet and clientside callbacks
├── migrations/            # Alembic database migrations
├── tests/                 # pytest suite (incl. HTTP-level Dash callback tests)
├── config.py              # App configuration
└── wsgi.py                # WSGI entry point
```

---

## 🚀 Getting Started

The quickest way to run StockWatch locally is with **SQLite** — no database server, no Docker, no ports to configure. You only need Python and a free API key. (Want production parity with PostgreSQL? See [Run against PostgreSQL](#-run-against-postgresql-optional) below.)

### Prerequisites

- **Python 3.11+**
- **Pipenv** — `pip install pipenv`
- A free [Massive.com](https://massive.com/) API key

### 1. Clone and install

```bash
git clone https://github.com/epeltz33/StockWatch.git
cd StockWatch
pipenv install
```

### 2. Configure environment variables

Create a `.env` file in the project root. For the SQLite quickstart, **leave `DATABASE_URL` out** — the app falls back to a local SQLite file (`app.db`):

```dotenv
SECRET_KEY=any-random-string
POLYGON_API_KEY=your_massive_api_key
```

### 3. Create the database schema

```bash
pipenv run flask db upgrade
```

This creates `app.db` with all tables. `FLASK_APP` is already set in `.flaskenv`, so no extra flags are needed.

### 4. (Optional) Seed the demo account

```bash
pipenv run flask seed-demo-user
```

Creates the demo account (`demo@stockwatch.dev` / `Demo123!`) with a pre-populated watchlist, so you can log in and see data right away. (The sample demo at `/demo/` needs neither this account nor an API key.)

### 5. Run the app

```bash
pipenv run flask run --port 8080
```

The app is available at **http://localhost:8080**, and the sample demo at **http://localhost:8080/demo/**.

> For a production-style server, use Gunicorn: `pipenv run gunicorn wsgi:app --bind 0.0.0.0:8080`

### 🐘 Run against PostgreSQL (optional)

For parity with production, run PostgreSQL locally with the bundled Docker setup. The container is published on host port **15433** (mapped to its internal `5432`) so it won't clash with an existing Postgres:

```bash
docker compose up -d    # start
docker compose down     # stop
```

Point `DATABASE_URL` at it in your `.env` and re-run migrations:

```dotenv
SECRET_KEY=any-random-string
POLYGON_API_KEY=your_massive_api_key
DATABASE_URL=postgresql://stockwatch_user:stockwatch_password@localhost:15433/stockwatch
```

```bash
pipenv run flask db upgrade
pipenv run flask run --port 8080
```

<details>
<summary>Default Docker connection details (local development only)</summary>

| Variable | Value |
|---|---|
| **Host port** | `15433` (mapped to the container's internal `5432`) |
| `POSTGRES_DB` | `stockwatch` |
| `POSTGRES_USER` | `stockwatch_user` |
| `POSTGRES_PASSWORD` | `stockwatch_password` |

</details>

---

## 🌐 Deployment

### Render (recommended)

StockWatch ships with a [`render.yaml`](render.yaml) blueprint for one-click deployment.

1. **Push to GitHub** — Render deploys from Git.
2. **Create a Render account** at [render.com](https://render.com) and connect GitHub.
3. **Create a Blueprint** — go to **Dashboard → New → Blueprint** and select the `StockWatch` repo. Render detects `render.yaml` and provisions:
   - A **PostgreSQL** database (`stockwatch-db`, ~$7/mo)
   - A **web service** (`stockwatch`, free tier with cold starts)
4. **Set secrets** — when prompted, set `POLYGON_API_KEY` to your [Massive.com](https://massive.com/) key. `SECRET_KEY` and `DATABASE_URL` are generated automatically.
5. **Seed the demo account** — after the first deploy, open the Render **Shell** for the web service and run `flask seed-demo-user`.
6. **Verify:**
   - `https://your-app.onrender.com/health` → `{"status": "healthy"}`
   - Open `/demo/` without logging in: AAPL's chart, the sample watchlist, and the portfolio load
   - Log in with `demo@stockwatch.dev` / `Demo123!`
   - Search a ticker and confirm chart data loads

> **Note:** Migrations run in the **start command**, not the build command — Render's internal database hostname is only reachable at runtime.

### DigitalOcean App Platform (alternative)

Use [`app.yaml`](app.yaml) instead:

1. Add a **Managed PostgreSQL** database in the DO dashboard.
2. Set `DATABASE_URL`, `SECRET_KEY`, and `POLYGON_API_KEY` as encrypted env vars.
3. Connect the GitHub repo — migrations run automatically on build.

---

## 🧪 Running Tests

```bash
pipenv run pytest
```

CI runs `ruff check`, `ruff format --check`, and the suite with a coverage gate. Besides unit tests, the suite drives the dashboard's callbacks over HTTP (`tests/dash_client.py`) against a counting fake of the market-data client (`tests/fake_market.py`), which is how it checks that the demo never reaches the provider, the database, or an account, and how many API calls each interaction costs.

---

## 📄 License

Released under the [MIT License](LICENSE).

## 📬 Contact

Questions or feedback? Reach out at [erpeltz@gmail.com](mailto:erpeltz@gmail.com).
