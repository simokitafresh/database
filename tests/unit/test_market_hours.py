"""Tests for market_hours module.

Test-driven development for the should_skip_today_data() function.
Tests cover various JST time scenarios to verify correct behavior.
"""

import pytest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.services.market_hours import (
    should_skip_today_data,
    MARKET_SKIP_START_HOUR,
    MARKET_SKIP_END_HOUR,
    JST,
)


class TestShouldSkipTodayData:
    """Test cases for should_skip_today_data function."""

    @pytest.mark.parametrize("hour,expected", [
        # During skip window (21:00-08:00 JST) - should return True
        (21, True),   # 21:00 JST - start of skip window
        (22, True),   # 22:00 JST - during skip window
        (23, True),   # 23:00 JST - during skip window
        (0, True),    # 00:00 JST - midnight, during skip window
        (1, True),    # 01:00 JST - during skip window
        (5, True),    # 05:00 JST - during skip window
        (7, True),    # 07:00 JST - during skip window
        
        # Outside skip window (08:00-21:00 JST) - should return False
        (8, False),   # 08:00 JST - end of skip window
        (9, False),   # 09:00 JST - outside skip window
        (12, False),  # 12:00 JST - noon, outside skip window
        (15, False),  # 15:00 JST - afternoon, outside skip window
        (18, False),  # 18:00 JST - evening, outside skip window
        (20, False),  # 20:00 JST - just before skip window
    ])
    def test_skip_window_hours(self, hour: int, expected: bool):
        """Test various hours to verify skip window boundaries."""
        with patch('app.services.market_hours._get_current_jst_hour', return_value=hour):
            result = should_skip_today_data()
            assert result == expected, f"Hour {hour}:00 JST should return {expected}"

    def test_boundary_21_00_is_skip(self):
        """21:00 JST exactly should be in skip window."""
        with patch('app.services.market_hours._get_current_jst_hour', return_value=21):
            assert should_skip_today_data() is True

    def test_boundary_08_00_is_not_skip(self):
        """08:00 JST exactly should NOT be in skip window."""
        with patch('app.services.market_hours._get_current_jst_hour', return_value=8):
            assert should_skip_today_data() is False

    def test_boundary_07_59_is_skip(self):
        """07:xx JST should still be in skip window (hour-based check)."""
        with patch('app.services.market_hours._get_current_jst_hour', return_value=7):
            assert should_skip_today_data() is True

    def test_boundary_20_59_is_not_skip(self):
        """20:xx JST should NOT be in skip window."""
        with patch('app.services.market_hours._get_current_jst_hour', return_value=20):
            assert should_skip_today_data() is False

    def test_constants_are_correct(self):
        """Verify the skip window constants are correctly defined."""
        assert MARKET_SKIP_START_HOUR == 21, "Skip should start at 21:00 JST"
        assert MARKET_SKIP_END_HOUR == 8, "Skip should end at 08:00 JST"

    def test_uses_jst_timezone(self):
        """Verify JST timezone is correctly configured."""
        assert JST == ZoneInfo("Asia/Tokyo")

