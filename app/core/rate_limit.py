"""Rate limiting and backoff utilities."""

import asyncio
import time
from typing import Optional

from app.core.config import Settings


class RateLimiter:
    """Token bucket rate limiter for API requests."""
    
    def __init__(self, rate_per_second: float, burst_size: int):
        self.rate_per_second = rate_per_second
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Acquire a token from the bucket, waiting if necessary."""
        async with self._lock:
            now = time.time()
            # Add tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate_per_second)
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                return
            
            # Calculate wait time for next token
            wait_time = (1 - self.tokens) / self.rate_per_second
            await asyncio.sleep(wait_time)
            self.tokens = 0
            self.last_update = time.time()
    
    def acquire_sync(self) -> None:
        """Synchronous version of acquire for use in sync functions."""
        # Simple token bucket implementation for sync context
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate_per_second)
        self.last_update = now
        
        if self.tokens < 1:
            # Simple delay calculation
            wait_time = (1 - self.tokens) / self.rate_per_second
            time.sleep(min(wait_time, 1.0))  # Cap at 1 second to avoid long delays
            self.tokens = 0
            self.last_update = time.time()
        else:
            self.tokens -= 1


class ExponentialBackoff:
    """Exponential backoff with jitter for retry logic."""
    
    def __init__(self, base_delay: float, multiplier: float, max_delay: float):
        self.base_delay = base_delay
        self.multiplier = multiplier
        self.max_delay = max_delay
        self.attempt = 0
    
    def reset(self):
        """Reset the backoff counter."""
        self.attempt = 0
    
    def get_delay(self) -> float:
        """Get the next delay duration."""
        if self.attempt == 0:
            delay = 0
        else:
            delay = min(self.base_delay * (self.multiplier ** (self.attempt - 1)), self.max_delay)
        self.attempt += 1
        return delay


# Global instances
_rate_limiter: Optional[RateLimiter] = None
_backoff: Optional[ExponentialBackoff] = None


def get_rate_limiter(settings: Settings) -> RateLimiter:
    """Get or create the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(
            rate_per_second=settings.YF_RATE_LIMIT_REQUESTS_PER_SECOND,
            burst_size=settings.YF_RATE_LIMIT_BURST_SIZE
        )
    return _rate_limiter


def get_backoff(settings: Settings) -> ExponentialBackoff:
    """Get or create the global backoff instance."""
    global _backoff
    if _backoff is None:
        _backoff = ExponentialBackoff(
            base_delay=settings.YF_RATE_LIMIT_BACKOFF_BASE_DELAY,
            multiplier=settings.YF_RATE_LIMIT_BACKOFF_MULTIPLIER,
            max_delay=settings.YF_RATE_LIMIT_MAX_BACKOFF_DELAY
        )
    return _backoff
