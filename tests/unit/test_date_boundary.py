import pytest
from datetime import date
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_date_boundary_conditions():
    """日付境界条件のテスト"""
    from app.db.queries import ensure_coverage_unified

    mock_session = AsyncMock()

    with patch('app.db.queries.binary_search_yf_start_date') as mock_search, \
         patch('app.db.queries._get_coverage') as mock_cov:
        mock_search.return_value = date(2004, 11, 18)
        mock_cov.return_value = {}

        result = await ensure_coverage_unified(
            mock_session,
            ["GLD"],
            date(1990, 1, 1),
            date(2001, 1, 1),
            30
        )

        assert "GLD" in result["adjustments"]
        assert result["adjustments"]["GLD"]["status"] == "no_data_in_range"
