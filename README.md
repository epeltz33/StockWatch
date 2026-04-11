
---

# 📈 StockWatch

A web-based stock portfolio monitoring application built with **Flask** and **Plotly Dash**. Track your favorite stocks, manage personalized watchlists, and visualize historical market data through interactive charts.

---

## Table of Contents

- [Features](#features)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Usage](#usage)
- [Running Tests](#running-tests)
- [Deployment](#deployment)
- [Contact](#contact)

---

## Features

- 🔐 **User Authentication** — Secure registration and login with hashed passwords
- 📊 **Stock Data** — Fetch stock prices and company details via the [Polygon.io](https://polygon.io/) API (delayed data on the free tier)
- 📈 **Watchlist Management** — Create, view, and remove stocks from personalized watchlists
- 📉 **Interactive Data Visualization** — Candlestick charts, volume overlays, and historical trend lines powered by Plotly
- 🏗️ **RESTful API** — JSON endpoints for stock info, historical data, and watchlist operations
- ⚡ **Caching** — Flask-Caching integration for improved performance
- 🐳 **Docker Support** — Docker Compose setup for local PostgreSQL development

## Technology Stack

| Layer        | Technologies                                          |
| ------------ | ----------------------------------------------------- |
| **Backend**  | Flask, SQLAlchemy, Flask-Login, Flask-Migrate, Celery |
| **Frontend** | Plotly Dash, Dash Bootstrap Components                |
| **Database** | PostgreSQL (SQLite for local development)             |
| **API**      | [Polygon.io](https://polygon.io/)                    |
| **Caching**  | Flask-Caching, Redis                                  |
| **Server**   | Gunicorn                                              |
| **Hosting**  | DigitalOcean App Platform                             |

## Project Structure

```
StockWatch/
├── app/                    # Flask application package
│   ├── __init__.py         # App factory (create_app)
│   ├── models.py           # SQLAlchemy models (User, Watchlist, Stock)
│   ├── extensions.py       # Extension instances (db, migrate, login, cache)
│   ├── blueprints/         # Route blueprints
│   │   ├── auth.py         #   Authentication (register, login, logout)
│   │   ├── main.py         #   Landing page & core routes
│   │   ├── stock.py        #   Stock API endpoints
│   │   └── user.py         #   User profile & settings
│   ├── services/           # Business logic
│   │   ├── stock_services.py   # Polygon.io integration & stock CRUD
│   │   └── user_services.py    # User-related operations
│   ├── templates/          # Jinja2 HTML templates
│   └── static/             # CSS, JS, images
├── frontend/
│   └── dashboard.py        # Plotly Dash interactive dashboard
├── migrations/             # Alembic database migrations
├── tests/                  # Test suite
│   ├── conftest.py
│   ├── test_cache_system.py
│   └── test_stock_integration.py
├── app.py                  # Application entry point
├── wsgi.py                 # WSGI entry point (for Gunicorn)
├── config.py               # Configuration (env-based)
├── docker-compose.yml      # Local PostgreSQL via Docker
├── Pipfile                 # Pipenv dependencies
├── requirements.txt        # pip dependencies
├── Procfile                # Gunicorn process definition
├── app.yaml                # DigitalOcean App Platform spec
└── build.sh                # Deployment build script
```

## Getting Started

### Prerequisites

- **Python 3.11+**
- **Pipenv** (or pip + virtualenv)
- **Docker** (optional — for local PostgreSQL)
- A free [Polygon.io API key](https://polygon.io/)

### 1. Clone the Repository

```bash
git clone https://github.com/epeltz33/StockWatch.git
cd StockWatch
```

### 2. Install Dependencies

```bash
pipenv install
pipenv shell
```

Or using pip:

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set Up Environment Variables

Create a `.env` file in the project root:

```plaintext
SECRET_KEY=your_secret_key
DATABASE_URL=postgresql://stockwatch_user:stockwatch_password@localhost:5432/stockwatch
POLYGON_API_KEY=your_polygon_api_key
```

> **Note:** If `DATABASE_URL` is not set, the app falls back to a local SQLite database automatically.

### 4. Start the Database (Docker)

```bash
docker compose up -d
```

This spins up a PostgreSQL 15 instance with the credentials from `docker-compose.yml`.

### 5. Initialize the Database

```bash
flask db upgrade
```

### 6. Run the Application

```bash
flask run
```

The app will be available at **http://localhost:5000**.

## Usage

1. **Register** — Create an account on the registration page.
2. **Log in** — Sign in with your credentials.
3. **Search stocks** — Look up any ticker symbol to view real-time price and company details.
4. **Manage watchlists** — Add or remove stocks from your personalized watchlists.
5. **View charts** — Explore interactive historical charts on the Dash dashboard.

## Running Tests

```bash
python -m pytest tests/
```

## Deployment

StockWatch is configured for **DigitalOcean App Platform**. The key deployment files are:

| File                 | Purpose                                          |
| -------------------- | ------------------------------------------------ |
| `app.yaml`           | DigitalOcean App Platform specification          |
| `Procfile`           | Gunicorn command for the web process             |
| `build.sh`           | Install dependencies & run migrations on deploy  |
| `wsgi.py`            | WSGI entry point used by Gunicorn                |

Set the required environment variables (`SECRET_KEY`, `DATABASE_URL`, `POLYGON_API_KEY`) in your DigitalOcean app settings.

## Contact

For questions or feedback, please reach out at [erpeltz@gmail.com](mailto:erpeltz@gmail.com).

---

