import requests
import sys

API_KEY = "a8d44f5fee887e9c844a783374065be4"
URL = "https://api.stlouisfed.org/fred/series/observations"

params = {
    "series_id": "DTB3",
    "api_key": API_KEY,
    "file_type": "json",
    "limit": 1
}

try:
    response = requests.get(URL, params=params)
    response.raise_for_status()
    data = response.json()
    print("Success! API Key is valid.")
    print(f"Sample Data: {data['observations'][0]}")
except Exception as e:
    print(f"Error: {e}")
    if response.status_code == 400:
        print("Bad Request - Likely invalid API key or parameters.")
    elif response.status_code == 403:
        print("Forbidden - API key may be invalid or disabled.")
    sys.exit(1)
