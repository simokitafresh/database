import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.auto_register import batch_register_symbols
from app.services.fetch_worker import process_fetch_job
from app.schemas.fetch_jobs import FetchJobProgress, FetchJobResult

class TestConcurrencyFixes(unittest.IsolatedAsyncioTestCase):
    async def test_batch_register_symbols_three_phase(self):
        """Verify that batch_register_symbols uses optimized three-phase approach."""
        mock_session = AsyncMock()
        symbols = ['SYM1', 'SYM2', 'SYM3']
        
        # Mock get_existing_symbols to return empty (no existing symbols)
        with patch('app.services.auto_register.get_existing_symbols', new_callable=AsyncMock) as mock_existing:
            mock_existing.return_value = set()
            
            # Mock validate_symbol_exists_async to return True for all
            with patch('app.services.auto_register.validate_symbol_exists_async', new_callable=AsyncMock) as mock_validate:
                mock_validate.return_value = True
                
                # Mock insert_symbols_batch to return success for all
                with patch('app.services.auto_register.insert_symbols_batch', new_callable=AsyncMock) as mock_insert:
                    mock_insert.return_value = {sym: True for sym in symbols}
                    
                    result = await batch_register_symbols(mock_session, symbols)
                    
                    # Verify all phases were called
                    mock_existing.assert_called_once()
                    self.assertEqual(mock_validate.call_count, 3)  # Called for each symbol
                    mock_insert.assert_called_once()
                    
                    # Verify result format: Dict[str, Tuple[bool, Optional[str]]]
                    for sym in symbols:
                        self.assertIn(sym, result)
                        success, error_type = result[sym]
                        self.assertTrue(success)
                        self.assertIsNone(error_type)
    
    async def test_batch_register_skips_existing_symbols(self):
        """Verify that existing symbols skip validation and insertion."""
        mock_session = AsyncMock()
        symbols = ['SYM1', 'SYM2', 'SYM3']
        
        # Mock get_existing_symbols to return all as existing
        with patch('app.services.auto_register.get_existing_symbols', new_callable=AsyncMock) as mock_existing:
            mock_existing.return_value = {'SYM1', 'SYM2', 'SYM3'}
            
            with patch('app.services.auto_register.validate_symbol_exists_async', new_callable=AsyncMock) as mock_validate:
                with patch('app.services.auto_register.insert_symbols_batch', new_callable=AsyncMock) as mock_insert:
                    
                    result = await batch_register_symbols(mock_session, symbols)
                    
                    # Verify validation and insertion were NOT called
                    mock_validate.assert_not_called()
                    mock_insert.assert_not_called()
                    
                    # All should be successful
                    for sym in symbols:
                        success, error_type = result[sym]
                        self.assertTrue(success)
                        self.assertIsNone(error_type)

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
