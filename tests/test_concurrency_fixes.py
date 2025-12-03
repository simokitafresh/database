import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.auto_register import batch_register_symbols
from app.services.fetch_worker import process_fetch_job
from app.schemas.fetch_jobs import FetchJobProgress, FetchJobResult

class TestConcurrencyFixes(unittest.IsolatedAsyncioTestCase):
    async def test_batch_register_symbols_sequential(self):
        """Verify that batch_register_symbols processes symbols sequentially."""
        mock_session = AsyncMock()
        symbols = ['SYM1', 'SYM2', 'SYM3']
        
        # Mock auto_register_symbol to track execution order/concurrency
        execution_log = []
        
        async def mock_register(session, symbol):
            execution_log.append(f"start_{symbol}")
            await asyncio.sleep(0.01) # Simulate work
            execution_log.append(f"end_{symbol}")
            return True
            
        with patch('app.services.auto_register.auto_register_symbol', side_effect=mock_register) as mock_reg:
            result = await batch_register_symbols(mock_session, symbols)
            
            # Verify result format changed to Dict[str, Tuple[bool, Optional[str]]]
            for sym in symbols:
                self.assertIn(sym, result)
                success, error_type = result[sym]
                self.assertTrue(success)
                self.assertIsNone(error_type)
            
            # Check if execution was sequential
            # If sequential: start_1, end_1, start_2, end_2...
            # If concurrent: start_1, start_2, end_1... (mixed)
            
            self.assertEqual(len(execution_log), 6)
            for i in range(0, 6, 2):
                self.assertTrue(execution_log[i].startswith("start_"))
                self.assertTrue(execution_log[i+1].startswith("end_"))
                self.assertEqual(execution_log[i].split("_")[1], execution_log[i+1].split("_")[1])

    async def test_fetch_worker_locking(self):
        """Verify that process_fetch_job uses a lock for progress updates."""
        # This is harder to test directly without inspecting the lock, 
        # but we can verify that update_job_progress is not called concurrently.
        
        mock_session_cls = MagicMock()
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session
        
        # Mock create_engine_and_sessionmaker to return our mock session
        with patch('app.services.fetch_worker.create_engine_and_sessionmaker', return_value=(None, mock_session_cls)):
            with patch('app.services.fetch_worker.update_job_status', new_callable=AsyncMock):
                with patch('app.services.fetch_worker.save_job_results', new_callable=AsyncMock):
                    with patch('app.services.fetch_worker.fetch_symbol_data', new_callable=AsyncMock) as mock_fetch:
                        
                        # Mock fetch to be fast
                        mock_fetch.return_value = FetchJobResult(symbol="TEST", status="success", rows_fetched=10)
                        
                        # Mock update_job_progress to check for concurrency
                        active_updates = 0
                        max_concurrent_updates = 0
                        
                        async def mock_update_progress(session, job_id, progress):
                            nonlocal active_updates, max_concurrent_updates
                            active_updates += 1
                            max_concurrent_updates = max(max_concurrent_updates, active_updates)
                            await asyncio.sleep(0.01) # Simulate DB latency
                            active_updates -= 1
                            
                        with patch('app.services.fetch_worker.update_job_progress', side_effect=mock_update_progress):
                            # Run with high concurrency to trigger potential race conditions if lock is missing
                            symbols = [f"SYM{i}" for i in range(10)]
                            await process_fetch_job("job_id", symbols, "2023-01-01", "2023-01-02", max_concurrency=5)
                            
                            # If locked correctly, active_updates should never exceed 1
                            self.assertEqual(max_concurrent_updates, 1, "update_job_progress was called concurrently!")

if __name__ == '__main__':
    unittest.main()
