
---

# 📈 StockWatch

A web application for monitoring stocks and managing personalized watchlists. Built with **Flask** and **Plotly Dash**, StockWatch provides real-time market data, interactive charts, and per-user watchlist tracking — all powered by the [Massive.com](https://massive.com/) API.

## Live Demo

> Deploy using the steps below, then add your public URL here.

| | |
|---|---|
| **URL** | `https://your-app.onrender.com` |
| **Demo login** | `demo@stockwatch.dev` / `Demo123!` |

> Free-tier hosting may take ~30s to wake up on the first visit after idle time.

## ✨ Features

| Feature | Description |
|---|---|
| 🔐 **Authentication** | Secure registration & login with Flask-Login and hashed passwords |
| 📊 **Live Market Data** | Current prices and company details via the Polygon.io REST API |
| 📈 **Watchlist Management** | Create, view, and remove stocks across multiple watchlists |
| 📉 **Interactive Charts** | Candlestick / line charts with volume overlays built in Plotly |
| ⚡ **Caching** | Flask-Caching layer to reduce redundant API calls |
| 🗄️ **Migrations** | Database schema managed with Flask-Migrate / Alembic |

## 🏗️ Architecture

```text
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   Browser    │◄────►│  Flask App   │◄────►│  PostgreSQL  │
│              │      │  + Dash UI   │      │              │
└──────────────┘      └──────┬───────┘      └──────────────┘
                             │
                             ▼
                      ┌──────────────┐
                      │ Polygon.io   │
                      │ REST API     │
                      └──────────────┘
```

### Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Flask, SQLAlchemy, Flask-Login, Flask-Caching, Gunicorn |
| **Frontend** | Plotly Dash, Dash Bootstrap Components |
| **Database** | PostgreSQL (production) · SQLite (development) |
| **API** | [Polygon.io](https://polygon.io/) |
| **Deployment** | Render, DigitalOcean App Platform, Docker Compose |

### Project Layout

```text
StockWatch/
├── app/
│   ├── blueprints/      # auth · main · stock · user route handlers
│   ├── services/        # stock_services · user_services (business logic)
│   ├── utils/           # cache_manager · cache_monitor
│   ├── models.py        # User, Watchlist, Stock ORM models
│   ├── extensions.py    # db, migrate, login, cache instances
│   └── templates/       # Jinja2 HTML templates
├── frontend/
│   └── dashboard.py     # Plotly Dash interactive dashboard
├── migrations/          # Alembic database migrations
├── tests/               # pytest test suite
├── config.py            # App configuration
├── wsgi.py              # WSGI entry point
├── docker-compose.yml   # Local PostgreSQL via Docker
├── Pipfile              # Pipenv dependencies
└── requirements.txt     # pip dependencies
```

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+**
- **Pipenv** — `pip install pipenv`
- **Docker** (optional, for local PostgreSQL)
- A free [Polygon.io](https://polygon.io/) API key

### 1. Clone the Repository

```bash
git clone https://github.com/epeltz33/StockWatch.git
cd StockWatch
```

### 2. Install Dependencies

```bash
pipenv install
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```dotenv
SECRET_KEY=your_secret_key
DATABASE_URL=postgresql://stockwatch_user:stockwatch_password@localhost:15433/stockwatch
POLYGON_API_KEY=your_polygon_api_key
```

> **Tip:** If `DATABASE_URL` is omitted, the app falls back to a local SQLite database.

### 4. Start the Database

```bash
# Option A — Docker (recommended)
docker compose up -d

# Option B — Use an existing PostgreSQL instance and set DATABASE_URL accordingly
```

### 5. Run Migrations

```bash
pipenv run flask db upgrade
```

### 6. Start the Application

```bash
# Development
pipenv run flask run

# Production-style
pipenv run gunicorn wsgi:app --bind 0.0.0.0:8080
```

The app will be available at **http://localhost:8080**.

## 🌐 Deploy to Render (Recommended)

StockWatch ships with a [`render.yaml`](render.yaml) blueprint for one-click deployment.

### 1. Push to GitHub

Ensure your repo is pushed to GitHub (Render deploys from Git).

### 2. Create a Render account

Sign up at [render.com](https://render.com) and connect your GitHub account.

### 3. Create a Blueprint

1. Go to **Dashboard → New → Blueprint**
2. Select the `StockWatch` repository
3. Render will detect `render.yaml` and provision:
   - A **PostgreSQL** database (`stockwatch-db`, ~$7/mo)
   - A **web service** (`stockwatch`, free tier with cold starts)

### 4. Set secrets

When prompted during blueprint setup, set:

| Variable | Value |
|---|---|
| `POLYGON_API_KEY` | Your [Polygon.io](https://polygon.io/) API key |

`SECRET_KEY` and `DATABASE_URL` are generated automatically.

> **Note:** Migrations run in the **start command**, not the build command. Render's internal database hostname is only reachable at runtime, not during builds.

### 5. Seed the demo account

After the first successful deploy, open the Render **Shell** for the web service and run:

```bash
flask seed-demo-user
```

### 6. Verify

- `https://your-app.onrender.com/health` → `{"status": "healthy"}`
- Log in with `demo@stockwatch.dev` / `Demo123!`
- Search a ticker and confirm chart data loads

### Alternative: DigitalOcean App Platform

Use [`app.yaml`](app.yaml) instead. You will need to:

1. Add a **Managed PostgreSQL** database in the DO dashboard
2. Set `DATABASE_URL`, `SECRET_KEY`, and `POLYGON_API_KEY` as encrypted env vars
3. Connect the GitHub repo — migrations run automatically on build

## 🧪 Running Tests

```bash
pipenv run pytest
```

## 🐳 Docker (Local Database)

The included `docker-compose.yml` spins up a PostgreSQL 15 instance:

```bash
docker compose up -d    # start
docker compose down      # stop
```

Default credentials (for local development only):

| Variable | Value |
|---|---|
| `POSTGRES_DB` | `stockwatch` |
| `POSTGRES_USER` | `stockwatch_user` |
| `POSTGRES_PASSWORD` | `stockwatch_password` |

## 📬 Contact

Questions or feedback? Reach out at [erpeltz@gmail.com](mailto:erpeltz@gmail.com).

---
