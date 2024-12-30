import pytest
from unittest.mock import Mock, patch
from app import create_app
from app.extensions import cache
from app.cli import test_cache
from flask.cli import ScriptInfo

@pytest.mark.integration
def test_full_stock_workflow(app, test_cache):
    """Test the entire stock data workflow with caching."""
    with app.app_context():
        with patch('app.services.stock_services.polygon_client') as mock_polygon:
            # Mock price response
            mock_price_response = Mock()
            mock_price_response.close = 150.0
            mock_polygon.get_daily_open_close_agg.return_value = mock_price_response

            # Mock company details response
            mock_details_response = Mock()
            mock_details_response.name = "Apple Inc."
            mock_details_response.market_cap = 2000000000000
            mock_details_response.primary_exchange = "NASDAQ"
            mock_details_response.description = "Technology company"
            mock_polygon.get_ticker_details.return_value = mock_details_response

            # Mock historical data response
            mock_agg = Mock()
            mock_agg.timestamp = 1609459200000  # 2021-01-01
            mock_agg.close = 150.0
            mock_agg.volume = 1000000
            mock_polygon.get_aggs.return_value = [mock_agg]

            # Test workflow
            from app.services.stock_services import (
                get_stock_price,
                get_company_details,
                get_stock_data
            )

            # First calls - should hit API
            price = get_stock_price("AAPL")
            assert price == 150.0

            details = get_company_details("AAPL")
            assert details["name"] == "Apple Inc."

            historical = get_stock_data("AAPL", "2021-01-01", "2021-01-31")
            assert len(historical) == 1
            assert historical[0]["close"] == 150.0

            # Second calls - should hit cache
            cached_price = get_stock_price("AAPL")
            assert cached_price == price

            cached_details = get_company_details("AAPL")
            assert cached_details == details

            cached_historical = get_stock_data("AAPL", "2021-01-01", "2021-01-31")
            assert cached_historical == historical

@pytest.mark.integration
def test_cache_cli_command():
    """Test the cache CLI command."""
    runner = app.test_cli_runner()

    with patch('app.utils.cache_monitor.test_cache_functionality') as mock_test_cache:
        result = runner.invoke(test_cache, ['AAPL'])
        assert result.exit_code == 0
        mock_test_cache.assert_called_once_with('AAPL')
