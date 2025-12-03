
import asyncio
import logging
from datetime import date, timedelta
from app.services.fetcher import fetch_prices
from app.core.config import settings

# Configure logging to capture output
logging.basicConfig(level=logging.INFO)

def test_fetch_index_fix():
    print("Testing fetch_prices with IRX (should automatically use ^IRX)...")
    
    # Test with a known index that requires caret
    symbol = "IRX"
    today = date.today()
    start_date = today - timedelta(days=5)
    
    # This should NOT log an error about missing data for "IRX"
    # It should directly fetch "^IRX"
    try:
        df = fetch_prices(symbol, start_date, today, settings=settings)
        
        if df is not None and not df.empty:
            print(f"Successfully fetched data for {symbol}")
            print(f"Data shape: {df.shape}")
        else:
            print(f"Failed to fetch data for {symbol}")
            
    except Exception as e:
        print(f"Exception occurred: {e}")

if __name__ == "__main__":
    test_fetch_index_fix()
