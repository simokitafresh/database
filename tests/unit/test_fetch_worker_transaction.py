import pytest
from unittest.mock import patch, AsyncMock
from datetime import date

from app.services.fetch_worker import process_fetch_job, FetchJobResult


@pytest.mark.asyncio
async def test_no_nested_transaction_error():
    """トランザクションエラーが発生しないことを確認"""
    with patch('app.services.fetch_jobs.update_job_status', new_callable=AsyncMock) as mock_update, \
         patch('app.services.fetch_jobs.update_job_progress', new_callable=AsyncMock), \
         patch('app.services.fetch_jobs.save_job_results', new_callable=AsyncMock):
        with patch('app.services.fetch_worker.create_engine_and_sessionmaker') as mock_engine, \
             patch('app.services.fetch_worker.fetch_symbol_data', new_callable=AsyncMock) as mock_fetch:
            mock_session = AsyncMock()
            session_ctx = AsyncMock()
            session_ctx.__aenter__.return_value = mock_session
            mock_engine.return_value = (None, lambda: session_ctx)
            mock_fetch.return_value = FetchJobResult(
                symbol="AAPL", status="success", rows_fetched=1, date_from=date(2024,1,1), date_to=date(2024,1,31), error=None
            )

            await process_fetch_job(
                "test-job-001",
                ["AAPL"],
                date(2024, 1, 1),
                date(2024, 1, 31)
            )
