# app/services/profiling.py
"""Performance profiling service for identifying bottlenecks."""

from __future__ import annotations

import asyncio
import cProfile
import io
import logging
import pstats
import time
from contextlib import contextmanager
from typing import Dict, Any, Optional, Callable
from functools import wraps

logger = logging.getLogger(__name__)


class PerformanceProfiler:
    """Performance profiling utility for identifying bottlenecks."""
    
    def __init__(self):
        self.profiles: Dict[str, pstats.Stats] = {}
        self.timing_data: Dict[str, list] = {}
    
    @contextmanager
    def profile_context(self, name: str):
        """Context manager for profiling code blocks."""
        if not settings.ENABLE_PROFILING:
            yield
            return
            
        pr = cProfile.Profile()
        pr.enable()
        start_time = time.time()
        
        try:
            yield
        finally:
            pr.disable()
            end_time = time.time()
            duration = end_time - start_time
            
            # Store timing data
            if name not in self.timing_data:
                self.timing_data[name] = []
            self.timing_data[name].append(duration)
            
            # Keep only last 100 measurements
            if len(self.timing_data[name]) > 100:
                self.timing_data[name] = self.timing_data[name][-100:]
            
            # Store profile data
            s = io.StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
            ps.print_stats(20)  # Top 20 functions
            self.profiles[name] = ps
            
            logger.debug(f"Profiled {name}: {duration:.3f}s")
    
    def profile_function(self, name: Optional[str] = None):
        """Decorator for profiling functions."""
        def decorator(func: Callable):
            profile_name = name or f"{func.__module__}.{func.__name__}"
            
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                with self.profile_context(profile_name):
                    return await func(*args, **kwargs)
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                with self.profile_context(profile_name):
                    return func(*args, **kwargs)
            
            # Return appropriate wrapper based on function type
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
        
        return decorator
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate performance report."""
        report = {
            "timing_stats": {},
            "slowest_operations": []
        }
        
        # Calculate timing statistics
        for name, times in self.timing_data.items():
            if times:
                report["timing_stats"][name] = {
                    "count": len(times),
                    "avg": sum(times) / len(times),
                    "min": min(times),
                    "max": max(times),
                    "recent_avg": sum(times[-10:]) / min(10, len(times))  # Last 10 measurements
                }
        
        # Find slowest operations
        if self.timing_data:
            all_times = []
            for name, times in self.timing_data.items():
                for t in times[-10:]:  # Only recent measurements
                    all_times.append((name, t))
            
            all_times.sort(key=lambda x: x[1], reverse=True)
            report["slowest_operations"] = [
                {"operation": name, "duration": duration}
                for name, duration in all_times[:10]
            ]
        
        return report
    
    def clear_data(self):
        """Clear all profiling data."""
        self.profiles.clear()
        self.timing_data.clear()


# Global profiler instance
_profiler = PerformanceProfiler()


def get_profiler() -> PerformanceProfiler:
    """Get the global profiler instance."""
    return _profiler


def profile_function(name: Optional[str] = None):
    """Decorator to profile a function."""
    return get_profiler().profile_function(name)


@contextmanager
def profile_block(name: str):
    """Context manager to profile a code block."""
    with get_profiler().profile_context(name):
        yield


__all__ = ["PerformanceProfiler", "get_profiler", "profile_function", "profile_block"]