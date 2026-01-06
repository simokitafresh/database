"""Timing utilities for performance measurement and logging.

Usage:
    async with TimingLogger("operation_name", logger):
        await some_async_operation()
    
    with SyncTimingLogger("sync_op", logger):
        sync_operation()
    
    @timed(logger)
    async def my_function():
        ...
"""

import time
import logging
import functools
from typing import Any, Optional


class TimingLogger:
    """Async context manager for timing code blocks.
    
    Logs execution time with [TIMING] prefix for easy grep-ability.
    
    Example:
        async with TimingLogger("db_query", logger, rows=100) as timer:
            result = await db.execute(query)
        # Logs: [TIMING] db_query: 45.32ms, rows=100
    """
    
    def __init__(
        self, 
        name: str, 
        logger: logging.Logger,
        log_level: int = logging.INFO,
        **extra_data: Any
    ):
        self.name = name
        self.logger = logger
        self.log_level = log_level
        self.extra_data = extra_data
        self.start: float = 0.0
        self.elapsed_ms: float = 0.0
    
    async def __aenter__(self) -> "TimingLogger":
        self.start = time.perf_counter()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.elapsed_ms = (time.perf_counter() - self.start) * 1000
        self._log(exc_type is not None)
        return False  # Don't suppress exceptions
    
    def _log(self, had_exception: bool = False) -> None:
        """Format and emit the timing log."""
        extra_str = ""
        if self.extra_data:
            extra_str = ", " + ", ".join(f"{k}={v}" for k, v in self.extra_data.items())
        
        message = f"[TIMING] {self.name}: {self.elapsed_ms:.2f}ms{extra_str}"
        
        if had_exception:
            self.logger.warning(message + " (exception occurred)")
        else:
            self.logger.info(message)


class SyncTimingLogger:
    """Sync context manager for timing code blocks.
    
    Same as TimingLogger but for synchronous code.
    """
    
    def __init__(
        self, 
        name: str, 
        logger: logging.Logger,
        log_level: int = logging.INFO,
        **extra_data: Any
    ):
        self.name = name
        self.logger = logger
        self.log_level = log_level
        self.extra_data = extra_data
        self.start: float = 0.0
        self.elapsed_ms: float = 0.0
    
    def __enter__(self) -> "SyncTimingLogger":
        self.start = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.elapsed_ms = (time.perf_counter() - self.start) * 1000
        self._log(exc_type is not None)
        return False
    
    def _log(self, had_exception: bool = False) -> None:
        """Format and emit the timing log."""
        extra_str = ""
        if self.extra_data:
            extra_str = ", " + ", ".join(f"{k}={v}" for k, v in self.extra_data.items())
        
        message = f"[TIMING] {self.name}: {self.elapsed_ms:.2f}ms{extra_str}"
        
        if had_exception:
            self.logger.warning(message + " (exception occurred)")
        else:
            self.logger.info(message)


def timed(logger: logging.Logger, name: Optional[str] = None):
    """Decorator for timing async or sync functions.
    
    Example:
        @timed(logger)
        async def fetch_data():
            ...
    """
    import asyncio
    
    def decorator(func):
        func_name = name or func.__name__
        
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    logger.info(f"[TIMING] {func_name}: {elapsed_ms:.2f}ms")
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return func(*args, **kwargs)
                finally:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    logger.info(f"[TIMING] {func_name}: {elapsed_ms:.2f}ms")
            return sync_wrapper
    return decorator


__all__ = ["TimingLogger", "SyncTimingLogger", "timed"]
