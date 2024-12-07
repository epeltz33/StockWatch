from flask import current_app
import time
from app.services.stock_services import get_stock_price, get_company_details, get_stock_data, StockDataCache
from datetime import datetime, timedelta
from app import cache
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_cache_functionality(symbol: str = "AAPL"):
    """
    Test cache functionality for a given stock symbol.
    This function will make multiple API calls and verify cache behavior.
    """
    print(f"\n=== Testing Cache Functionality for {symbol} ===\n")

    # Test price caching
    print("Testing Price Caching:")
    print("-" * 50)

    # First call - should hit the API
    start_time = time.time()
    price = get_stock_price(symbol)
    first_call_time = time.time() - start_time
    print(f"First call (API): ${
          price:.2f} - Took {first_call_time:.3f} seconds")

    # Second call - should hit cache
    start_time = time.time()
    cached_price = get_stock_price(symbol)
    second_call_time = time.time() - start_time
    print(f"Second call (Cache): ${
          cached_price:.2f} - Took {second_call_time:.3f} seconds")

    # Verify cache is faster
    speed_improvement = (
        first_call_time / second_call_time) if second_call_time > 0 else float('inf')
    print(f"Cache is {speed_improvement:.1f}x faster than API call")

    # Test company details caching
    print("\nTesting Company Details Caching:")
    print("-" * 50)

    # First call - should hit the API
    start_time = time.time()
    details = get_company_details(symbol)
    first_call_time = time.time() - start_time
    print(f"First call (API) - Took {first_call_time:.3f} seconds")
    print(f"Company Name: {details.get('name')}")

    # Second call - should hit cache
    start_time = time.time()
    cached_details = get_company_details(symbol)
    second_call_time = time.time() - start_time
    print(f"Second call (Cache) - Took {second_call_time:.3f} seconds")

    # Verify cache keys exist
    print("\nChecking Cache Keys:")
    print("-" * 50)

    # Get cache keys for the symbol
    price_key = StockDataCache.get_cache_key(symbol, 'price')
    details_key = StockDataCache.get_cache_key(symbol, 'details')

    # Check if keys exist in cache
    price_exists = cache.get(price_key) is not None
    details_exist = cache.get(details_key) is not None

    print(f"Price cache exists: {price_exists}")
    print(f"Details cache exists: {details_exist}")

    # Print cache configuration
    print("\nCache Configuration:")
    print("-" * 50)
    print(f"Cache Type: {current_app.config['CACHE_TYPE']}")
    print(f"Default Timeout: {
          current_app.config['CACHE_DEFAULT_TIMEOUT']} seconds")
    price_timeout = current_app.config.get(
        'CACHE_TIMEOUTS', {}).get('price', 300)
    details_timeout = current_app.config.get(
        'CACHE_TIMEOUTS', {}).get('details', 86400)
    print(f"Price Cache Timeout: {price_timeout} seconds")
    print(f"Details Cache Timeout: {details_timeout} seconds")


def verify_historical_data_cache(symbol: str = "AAPL", days: int = 30):
    """
    Verify historical data caching functionality.
    """
    print(f"\n=== Testing Historical Data Cache for {symbol} ===\n")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # First call - should hit the API
    print("Testing Historical Data Caching:")
    print("-" * 50)

    start_time = time.time()
    data = get_stock_data(symbol, start_date.strftime('%Y-%m-%d'),
                          end_date.strftime('%Y-%m-%d'))
    first_call_time = time.time() - start_time
    print(f"First call (API) - Took {first_call_time:.3f} seconds")
    print(f"Data points retrieved: {len(data)}")

    # Second call - should hit cache
    start_time = time.time()
    cached_data = get_stock_data(symbol, start_date.strftime('%Y-%m-%d'),
                                 end_date.strftime('%Y-%m-%d'))
    second_call_time = time.time() - start_time
    print(f"Second call (Cache) - Took {second_call_time:.3f} seconds")
    print(f"Cached data points: {len(cached_data)}")

    # Verify cache is faster
    speed_improvement = (
        first_call_time / second_call_time) if second_call_time > 0 else float('inf')
    print(f"Cache is {speed_improvement:.1f}x faster than API call")

    # Print historical data cache configuration
    historical_timeout = current_app.config.get(
        'CACHE_TIMEOUTS', {}).get('historical', 3600)
    print(f"\nHistorical Data Cache Timeout: {historical_timeout} seconds")


if __name__ == "__main__":
    # Test with a sample stock
    test_cache_functionality("AAPL")
    verify_historical_data_cache("AAPL")
