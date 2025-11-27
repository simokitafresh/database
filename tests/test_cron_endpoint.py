import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from app.api.v1.cron import daily_economic_update
from app.schemas.cron import CronDailyUpdateRequest

class TestCronEndpoint(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.fred_service.get_fred_service")
    async def test_daily_economic_update(self, mock_get_service):
        # Mock Service
        mock_service = MagicMock()
        mock_service.fetch_dtb3_data.return_value = [
            {"date": date(2023, 1, 1), "value": 4.5, "symbol": "DTB3"}
        ]
        mock_service.save_economic_data_async = AsyncMock()
        mock_get_service.return_value = mock_service

        # Mock Session
        mock_session = AsyncMock()

        # Test Request
        request = CronDailyUpdateRequest(dry_run=False)
        
        response = await daily_economic_update(
            request=request,
            session=mock_session,
            authenticated=True
        )

        self.assertEqual(response.status, "success")
        self.assertEqual(response.success_count, 1)
        mock_service.fetch_dtb3_data.assert_called_once()
        mock_service.save_economic_data_async.assert_called_once()

if __name__ == "__main__":
    unittest.main()
