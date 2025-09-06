import pytest
from unittest.mock import patch, AsyncMock
from datetime import date


@pytest.mark.asyncio
async def test_no_nested_transaction_error():
    """トランザクションエラーが発生しないことを確認"""
    from app.services.fetch_worker import process_fetch_job, FetchJobResult

    with patch('app.services.fetch_worker.update_job_status') as mock_update:
        mock_update.return_value = None
        with patch('app.db.engine.create_engine_and_sessionmaker') as engine_patch:
            with patch('app.services.fetch_worker.create_engine_and_sessionmaker', engine_patch), \
                 patch('app.services.fetch_worker.fetch_symbol_data', AsyncMock()) as mock_fetch:
                mock_session = AsyncMock()
                mock_session.in_transaction.return_value = False
                session_ctx = AsyncMock()
                session_ctx.__aenter__.return_value = mock_session
                engine_patch.return_value = (None, lambda: session_ctx)
                mock_fetch.return_value = FetchJobResult(
                    symbol="AAPL", status="success", rows_fetched=1, date_from=date(2024,1,1), date_to=date(2024,1,31), error=None
                )

                await process_fetch_job(
                    "test-job-001",
                    ["AAPL"],
                    date(2024, 1, 1),
                    date(2024, 1, 31)
                )
                assert mock_update.called
