import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from app.utils.cache_manager import StockCache
from app.services.stock_services import get_stock_price, get_company_details, get_stock_data
from flask_caching import Cache

@pytest.fixture
def mock_cache():
    """Create a mock cache instance."""
    cache = Mock(spec=Cache)
    cache.get.return_value = None
    return cache

@pytest.fixture
def stock_cache(mock_cache):
    """Create a StockCache instance with mock cache."""
    return StockCache(mock_cache)

def test_cache_key_generation(stock_cache):
    """Test cache key generation with different inputs."""
    # Test basic key generation
    key = stock_cache._get_cache_key("AAPL", "price")
    assert key == "stock:AAPL:price"

    # Test key generation with additional parameters
    key_with_params = stock_cache._get_cache_key(
        "AAPL",
        "historical",
        start_date="2024-01-01",
        end_date="2024-01-31"
    )
    assert key_with_params == "stock:AAPL:historical:end_date=2024-01-31:start_date=2024-01-01"

def test_cache_get_set(stock_cache, mock_cache):
    """Test cache get and set operations."""
    test_data = {"price": 150.0}
    stock_cache.set_cached_data("AAPL", "price", test_data)

    # Verify set was called with correct parameters
    mock_cache.set.assert_called_once()
    args = mock_cache.set.call_args[0]
    assert args[0] == "stock:AAPL:price"
    assert args[1] == test_data

    # Test cache get
    mock_cache.get.return_value = test_data
    cached_data = stock_cache.get_cached_data("AAPL", "price")
    assert cached_data == test_data

def test_cache_timeouts(stock_cache, mock_cache):
    """Test different cache timeouts for different data types."""
    test_data = {"price": 150.0}

    # Test price cache timeout
    stock_cache.set_cached_data("AAPL", "price", test_data)
    assert mock_cache.set.call_args[1]['timeout'] == 300  # 5 minutes

    # Test details cache timeout
    stock_cache.set_cached_data("AAPL", "details", test_data)
    assert mock_cache.set.call_args[1]['timeout'] == 86400  # 24 hours

@patch('app.services.stock_services.polygon_client')
def test_stock_price_caching(mock_polygon, app, test_cache):
    """Test stock price caching behavior."""
    with app.app_context():
        # Mock polygon response
        mock_response = Mock()
        mock_response.close = 150.0
        mock_polygon.get_daily_open_close_agg.return_value = mock_response

        # First call - should hit API
        price = get_stock_price("AAPL")
        assert price == 150.0
        mock_polygon.get_daily_open_close_agg.assert_called_once()

        # Second call - should hit cache
        cached_price = get_stock_price("AAPL")
        assert cached_price == 150.0
        assert mock_polygon.get_daily_open_close_agg.call_count == 1  # No additional API calls

@patch('app.services.stock_services.polygon_client')
def test_api_error_handling(mock_polygon, app, test_cache):
    """Test error handling when API calls fail."""
    with app.app_context():
        # Mock API error
        mock_polygon.get_daily_open_close_agg.side_effect = Exception("API Error")

        # Should return None but not raise exception
        price = get_stock_price("AAPL")
        assert price is None

@patch('app.services.stock_services.polygon_client')
def test_historical_data_handling(mock_polygon, app, test_cache):
    """Test historical data retrieval and caching."""
    with app.app_context():
        # Mock historical data response
        mock_result = Mock()
        mock_result.t = int(datetime.now().timestamp() * 1000)
        mock_result.c = 150.0
        mock_result.v = 1000000

        mock_response = Mock()
        mock_response.results = [mock_result]
        mock_polygon.get_aggs.return_value = mock_response

        # Get historical data
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        data = get_stock_data("AAPL", start_date, end_date)
        assert len(data) == 1
        assert data[0]['close'] == 150.0
        assert data[0]['volume'] == 1000000

def test_cache_key_conflicts(stock_cache):
    """Test that different cache keys don't conflict."""
    # Set different types of data
    stock_cache.set_cached_data("AAPL", "price", 150.0)
    stock_cache.set_cached_data("AAPL", "details", {"name": "Apple Inc."})

    # Verify keys are different
    price_key = stock_cache._get_cache_key("AAPL", "price")
    details_key = stock_cache._get_cache_key("AAPL", "details")
    assert price_key != details_key