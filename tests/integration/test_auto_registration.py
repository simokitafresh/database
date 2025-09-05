"""Integration tests for automatic symbol registration functionality."""

import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

from app.main import app
from app.core.config import get_settings


class TestAutoRegistrationIntegration:
    """Integration tests for the complete auto-registration workflow."""

    def setup_method(self):
        """Setup for each test method."""
        self.client = TestClient(app)

    @patch('app.core.config.get_settings')
    @patch('app.api.v1.prices.auto_register_symbol')
    @patch('app.api.v1.prices.ensure_coverage')
    def test_prices_endpoint_with_auto_registration_enabled(
        self, mock_ensure_coverage, mock_auto_register, mock_settings
    ):
        """Test prices endpoint with auto-registration enabled."""
        # Setup mocks
        mock_settings_obj = MagicMock()
        mock_settings_obj.ENABLE_AUTO_REGISTRATION = True
        mock_settings.return_value = mock_settings_obj
        
        mock_auto_register.return_value = True
        mock_ensure_coverage.return_value = None

        # Test request
        response = self.client.post("/api/v1/prices/ensure-coverage", json={
            "symbols": ["NEWSTOCK"],
            "days": 30
        })

        # Assertions
        assert response.status_code in [200, 202]  # Success or accepted
        mock_auto_register.assert_called_once()
        mock_ensure_coverage.assert_called_once()

    @patch('app.core.config.get_settings')
    @patch('app.api.v1.prices.ensure_coverage')
    def test_prices_endpoint_with_auto_registration_disabled(
        self, mock_ensure_coverage, mock_settings
    ):
        """Test prices endpoint with auto-registration disabled."""
        # Setup mocks
        mock_settings_obj = MagicMock()
        mock_settings_obj.ENABLE_AUTO_REGISTRATION = False
        mock_settings.return_value = mock_settings_obj
        
        mock_ensure_coverage.return_value = None

        # Test request
        response = self.client.post("/api/v1/prices/ensure-coverage", json={
            "symbols": ["NEWSTOCK"],
            "days": 30
        })

        # Assertions - should proceed without auto-registration
        assert response.status_code in [200, 202]
        mock_ensure_coverage.assert_called_once()

    @patch('app.core.config.get_settings')
    @patch('app.api.v1.prices.auto_register_symbol')
    def test_auto_registration_failure_handling(
        self, mock_auto_register, mock_settings
    ):
        """Test handling of auto-registration failures."""
        # Setup mocks
        mock_settings_obj = MagicMock()
        mock_settings_obj.ENABLE_AUTO_REGISTRATION = True
        mock_settings.return_value = mock_settings_obj
        
        # Simulate auto-registration failure
        mock_auto_register.side_effect = ValueError("Symbol does not exist in Yahoo Finance")

        # Test request
        response = self.client.post("/api/v1/prices/ensure-coverage", json={
            "symbols": ["INVALID_SYMBOL"],
            "days": 30
        })

        # Assertions - should return error
        assert response.status_code == 400
        response_data = response.json()
        assert "SYMBOL_NOT_EXISTS" in str(response_data)

    @patch('app.core.config.get_settings')
    @patch('app.api.v1.prices.auto_register_symbol')
    def test_database_registration_failure_handling(
        self, mock_auto_register, mock_settings
    ):
        """Test handling of database registration failures."""
        # Setup mocks
        mock_settings_obj = MagicMock()
        mock_settings_obj.ENABLE_AUTO_REGISTRATION = True
        mock_settings.return_value = mock_settings_obj
        
        # Simulate database insertion failure
        mock_auto_register.side_effect = RuntimeError("Failed to insert symbol into database")

        # Test request
        response = self.client.post("/api/v1/prices/ensure-coverage", json={
            "symbols": ["TEST_SYMBOL"],
            "days": 30
        })

        # Assertions - should return error
        assert response.status_code == 500
        response_data = response.json()
        assert "SYMBOL_REGISTRATION_FAILED" in str(response_data)

    @patch('app.core.config.get_settings')
    @patch('app.api.v1.prices.batch_register_symbols')
    @patch('app.api.v1.prices.ensure_coverage')
    def test_batch_registration_mixed_results(
        self, mock_ensure_coverage, mock_batch_register, mock_settings
    ):
        """Test batch registration with mixed success/failure results."""
        # Setup mocks
        mock_settings_obj = MagicMock()
        mock_settings_obj.ENABLE_AUTO_REGISTRATION = True
        mock_settings.return_value = mock_settings_obj
        
        # Simulate mixed batch results
        mock_batch_register.return_value = {
            "AAPL": True,
            "INVALID": False,
            "MSFT": True
        }
        mock_ensure_coverage.return_value = None

        # Test request with multiple symbols
        response = self.client.post("/api/v1/prices/ensure-coverage", json={
            "symbols": ["AAPL", "INVALID", "MSFT"],
            "days": 30
        })

        # Should proceed with valid symbols only
        assert response.status_code in [200, 202]
        mock_batch_register.assert_called_once()
        mock_ensure_coverage.assert_called_once()

    def test_configuration_settings(self):
        """Test that configuration settings are properly loaded."""
        settings = get_settings()
        
        # Check that auto-registration settings exist
        assert hasattr(settings, 'ENABLE_AUTO_REGISTRATION')
        assert hasattr(settings, 'AUTO_REGISTER_TIMEOUT')
        assert hasattr(settings, 'YF_VALIDATE_TIMEOUT')
        
        # Check default values
        assert isinstance(settings.ENABLE_AUTO_REGISTRATION, bool)
        assert isinstance(settings.AUTO_REGISTER_TIMEOUT, int)
        assert isinstance(settings.YF_VALIDATE_TIMEOUT, int)


