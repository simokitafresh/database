"""Tests for TimingLogger utility."""

import pytest
import logging
import asyncio
from unittest.mock import MagicMock, patch


class TestTimingLogger:
    """Test TimingLogger context manager."""

    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger."""
        logger = MagicMock()
        # Configure log method to behave like real logger
        logger.log = MagicMock()
        logger.info = MagicMock()
        logger.warning = MagicMock()
        return logger

    @pytest.mark.asyncio
    async def test_timing_logger_logs_elapsed_time(self, mock_logger):
        """
        GIVEN: A TimingLogger with a name and logger
        WHEN: Used as async context manager
        THEN: Should log elapsed time with [TIMING] prefix
        """
        from app.utils.timing import TimingLogger
        
        async with TimingLogger("test_operation", mock_logger):
            await asyncio.sleep(0.01)  # 10ms
        
        # Verify logger.info was called
        assert mock_logger.info.called
        log_message = mock_logger.info.call_args[0][0]
        
        # Verify format: [TIMING] name: X.XXms
        assert "[TIMING]" in log_message
        assert "test_operation" in log_message
        assert "ms" in log_message

    @pytest.mark.asyncio
    async def test_timing_logger_measures_actual_time(self, mock_logger):
        """
        GIVEN: A TimingLogger
        WHEN: Code inside takes ~50ms
        THEN: Logged time should be >= 50ms
        """
        from app.utils.timing import TimingLogger
        
        async with TimingLogger("slow_op", mock_logger):
            await asyncio.sleep(0.05)  # 50ms
        
        log_message = mock_logger.info.call_args[0][0]
        
        # Extract time from message like "[TIMING] slow_op: 52.34ms"
        import re
        match = re.search(r'(\d+\.?\d*)ms', log_message)
        assert match, f"Could not find time in: {log_message}"
        
        elapsed_ms = float(match.group(1))
        assert elapsed_ms >= 50, f"Expected >= 50ms, got {elapsed_ms}ms"

    @pytest.mark.asyncio
    async def test_timing_logger_with_extra_data(self, mock_logger):
        """
        GIVEN: A TimingLogger with extra data
        WHEN: Used as context manager
        THEN: Should include extra data in log
        """
        from app.utils.timing import TimingLogger
        
        async with TimingLogger("db_query", mock_logger, rows=100, symbol="AAPL") as timer:
            await asyncio.sleep(0.01)
        
        log_message = mock_logger.info.call_args[0][0]
        
        assert "rows=100" in log_message
        assert "symbol=AAPL" in log_message

    @pytest.mark.asyncio
    async def test_timing_logger_handles_exception(self, mock_logger):
        """
        GIVEN: A TimingLogger
        WHEN: Exception occurs inside
        THEN: Should still log timing (for debugging)
        """
        from app.utils.timing import TimingLogger
        
        with pytest.raises(ValueError):
            async with TimingLogger("failing_op", mock_logger):
                raise ValueError("test error")
        
        # Should still log despite exception
        assert mock_logger.info.called or mock_logger.warning.called

    def test_sync_timing_logger(self, mock_logger):
        """
        GIVEN: A SyncTimingLogger
        WHEN: Used as sync context manager
        THEN: Should log elapsed time
        """
        from app.utils.timing import SyncTimingLogger
        import time
        
        with SyncTimingLogger("sync_op", mock_logger):
            time.sleep(0.01)
        
        assert mock_logger.info.called
        log_message = mock_logger.info.call_args[0][0]
        assert "[TIMING]" in log_message


class TestTimingDecorator:
    """Test timing decorator."""

    @pytest.fixture
    def mock_logger(self):
        logger = MagicMock()
        logger.log = MagicMock()
        logger.info = MagicMock()
        logger.warning = MagicMock()
        return logger

    @pytest.mark.asyncio
    async def test_timed_decorator_async(self, mock_logger):
        """
        GIVEN: An async function decorated with @timed
        WHEN: Function is called
        THEN: Should log execution time
        """
        from app.utils.timing import timed
        
        @timed(mock_logger)
        async def my_async_func():
            await asyncio.sleep(0.01)
            return "result"
        
        result = await my_async_func()
        
        assert result == "result"
        assert mock_logger.info.called
        log_message = mock_logger.info.call_args[0][0]
        assert "my_async_func" in log_message
