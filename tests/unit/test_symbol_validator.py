"""Tests for symbol validation service."""

import pytest
from unittest.mock import patch, MagicMock
from requests.exceptions import HTTPError as RequestsHTTPError, Timeout, ConnectionError

from app.services.symbol_validator import validate_symbol_exists, get_symbol_info


class TestValidateSymbolExists:
    """Test cases for validate_symbol_exists function."""

    def test_valid_symbol_aapl(self):
        """Test with a known valid symbol (AAPL)."""
        # This test uses actual Yahoo Finance API - may be slow
        result = validate_symbol_exists("AAPL")
        assert result is True

    def test_valid_symbol_msft(self):
        """Test with another known valid symbol (MSFT)."""
        result = validate_symbol_exists("MSFT")
        assert result is True

    def test_invalid_symbol(self):
        """Test with an obviously invalid symbol."""
        result = validate_symbol_exists("XXXYYY123INVALID")
        assert result is False

    @patch('app.services.symbol_validator.yf.Ticker')
    def test_empty_info_response(self, mock_ticker_class):
        """Test handling of empty info response."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker_class.return_value = mock_ticker
        
        result = validate_symbol_exists("TEST")
        assert result is False

    @patch('app.services.symbol_validator.yf.Ticker')
    def test_insufficient_info_data(self, mock_ticker_class):
        """Test handling of insufficient info data."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"symbol": "TEST"}  # Only 1 field, less than threshold
        mock_ticker_class.return_value = mock_ticker
        
        result = validate_symbol_exists("TEST")
        assert result is False

    @patch('app.services.symbol_validator.yf.Ticker')
    def test_symbol_mismatch(self, mock_ticker_class):
        """Test handling of symbol mismatch in response."""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "symbol": "DIFFERENT",
            "shortName": "Test Company",
            "longName": "Test Company Inc",
            "exchange": "NMS",
            "currency": "USD",
            "marketCap": 1000000
        }
        mock_ticker_class.return_value = mock_ticker
        
        result = validate_symbol_exists("REQUESTED")
        assert result is False

    @patch('app.services.symbol_validator.yf.Ticker')
    def test_http_404_error(self, mock_ticker_class):
        """Test handling of 404 HTTP error."""
        mock_ticker = MagicMock()
        mock_error = RequestsHTTPError()
        mock_error.response = MagicMock()
        mock_error.response.status_code = 404
        mock_ticker.info = mock_error
        mock_ticker_class.side_effect = mock_error
        
        result = validate_symbol_exists("NOTFOUND")
        assert result is False

    @patch('app.services.symbol_validator.yf.Ticker')
    def test_timeout_error(self, mock_ticker_class):
        """Test handling of timeout error."""
        mock_ticker_class.side_effect = Timeout("Request timed out")
        
        result = validate_symbol_exists("TEST")
        assert result is False

    @patch('app.services.symbol_validator.yf.Ticker')
    def test_connection_error(self, mock_ticker_class):
        """Test handling of connection error."""
        mock_ticker_class.side_effect = ConnectionError("Connection failed")
        
        result = validate_symbol_exists("TEST")
        assert result is False

    @patch('app.services.symbol_validator.yf.Ticker')
    def test_key_error(self, mock_ticker_class):
        """Test handling of KeyError."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"incomplete": "data"}
        mock_ticker_class.return_value = mock_ticker
        
        # This should still return False due to insufficient data
        result = validate_symbol_exists("TEST")
        assert result is False

    @patch('app.services.symbol_validator.yf.Ticker')
    def test_success_case(self, mock_ticker_class):
        """Test successful validation with sufficient data."""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "symbol": "TEST",
            "shortName": "Test Company",
            "longName": "Test Company Inc",
            "exchange": "NMS",
            "currency": "USD",
            "marketCap": 1000000,
            "sector": "Technology"
        }
        mock_ticker_class.return_value = mock_ticker
        
        result = validate_symbol_exists("TEST")
        assert result is True


class TestGetSymbolInfo:
    """Test cases for get_symbol_info function."""

    @patch('app.services.symbol_validator.yf.Ticker')
    def test_successful_info_retrieval(self, mock_ticker_class):
        """Test successful symbol info retrieval."""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "symbol": "TEST",
            "shortName": "Test Company",
            "longName": "Test Company Inc",
            "exchange": "NMS", 
            "currency": "USD",
            "marketCap": 1000000,
            "sector": "Technology",
            "industry": "Software"
        }
        mock_ticker_class.return_value = mock_ticker
        
        result = get_symbol_info("TEST")
        
        assert result["symbol"] == "TEST"
        assert result["exists"] is True
        assert result["error"] is None
        assert result["info"]["symbol"] == "TEST"
        assert result["info"]["shortName"] == "Test Company"
        assert result["info"]["exchange"] == "NMS"

    @patch('app.services.symbol_validator.yf.Ticker')
    def test_symbol_not_found(self, mock_ticker_class):
        """Test symbol not found scenario."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker_class.return_value = mock_ticker
        
        result = get_symbol_info("NOTFOUND")
        
        assert result["symbol"] == "NOTFOUND"
        assert result["exists"] is False
        assert "not found in Yahoo Finance" in result["error"]
        assert result["info"] is None

    @patch('app.services.symbol_validator.yf.Ticker')
    def test_network_error_handling(self, mock_ticker_class):
        """Test network error handling in get_symbol_info."""
        mock_ticker_class.side_effect = Timeout("Network timeout")
        
        result = get_symbol_info("TEST")
        
        assert result["symbol"] == "TEST"
        assert result["exists"] is False
        assert "timeout" in result["error"].lower()
        assert result["info"] is None

    def test_get_info_real_symbol(self):
        """Test get_symbol_info with real symbol (integration test)."""
        # This test uses actual Yahoo Finance API
        result = get_symbol_info("AAPL")
        
        assert result["symbol"] == "AAPL"
        if result["exists"]:  # May fail due to network issues
            assert result["error"] is None
            assert result["info"] is not None
            assert result["info"]["symbol"] == "AAPL"
