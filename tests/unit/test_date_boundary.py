import pytest
from datetime import date
from unittest.mock import patch, AsyncMock

from app.db.queries import ensure_coverage_with_auto_fetch


@pytest.mark.asyncio
async def test_date_boundary_conditions():
    """日付境界条件のテスト"""
    mock_session = AsyncMock()

    with patch('app.db.queries.find_earliest_available_date') as mock_find, \
         patch('app.db.queries.fetch_prices_df') as mock_fetch, \
         patch('app.db.queries._get_coverage') as mock_cov:
        mock_find.return_value = date(2004, 11, 18)
        mock_fetch.return_value = AsyncMock(empty=True)
        mock_cov.return_value = {}

        result = await ensure_coverage_with_auto_fetch(
            mock_session,
            ["GLD"],
            date(1990, 1, 1),
            date(2001, 1, 1),
            30
        )

        assert "GLD" in result["adjustments"]
        assert result["adjustments"]["GLD"]["status"] == "no_data_in_range"
