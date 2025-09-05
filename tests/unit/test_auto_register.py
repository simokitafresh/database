"""Tests for automatic symbol registration service."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.services.auto_register import (
    symbol_exists_in_db,
    insert_symbol,
    auto_register_symbol,
    batch_register_symbols
)


class TestSymbolExistsInDb:
    """Test cases for symbol_exists_in_db function."""

    @pytest.mark.asyncio
    async def test_symbol_exists(self):
        """Test when symbol exists in database."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_session.execute.return_value = mock_result

        result = await symbol_exists_in_db(mock_session, "AAPL")

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_symbol_not_exists(self):
        """Test when symbol doesn't exist in database."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_session.execute.return_value = mock_result

        result = await symbol_exists_in_db(mock_session, "NEWSTOCK")

        assert result is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_database_error(self):
        """Test handling of database errors."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute.side_effect = SQLAlchemyError("Database error")

        with pytest.raises(SQLAlchemyError):
            await symbol_exists_in_db(mock_session, "TEST")


class TestInsertSymbol:
    """Test cases for insert_symbol function."""

    @pytest.mark.asyncio
    async def test_successful_insertion(self):
        """Test successful symbol insertion."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("TEST",)  # Simulate successful insertion
        mock_session.execute.return_value = mock_result

        result = await insert_symbol(mock_session, "TEST")

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_symbol_already_exists_conflict(self):
        """Test insertion when symbol already exists (ON CONFLICT DO NOTHING)."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None  # No row returned due to conflict
        mock_session.execute.return_value = mock_result

        result = await insert_symbol(mock_session, "EXISTING")

        assert result is True  # Still success, just didn't insert
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_integrity_error(self):
        """Test handling of integrity errors."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute.side_effect = IntegrityError("statement", "params", "orig")

        result = await insert_symbol(mock_session, "TEST")

        assert result is False

    @pytest.mark.asyncio
    async def test_general_database_error(self):
        """Test handling of general database errors."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute.side_effect = SQLAlchemyError("General error")

        result = await insert_symbol(mock_session, "TEST")

        assert result is False


class TestAutoRegisterSymbol:
    """Test cases for auto_register_symbol function."""

    @pytest.mark.asyncio
    @patch('app.services.auto_register.normalize_symbol')
    @patch('app.services.auto_register.symbol_exists_in_db')
    async def test_symbol_already_exists(self, mock_exists, mock_normalize):
        """Test when symbol already exists in database."""
        mock_normalize.return_value = "AAPL"
        mock_exists.return_value = True
        mock_session = AsyncMock(spec=AsyncSession)

        result = await auto_register_symbol(mock_session, "aapl")

        assert result is True
        mock_normalize.assert_called_once_with("aapl")
        mock_exists.assert_called_once_with(mock_session, "AAPL")

    @pytest.mark.asyncio
    @patch('app.services.auto_register.validate_symbol_exists')
    @patch('app.services.auto_register.insert_symbol')
    @patch('app.services.auto_register.symbol_exists_in_db')
    @patch('app.services.auto_register.normalize_symbol')
    async def test_successful_registration(self, mock_normalize, mock_exists, mock_insert, mock_validate):
        """Test successful new symbol registration."""
        mock_normalize.return_value = "NEWSTOCK"
        mock_exists.return_value = False
        mock_validate.return_value = True
        mock_insert.return_value = True
        mock_session = AsyncMock(spec=AsyncSession)

        result = await auto_register_symbol(mock_session, "newstock")

        assert result is True
        mock_validate.assert_called_once_with("NEWSTOCK")
        mock_insert.assert_called_once_with(mock_session, "NEWSTOCK")

    @pytest.mark.asyncio
    @patch('app.services.auto_register.validate_symbol_exists')
    @patch('app.services.auto_register.symbol_exists_in_db')
    @patch('app.services.auto_register.normalize_symbol')
    async def test_symbol_not_in_yfinance(self, mock_normalize, mock_exists, mock_validate):
        """Test when symbol doesn't exist in Yahoo Finance."""
        mock_normalize.return_value = "INVALID"
        mock_exists.return_value = False
        mock_validate.return_value = False
        mock_session = AsyncMock(spec=AsyncSession)

        with pytest.raises(ValueError) as excinfo:
            await auto_register_symbol(mock_session, "invalid")

        assert "does not exist in Yahoo Finance" in str(excinfo.value)

    @pytest.mark.asyncio
    @patch('app.services.auto_register.validate_symbol_exists')
    @patch('app.services.auto_register.insert_symbol')
    @patch('app.services.auto_register.symbol_exists_in_db')
    @patch('app.services.auto_register.normalize_symbol')
    async def test_database_insertion_failure(self, mock_normalize, mock_exists, mock_insert, mock_validate):
        """Test when database insertion fails."""
        mock_normalize.return_value = "TEST"
        mock_exists.return_value = False
        mock_validate.return_value = True
        mock_insert.return_value = False  # Insertion failed
        mock_session = AsyncMock(spec=AsyncSession)

        with pytest.raises(RuntimeError) as excinfo:
            await auto_register_symbol(mock_session, "test")

        assert "Failed to insert" in str(excinfo.value)


class TestBatchRegisterSymbols:
    """Test cases for batch_register_symbols function."""

    @pytest.mark.asyncio
    @patch('app.services.auto_register.auto_register_symbol')
    async def test_all_successful(self, mock_auto_register):
        """Test batch registration with all symbols successful."""
        mock_auto_register.return_value = True
        mock_session = AsyncMock(spec=AsyncSession)
        symbols = ["AAPL", "MSFT", "GOOGL"]

        results = await batch_register_symbols(mock_session, symbols)

        assert len(results) == 3
        assert all(results.values())
        assert mock_auto_register.call_count == 3

    @pytest.mark.asyncio
    @patch('app.services.auto_register.auto_register_symbol')
    async def test_mixed_results(self, mock_auto_register):
        """Test batch registration with mixed success/failure."""
        def side_effect(session, symbol):
            if symbol == "INVALID":
                raise ValueError("Symbol doesn't exist")
            return True

        mock_auto_register.side_effect = side_effect
        mock_session = AsyncMock(spec=AsyncSession)
        symbols = ["AAPL", "INVALID", "MSFT"]

        results = await batch_register_symbols(mock_session, symbols)

        assert len(results) == 3
        assert results["AAPL"] is True
        assert results["INVALID"] is False
        assert results["MSFT"] is True

    @pytest.mark.asyncio
    @patch('app.services.auto_register.auto_register_symbol')
    async def test_empty_symbols_list(self, mock_auto_register):
        """Test batch registration with empty symbols list."""
        mock_session = AsyncMock(spec=AsyncSession)
        symbols = []

        results = await batch_register_symbols(mock_session, symbols)

        assert len(results) == 0
        mock_auto_register.assert_not_called()

    @pytest.mark.asyncio
    @patch('app.services.auto_register.auto_register_symbol')
    async def test_all_failures(self, mock_auto_register):
        """Test batch registration with all symbols failing."""
        mock_auto_register.side_effect = RuntimeError("Database error")
        mock_session = AsyncMock(spec=AsyncSession)
        symbols = ["TEST1", "TEST2"]

        results = await batch_register_symbols(mock_session, symbols)

        assert len(results) == 2
        assert all(not success for success in results.values())
        assert mock_auto_register.call_count == 2
