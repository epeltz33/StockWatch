
---

# 📈 StockWatch

## Overview

The **StockWatch App** is a web-based application designed to help users monitor and manage their stock portfolios. Built with Flask for the backend and Plotly Dash for the frontend, this app allows users to track their favorite stocks, view historical data, and maintain a personalized watchlist.

## Features

- 🔐 **User Authentication**: Secure registration and login functionalities.
- 📊 **Stock Data Integration**: Fetch delayed stock data using the Polygon.io API.
- 📈 **Watchlist Management**: Add, view, and remove stocks from your personalized watchlist.
- 📉 **Data Visualization**: Interactive charts and graphs to visualize stock performance.
- 📱 **Responsive Design**: Accessible on desktop.

## Technology Stack

- **Backend**: Flask, SQLAlchemy, Flask-Login, Flask-Migrate
- **Frontend**: Plotly Dash, Dash Bootstrap Components, CSS
- **Database**: SQLite (development), PostgreSQL (production)
- **API**: Polygon.io for real-time stock data
- **Caching**: Flask-Caching (supports Redis, Memcached)
- **Testing**: pytest with coverage reporting
- **Development Tools**: Python 3.12+, Git, VSCode
- **Deployment**: Gunicorn, Docker support

## Getting Started

### Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.12+** - [Download from python.org](https://www.python.org/downloads/)
- **pip** - Comes with Python 3.12+
- **Git** - [Download from git-scm.com](https://git-scm.com/downloads)
- **Polygon.io API Key** - Sign up at [polygon.io](https://polygon.io/) for stock data access

### Installation

Follow these steps to set up StockWatch locally:

#### 1. Clone the Repository
```bash
git clone https://github.com/epeltz33/StockWatch.git
cd StockWatch
```

#### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 3. Environment Configuration
Create a `.env` file in the root directory with the following variables:

```bash
# Required: Flask secret key for session management
SECRET_KEY=your-super-secret-key-change-this-in-production

# Required: Polygon.io API key for stock data
POLYGON_API_KEY=your_polygon_api_key_here

# Optional: Database URL (defaults to SQLite if not specified)
# For SQLite (default): 
# DATABASE_URL=sqlite:///app.db
# For PostgreSQL (production):
# DATABASE_URL=postgresql://username:password@localhost/stockwatch

# Optional: Application port (defaults to 8080)
PORT=8080
```

**Environment Variable Details:**
- `SECRET_KEY`: Generate a secure random string. You can use: `python -c "import secrets; print(secrets.token_hex(32))"`
- `POLYGON_API_KEY`: Required for fetching stock data. Get it from [polygon.io](https://polygon.io/)
- `DATABASE_URL`: Uses SQLite by default. For production, use PostgreSQL
- `PORT`: Server port, defaults to 8080

#### 4. Database Setup
Initialize the database tables:
```bash
python create_tables.py
```

#### 5. Running the Application

**Development Server:**
```bash
python app.py
```
The application will be available at `http://localhost:8080`

**Production Server (using Gunicorn):**
```bash
bash run.sh
```

### Running Tests

Execute the test suite to ensure everything is working correctly:

```bash
# Install pytest if not already installed
pip install pytest

# Run all tests
python -m pytest tests/ -v

# Run tests with coverage (optional)
pip install pytest-cov
python -m pytest tests/ --cov=app --cov-report=html
```

The test suite includes:
- Cache system tests
- Stock integration tests  
- Database constraint tests
- Error handling tests
   

### Project Structure

```
StockWatch/
├── app/                    # Flask application
│   ├── blueprints/        # Route handlers (auth, stock, user, main)
│   ├── models.py          # Database models
│   ├── services/          # Business logic and external API integration
│   ├── static/           # CSS, JS, images
│   └── templates/        # Jinja2 HTML templates
├── frontend/             # Plotly Dash dashboard
├── tests/               # Test suite
├── migrations/          # Database migration files
├── config.py           # Application configuration
├── requirements.txt    # Python dependencies
├── create_tables.py   # Database initialization script
└── app.py            # Application entry point
```

## Usage

1. **Access the Application**:
   - Open your browser and navigate to `http://localhost:8080`

2. **Register and Login**:
   - Create a new account on the registration page
   - Use your credentials to log in

3. **Search for Stocks**:
   - Use the search functionality to find stocks and view their data
   - View real-time and historical stock information

4. **Add to Watchlist**:
   - Add stocks to your personalized watchlist for easy tracking
   - Monitor your favorite stocks in one place

5. **View Data Visualizations**:
   - Access interactive charts and graphs through the Dash dashboard
   - Analyze historical data and stock performance

## Troubleshooting

### Common Issues

**1. Application won't start - Missing API Key**
```
Error: Must specify env var POLYGON_API_KEY or pass api_key in constructor
```
**Solution:** Ensure you have set the `POLYGON_API_KEY` in your `.env` file with a valid API key from polygon.io.

**2. Database Connection Issues**
```
Error: Failed to create tables
```
**Solution:** 
- Ensure you've run `python create_tables.py` 
- Check that your `DATABASE_URL` is correctly formatted
- For SQLite, ensure the directory is writable

**3. Cache Warnings**
```
Flask-Caching: CACHE_TYPE is set to null, caching is effectively disabled
```
**Solution:** This is normal for development. In production, configure Redis or another cache backend.

**4. Port Already in Use**
```
Error: [Errno 98] Address already in use
```
**Solution:** 
- Change the port in your `.env` file: `PORT=8081`
- Or kill the process using the port: `lsof -ti:8080 | xargs kill -9`

**5. Import Errors**
```
ModuleNotFoundError: No module named 'app'
```
**Solution:** Ensure you're running commands from the project root directory and have installed all dependencies.

### Development Tips

- **Database Reset**: Delete `app.db` file and run `python create_tables.py` again
- **Clear Cache**: Restart the application to clear in-memory cache
- **Debug Mode**: Set `FLASK_ENV=development` for detailed error messages
- **Logs**: Check console output for detailed error information

### Getting Help

- **Issues**: Report bugs and feature requests on [GitHub Issues](https://github.com/epeltz33/StockWatch/issues)
- **Documentation**: Check the inline code documentation for API details
- **Contributing**: See the contributing guidelines for development setup

## Contact

For questions or feedback, please contact [erpeltz@gmail.com](mailto:erpeltz@gmail.com).

---

