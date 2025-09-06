import logging
import pytest
from unittest.mock import patch, MagicMock
from datetime import date

from app.services.fetcher import fetch_prices
from app.core.config import settings


def test_no_yfinance_warning(caplog):
    """YFinance警告が出力されないことを確認"""
    with patch('yfinance.download') as mock_download:
        mock_download.return_value = MagicMock(empty=False, columns=["Open","High","Low","Close","Volume"])

        with caplog.at_level(logging.WARNING):
            fetch_prices("AAPL", date(2024, 1, 1), date(2024, 1, 31), settings=settings)

        assert "auto_adjust" not in caplog.text
        call_kwargs = mock_download.call_args.kwargs
        assert "auto_adjust" in call_kwargs
        assert call_kwargs["auto_adjust"] is True
