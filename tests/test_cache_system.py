import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from types import SimpleNamespace
from app.utils.cache_manager import StockCache
from app.services import stock_services
from app.services.stock_services import get_stock_price, get_company_details, get_stock_data
from flask_caching import Cache
from frontend import dashboard

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


def test_company_details_keeps_full_trimmed_description_and_versions_cache():
    description = "  " + ("A complete company description. " * 12) + "  "
    ticker_details = SimpleNamespace(
        name="Example Corp.",
        description=description,
        market_cap=1_000_000,
        primary_exchange="XNAS",
    )

    with patch.object(stock_services.StockCache, "get_cached_data", return_value=None) as get_cached:
        with patch.object(stock_services.StockCache, "set_cached_data") as set_cached:
            with patch.object(stock_services, "_get_client") as get_client:
                get_client.return_value.get_ticker_details.return_value = ticker_details

                details = stock_services.get_company_details("EXMP")

    assert details["description"] == description.strip()
    assert len(details["description"]) > 150
    get_cached.assert_called_once_with(
        "EXMP", "details", version=stock_services.DETAILS_CACHE_VERSION
    )
    set_cached.assert_called_once_with(
        "EXMP", "details", details, version=stock_services.DETAILS_CACHE_VERSION
    )


def test_about_section_starts_as_a_two_line_preview_with_accessible_toggle():
    section = dashboard.create_about_section("EXMP", "A complete company description.")
    _, description, toggle = section.children

    assert description.id == {"type": "about-text", "index": "EXMP"}
    assert description.className == dashboard.ABOUT_TEXT_COLLAPSED_CLASS
    assert description.children == "A complete company description."
    assert toggle.id == {"type": "about-toggle", "index": "EXMP"}
    assert toggle.children == "Show full description"
    assert toggle.to_plotly_json()["props"]["aria-expanded"] == "false"


def test_about_display_state_expands_and_collapses_again():
    assert dashboard.about_display_state(expanded=True) == (
        dashboard.ABOUT_TEXT_EXPANDED_CLASS,
        "Show less",
        "true",
    )
    assert dashboard.about_display_state(expanded=False) == (
        dashboard.ABOUT_TEXT_COLLAPSED_CLASS,
        "Show full description",
        "false",
    )

@patch('app.services.stock_services.polygon_client')
def test_historical_data_handling(mock_polygon, app, test_cache):
    """Test historical data retrieval and caching."""
    with app.app_context():
        mock_result = Mock()
        mock_result.timestamp = int(datetime.now().timestamp() * 1000)
        mock_result.open = 149.0
        mock_result.high = 151.0
        mock_result.low = 148.0
        mock_result.close = 150.0
        mock_result.volume = 1000000

        mock_polygon.get_aggs.return_value = [mock_result]

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

