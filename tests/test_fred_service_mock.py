import unittest
from unittest.mock import MagicMock, patch
from datetime import date
from app.services.fred_service import FredService

class TestFredService(unittest.TestCase):
    def setUp(self):
        self.service = FredService(api_key="test_key")

    @patch("requests.get")
    def test_fetch_dtb3_data(self, mock_get):
        # Mock FRED API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "observations": [
                {"date": "2023-01-01", "value": "4.5"},
                {"date": "2023-01-02", "value": "."}, # Missing value
                {"date": "2023-01-03", "value": "4.6"}
            ]
        }
        mock_get.return_value = mock_response

        data = self.service.fetch_dtb3_data(start_date=date(2023, 1, 1), end_date=date(2023, 1, 3))
        
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["date"], date(2023, 1, 1))
        self.assertEqual(data[0]["value"], 4.5)
        self.assertEqual(data[0]["symbol"], "DTB3")
        self.assertEqual(data[1]["date"], date(2023, 1, 3))
        self.assertEqual(data[1]["value"], 4.6)

if __name__ == "__main__":
    unittest.main()
