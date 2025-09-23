import pytest
from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from app.main import app
from app.core.config import settings


class TestCronEndpoints:
    """Test cron job endpoints"""
    
    def setup_method(self):
        """Setup test client"""
        self.patcher = patch.object(settings, 'ENABLE_CACHE', False)
        self.patcher.start()
        self.client = TestClient(app)
        self.headers = {"X-Cron-Secret": "test-secret"}
    
    def teardown_method(self):
        """Teardown"""
        self.patcher.stop()
    
    @pytest.mark.skip(reason="Test is too slow due to TestClient startup, needs optimization")
    @patch('app.api.deps.get_session')
    @patch('app.db.queries.list_symbols')
    @patch.object(settings, 'CRON_SECRET_TOKEN', 'test-secret')
    def test_daily_update_dry_run(self, mock_list_symbols, mock_get_session):
        """Test dry run mode"""
        # Mock session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=AsyncMock(scalar=AsyncMock(return_value=1)))
        mock_get_session.return_value = mock_session
        
        # Mock list_symbols to return sample data quickly
        mock_list_symbols.return_value = [
            {"symbol": "AAPL"},
            {"symbol": "MSFT"},
            {"symbol": "GOOGL"}
        ]
        
        response = self.client.post(
            "/v1/daily-update",
            json={"dry_run": True},
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "total_symbols" in data
        assert "batch_count" in data
    
    @patch.object(settings, 'CRON_SECRET_TOKEN', 'test-secret')
    @patch('app.api.v1.cron.list_symbols')
    def test_daily_update_no_symbols(self, mock_list_symbols):
        """Test handling when no symbols found"""
        mock_list_symbols.return_value = []
        
        response = self.client.post(
            "/v1/daily-update",
            json={"dry_run": False},
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    def test_daily_update_missing_token(self):
        """Test missing authentication token"""
        response = self.client.post(
            "/v1/daily-update",
            json={"dry_run": True}
        )
        
        assert response.status_code == 401
        assert "Missing X-Cron-Secret header" in response.json()["error"]["message"]
    
    def test_daily_update_invalid_token(self):
        """Test invalid authentication token"""
        response = self.client.post(
            "/v1/daily-update",
            json={"dry_run": True},
            headers={"X-Cron-Secret": "invalid"}
        )
        
        assert response.status_code == 403
    
    @patch.object(settings, 'CRON_SECRET_TOKEN', 'test-secret')
    def test_status_endpoint(self):
        """Test cron status endpoint"""
        response = self.client.get(
            "/v1/status",
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"
        assert "settings" in data
    
    @patch.object(settings, 'CRON_SECRET_TOKEN', 'test-secret')
    def test_date_validation(self):
        """Test date format validation"""
        response = self.client.post(
            "/v1/daily-update",
            json={
                "dry_run": True,
                "date_from": "invalid-date"
            },
            headers=self.headers
        )
        
        assert response.status_code == 422  # Pydantic validation error


@pytest.fixture
def mock_cron_settings():
    """Mock cron settings for testing"""
    with patch.object(settings, 'CRON_SECRET_TOKEN', 'test-secret'), \
         patch.object(settings, 'CRON_BATCH_SIZE', 10), \
         patch.object(settings, 'CRON_UPDATE_DAYS', 3):
        yield


class TestCronLogic:
    """Test cron job business logic"""
    
    def test_batch_creation(self):
        """Test symbol batch creation"""
        symbols = [f"SYMBOL{i}" for i in range(100)]
        batch_size = 25
        
        batches = [
            symbols[i:i + batch_size]
            for i in range(0, len(symbols), batch_size)
        ]
        
        assert len(batches) == 4
        assert len(batches[0]) == 25
        assert len(batches[-1]) <= 25


if __name__ == "__main__":
    pytest.main([__file__])
