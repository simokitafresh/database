
import asyncio
import sys
import os
from pathlib import Path

# Add project root to python path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from app.api.deps import get_session
from app.services.adjustment_detector import PrecisionAdjustmentDetector

async def main():
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    print("Starting TQQQ adjustment check...")
    
    # Get session
    async for session in get_session():
        detector = PrecisionAdjustmentDetector()
        
        print("Running detect_adjustments for TQQQ...")
        # Manually call get_sample_prices to see what it returns
        samples = await detector.get_sample_prices(session, "TQQQ")
        print(f"Samples found: {len(samples)}")
        for date, price in samples:
            print(f"  Sample: {date}, DB Price: {price}")
            
        result = await detector.detect_adjustments(session, "TQQQ")
        
        print("\n--- Detection Result ---")
        print(f"Symbol: {result.symbol}")
        print(f"Needs Refresh: {result.needs_refresh}")
        print(f"Error: {result.error}")
        print(f"Max Pct Diff: {result.max_pct_diff}")
        
        if result.events:
            print(f"\nEvents ({len(result.events)}):")
            for event in result.events:
                print(f"  - Type: {event.event_type}")
                print(f"    Severity: {event.severity}")
                print(f"    Date: {event.check_date}")
                print(f"    DB Price: {event.db_price}")
                print(f"    YF Price: {event.yf_adjusted_price}")
                print(f"    Diff: {event.pct_difference}%")
                print(f"    Details: {event.details}")
        else:
            print("\nNo events detected.")
            
        break # Only need one session

if __name__ == "__main__":
    asyncio.run(main())
