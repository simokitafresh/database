"""Tests for TID-ADJ-001: Adjustment detection configuration settings."""

import os
import pytest
from unittest.mock import patch


class TestAdjustmentSettingsDefaults:
    """Test default values for adjustment settings."""

    def test_adjustment_check_enabled_default(self):
        """Test ADJUSTMENT_CHECK_ENABLED defaults to True."""
        from app.core.config import Settings
        settings = Settings()
        assert settings.ADJUSTMENT_CHECK_ENABLED is True

    def test_adjustment_min_threshold_pct_default(self):
        """Test ADJUSTMENT_MIN_THRESHOLD_PCT defaults to 0.001."""
        from app.core.config import Settings
        settings = Settings()
        assert settings.ADJUSTMENT_MIN_THRESHOLD_PCT == 0.001

    def test_adjustment_sample_points_default(self):
        """Test ADJUSTMENT_SAMPLE_POINTS defaults to 10."""
        from app.core.config import Settings
        settings = Settings()
        assert settings.ADJUSTMENT_SAMPLE_POINTS == 10

    def test_adjustment_min_data_age_days_default(self):
        """Test ADJUSTMENT_MIN_DATA_AGE_DAYS defaults to 7 (reduced to catch recent splits)."""
        from app.core.config import Settings
        settings = Settings()
        assert settings.ADJUSTMENT_MIN_DATA_AGE_DAYS == 7

    def test_adjustment_auto_fix_default(self):
        """Test ADJUSTMENT_AUTO_FIX defaults to False."""
        from app.core.config import Settings
        settings = Settings()
        assert settings.ADJUSTMENT_AUTO_FIX is False

    def test_adjustment_check_full_history_default(self):
        """Test ADJUSTMENT_CHECK_FULL_HISTORY defaults to True."""
        from app.core.config import Settings
        settings = Settings()
        assert settings.ADJUSTMENT_CHECK_FULL_HISTORY is True


class TestAdjustmentSettingsFromEnv:
    """Test reading adjustment settings from environment variables."""

    def test_adjustment_check_enabled_from_env(self):
        """Test ADJUSTMENT_CHECK_ENABLED can be set via environment."""
        with patch.dict(os.environ, {"ADJUSTMENT_CHECK_ENABLED": "false"}):
            from app.core.config import Settings
            settings = Settings()
            assert settings.ADJUSTMENT_CHECK_ENABLED is False

    def test_adjustment_min_threshold_pct_from_env(self):
        """Test ADJUSTMENT_MIN_THRESHOLD_PCT can be set via environment."""
        with patch.dict(os.environ, {"ADJUSTMENT_MIN_THRESHOLD_PCT": "0.01"}):
            from app.core.config import Settings
            settings = Settings()
            assert settings.ADJUSTMENT_MIN_THRESHOLD_PCT == 0.01

    def test_adjustment_sample_points_from_env(self):
        """Test ADJUSTMENT_SAMPLE_POINTS can be set via environment."""
        with patch.dict(os.environ, {"ADJUSTMENT_SAMPLE_POINTS": "20"}):
            from app.core.config import Settings
            settings = Settings()
            assert settings.ADJUSTMENT_SAMPLE_POINTS == 20

    def test_adjustment_min_data_age_days_from_env(self):
        """Test ADJUSTMENT_MIN_DATA_AGE_DAYS can be set via environment."""
        with patch.dict(os.environ, {"ADJUSTMENT_MIN_DATA_AGE_DAYS": "90"}):
            from app.core.config import Settings
            settings = Settings()
            assert settings.ADJUSTMENT_MIN_DATA_AGE_DAYS == 90

    def test_adjustment_auto_fix_from_env(self):
        """Test ADJUSTMENT_AUTO_FIX can be set via environment."""
        with patch.dict(os.environ, {"ADJUSTMENT_AUTO_FIX": "true"}):
            from app.core.config import Settings
            settings = Settings()
            assert settings.ADJUSTMENT_AUTO_FIX is True
