import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from app.cli import test_cache
from app.models import Stock
from app.extensions import db

@pytest.mark.integration
def test_full_stock_workflow(app, test_cache):
    """Test the entire stock data workflow with caching."""
    with app.app_context():
        with patch('app.services.stock_services.polygon_client') as mock_polygon:
            # Set up price response
            mock_price_response = Mock()
            mock_price_response.close = 150.0
            mock_price_response.date = datetime.now().strftime('%Y-%m-%d')
            mock_polygon.get_daily_open_close_agg.return_value = mock_price_response

            # Set up company details response
            mock_details_response = Mock()
            mock_details_response.name = "Apple Inc."
            mock_details_response.market_cap = 2000000000000
            mock_details_response.primary_exchange = "NASDAQ"
            mock_details_response.description = "Technology company"
            mock_details_response.sector = "Technology"
            mock_details_response.industry = "Consumer Electronics"
            mock_details_response.url = "http://www.apple.com"
            mock_polygon.get_ticker_details.return_value = mock_details_response

            # Set up historical data response
            mock_agg = Mock()
            mock_agg.t = int(datetime.now().timestamp() * 1000)
            mock_agg.c = 150.0
            mock_agg.v = 1000000
            mock_agg.o = 149.0
            mock_agg.h = 151.0
            mock_agg.l = 148.0
            mock_response = Mock()
            mock_response.results = [mock_agg]
            mock_polygon.get_aggs.return_value = mock_response

            # Import services inside context
            from app.services.stock_services import (
                get_stock_price,
                get_company_details,
                get_stock_data,
                create_stock,
                get_stock_by_symbol,
                delete_stock
            )

            # Test price retrieval
            price = get_stock_price("AAPL")
            assert price == 150.0

            # Test company details
            details = get_company_details("AAPL")
            assert details is not None
            assert details["name"] == "Apple Inc."
            assert details["sector"] == "Technology"
            assert details["industry"] == "Consumer Electronics"

            # Test historical data
            from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            to_date = datetime.now().strftime('%Y-%m-%d')
            historical = get_stock_data("AAPL", from_date, to_date)
            assert len(historical) == 1
            assert historical[0]["close"] == 150.0
            assert historical[0]["volume"] == 1000000

            # Test database operations
            # Create stock
            stock = create_stock("AAPL", "Apple Inc.")
            assert stock is not None
            assert stock.symbol == "AAPL"
            assert stock.name == "Apple Inc."

            # Get stock
            retrieved_stock = get_stock_by_symbol("AAPL")
            assert retrieved_stock is not None
            assert retrieved_stock.symbol == "AAPL"

            # Delete stock
            assert delete_stock("AAPL") is True
            assert get_stock_by_symbol("AAPL") is None

@pytest.mark.integration
def test_error_handling(app, test_cache):
    """Test error handling in stock services."""
    with app.app_context():
        with patch('app.services.stock_services.polygon_client') as mock_polygon:
            # Simulate API errors
            mock_polygon.get_daily_open_close_agg.side_effect = Exception("API Error")
            mock_polygon.get_ticker_details.side_effect = Exception("API Error")
            mock_polygon.get_aggs.side_effect = Exception("API Error")

            from app.services.stock_services import (
                get_stock_price,
                get_company_details,
                get_stock_data
            )

            # Test error handling for each service
            assert get_stock_price("AAPL") is None
            assert get_company_details("AAPL") == {}
            assert get_stock_data("AAPL", "2024-01-01", "2024-01-31") == []

@pytest.mark.integration
def test_cache_cli_command(app):
    """Test the cache CLI command."""
    runner = app.test_cli_runner()

    with patch('app.utils.cache_monitor.test_cache_functionality') as mock_test_cache:
        result = runner.invoke(test_cache, ['AAPL'])
        assert result.exit_code == 0
        mock_test_cache.assert_called_once_with('AAPL')

@pytest.mark.integration
def test_database_constraints(app):
    """Test database constraints and integrity."""
    with app.app_context():
        # Test duplicate stock creation
        stock1 = Stock(symbol="AAPL", name="Apple Inc.")
        stock2 = Stock(symbol="AAPL", name="Apple Inc.")

        db.session.add(stock1)
        db.session.commit()

        db.session.add(stock2)
        with pytest.raises(Exception):
            db.session.commit()

        db.session.rollback()

        # Clean up
        Stock.query.filter_by(symbol="AAPL").delete()
        db.session.commit()