import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from app.utils.cache_manager import StockCache
from app.services.stock_services import get_stock_price, get_company_details, get_stock_data
from app.cli import test_cache
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

        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        data = get_stock_data("AAPL", start_date, end_date)
        assert len(data) == 1
        assert data[0]['close'] == 150.0
        assert data[0]['volume'] == 1000000

@pytest.mark.integration
def test_full_stock_workflow(app, test_cache):
    """Test the entire stock data workflow with caching."""
    with app.app_context():
        with patch('app.services.stock_services.polygon_client') as mock_polygon:
            # Mock company details response
            mock_details_response = Mock()
            mock_details_response.name = "Apple Inc."
            mock_details_response.market_cap = 2000000000000
            mock_details_response.primary_exchange = "NASDAQ"
            mock_details_response.description = "Technology company"
            mock_details_response.sector = "Technology"
            mock_details_response.industry = "Consumer Electronics"
            mock_details_response.url = "http://www.apple.com"
            mock_polygon.get_ticker_details.return_value = mock_details_response

            # Test company details
            details = get_company_details("AAPL")
            assert details is not None
            assert "name" in details
            assert details["name"] == "Apple Inc."
            assert details["sector"] == "Technology"
            assert details["industry"] == "Consumer Electronics"

@pytest.mark.integration
def test_cache_cli_command(app):
    """Test the cache CLI command."""
    runner = app.test_cli_runner()

    with patch('app.utils.cache_monitor.test_cache_functionality') as mock_test_cache:
        result = runner.invoke(test_cache, ['AAPL'])
        assert result.exit_code == 0
        mock_test_cache.assert_called_once_with('AAPL')