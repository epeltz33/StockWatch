from celery_config import app
from pickler import get_stock_data
from your_database_module import get_all_watchlist_stocks

@app.task
def update_stock_data(ticker):
    get_stock_data(ticker)  # This will update the cache

@app.task
def update_watchlist_stocks():
    watchlist_stocks = get_all_watchlist_stocks()  # Implement this to fetch all unique stocks from user watchlists
    for ticker in watchlist_stocks:
        update_stock_data.delay(ticker)
