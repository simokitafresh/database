"""Market hours utility for skipping intraday data during US market hours.

During US market hours, yfinance returns real-time prices for the 'close' field
instead of actual closing prices. This module provides a simple check to skip
today's data during these hours to avoid storing inaccurate prices.

Design: Use fixed JST time window (21:00-08:00) to cover both winter and summer time
with a 2-hour buffer, avoiding complex timezone calculations.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# Skip window: JST 21:00 - 08:00 (covers US market hours with buffer)
# Winter: NYSE 9:30-16:00 ET = 23:30-06:00 JST
# Summer: NYSE 9:30-16:00 ET = 22:30-05:00 JST
MARKET_SKIP_START_HOUR = 21  # 21:00 JST
MARKET_SKIP_END_HOUR = 8     # 08:00 JST


def _get_current_jst_hour() -> int:
    """Get current hour in JST. Extracted for testability."""
    return datetime.now(JST).hour


def should_skip_today_data() -> bool:
    """Check if current time falls within US market hours (with buffer).
    
    Returns True during JST 21:00-08:00, when US markets are likely open
    or have recently closed. During this window, today's data should be
    skipped to avoid storing inaccurate intraday prices as 'close' values.
    
    Returns:
        bool: True if today's data should be skipped, False otherwise.
    """
    hour = _get_current_jst_hour()
    return hour >= MARKET_SKIP_START_HOUR or hour < MARKET_SKIP_END_HOUR


__all__ = ["should_skip_today_data"]