class TestEndToEndWorkflow:
    """End-to-end tests for the complete auto-registration workflow."""

    @pytest.mark.integration
    @patch('app.services.symbol_validator.yf.Ticker')
    @patch('app.services.auto_register.symbol_exists_in_db')
    @patch('app.services.auto_register.insert_symbol')
    def test_complete_workflow_new_symbol(
        self, mock_insert, mock_exists, mock_ticker
    ):
        """Test complete workflow for a new symbol registration."""
        # Mock Yahoo Finance validation
        mock_ticker_instance = MagicMock()
        mock_ticker_instance.info = {'symbol': 'TEST', 'shortName': 'Test Company'}
        mock_ticker.return_value = mock_ticker_instance
        
        # Mock database operations
        mock_exists.return_value = False  # Symbol doesn't exist
        mock_insert.return_value = True   # Successful insertion

        client = TestClient(app)
        
        # Test the complete workflow
        with patch('app.core.config.get_settings') as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.ENABLE_AUTO_REGISTRATION = True
            mock_settings_obj.AUTO_REGISTER_TIMEOUT = 15
            mock_settings_obj.YF_VALIDATE_TIMEOUT = 10
            mock_settings.return_value = mock_settings_obj

            response = client.post("/api/v1/prices/ensure-coverage", json={
                "symbols": ["TEST"],
                "days": 30
            })

            # Should successfully process the request
            assert response.status_code in [200, 202]

    @pytest.mark.integration
    def test_workflow_with_existing_symbol(self):
        """Test workflow when symbol already exists in database."""
        client = TestClient(app)
        
        with patch('app.core.config.get_settings') as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.ENABLE_AUTO_REGISTRATION = True
            mock_settings.return_value = mock_settings_obj
            
            with patch('app.services.auto_register.symbol_exists_in_db', return_value=True):
                response = client.post("/api/v1/prices/ensure-coverage", json={
                    "symbols": ["AAPL"],  # Assume AAPL exists
                    "days": 30
                })

                # Should proceed without registration
                assert response.status_code in [200, 202]

    @pytest.mark.integration
    def test_error_propagation(self):
        """Test that errors are properly propagated through the system."""
        client = TestClient(app)
        
        with patch('app.core.config.get_settings') as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.ENABLE_AUTO_REGISTRATION = True
            mock_settings.return_value = mock_settings_obj
            
            # Simulate network error during validation
            with patch('app.services.symbol_validator.validate_symbol_exists') as mock_validate:
                mock_validate.side_effect = Exception("Network error")
                
                response = client.post("/api/v1/prices/ensure-coverage", json={
                    "symbols": ["TEST"],
                    "days": 30
                })

                # Should handle the error gracefully
                assert response.status_code >= 400


@pytest.mark.asyncio
class TestAsyncWorkflow:
    """Test async operations in the auto-registration workflow."""

    async def test_concurrent_registrations(self):
        """Test handling of concurrent symbol registrations."""
        from app.services.auto_register import batch_register_symbols
        
        # Mock session
        mock_session = AsyncMock()
        
        with patch('app.services.auto_register.auto_register_symbol') as mock_register:
            # Simulate some delay to test concurrency
            async def delayed_register(session, symbol):
                await asyncio.sleep(0.1)
                return True
            
            mock_register.side_effect = delayed_register
            
            symbols = ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5"]
            
            # Time the batch operation
            import time
            start_time = time.time()
            results = await batch_register_symbols(mock_session, symbols)
            end_time = time.time()
            
            # Should complete all registrations
            assert len(results) == 5
            assert all(results.values())
            
            # Should take advantage of concurrent execution
            # (less than sequential time)
            assert end_time - start_time < 0.5  # Much less than 5 * 0.1
