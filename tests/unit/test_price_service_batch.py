"""Test for N+1 query optimization in PriceService.

This test verifies that get_prices uses batch query instead of N+1 pattern.
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, patch, MagicMock
from typing import List


class TestPriceServiceQueryOptimization:
    """Test that PriceService uses batch queries efficiently."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_get_prices_uses_batch_query_not_n_plus_1(self, mock_session):
        """
        GIVEN: 5 uncached symbols to retrieve
        WHEN: get_prices is called
        THEN: get_prices_resolved should be called ONCE with all symbols (batch)
              NOT 5 times with 1 symbol each (N+1)
        """
        from app.services.price_service import PriceService
        
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
        date_from = date(2025, 1, 1)
        date_to = date(2025, 12, 31)
        
        # Mock the queries module
        with patch("app.services.price_service.queries") as mock_queries, \
             patch("app.services.price_service.settings") as mock_settings, \
             patch("app.services.price_service.ensure_symbols_registered", new_callable=AsyncMock):
            
            # Setup mock settings
            mock_settings.ENABLE_AUTO_REGISTRATION = False
            mock_settings.ENABLE_CACHE = False
            mock_settings.YF_REFETCH_DAYS = 7
            
            # Mock get_prices_resolved to return sample data
            mock_queries.get_prices_resolved = AsyncMock(return_value=[
                {"symbol": s, "date": date_from, "open": 100, "high": 105, 
                 "low": 95, "close": 102, "volume": 1000000, 
                 "source": "test", "last_updated": None, "source_symbol": None}
                for s in symbols
            ])
            mock_queries.ensure_coverage = AsyncMock()
            
            # Execute
            service = PriceService(mock_session)
            await service.get_prices(symbols, date_from, date_to, auto_fetch=False)
            
            # ASSERT: get_prices_resolved should be called ONCE (batch)
            # NOT 5 times (N+1)
            call_count = mock_queries.get_prices_resolved.call_count
            
            assert call_count == 1, (
                f"N+1 detected! get_prices_resolved was called {call_count} times "
                f"instead of 1. This means each symbol is queried separately."
            )
            
            # Verify the single call included all symbols
            call_args = mock_queries.get_prices_resolved.call_args
            called_symbols = call_args.kwargs.get("symbols", call_args.args[1] if len(call_args.args) > 1 else None)
            
            assert set(called_symbols) == set(symbols), (
                f"Batch query should include all symbols. "
                f"Expected: {symbols}, Got: {called_symbols}"
            )

    @pytest.mark.asyncio
    async def test_get_prices_batch_query_count(self, mock_session):
        """
        Verify query count stays constant regardless of symbol count.
        """
        from app.services.price_service import PriceService
        
        date_from = date(2025, 1, 1)
        date_to = date(2025, 12, 31)
        
        with patch("app.services.price_service.queries") as mock_queries, \
             patch("app.services.price_service.settings") as mock_settings, \
             patch("app.services.price_service.ensure_symbols_registered", new_callable=AsyncMock):
            
            mock_settings.ENABLE_AUTO_REGISTRATION = False
            mock_settings.ENABLE_CACHE = False
            mock_settings.YF_REFETCH_DAYS = 7
            
            mock_queries.get_prices_resolved = AsyncMock(return_value=[])
            mock_queries.ensure_coverage = AsyncMock()
            
            service = PriceService(mock_session)
            
            # Test with different symbol counts
            for num_symbols in [1, 5, 10, 20]:
                mock_queries.get_prices_resolved.reset_mock()
                symbols = [f"SYM{i}" for i in range(num_symbols)]
                
                await service.get_prices(symbols, date_from, date_to, auto_fetch=False)
                
                call_count = mock_queries.get_prices_resolved.call_count
                assert call_count == 1, (
                    f"With {num_symbols} symbols, expected 1 query but got {call_count}. "
                    f"Query count should be O(1), not O(N)."
                )
