
import asyncio
import sys
import os
from pathlib import Path

# Add project root to python path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

# Fix for Windows asyncio loop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.api.deps import get_session
from app.services.adjustment_detector import PrecisionAdjustmentDetector
from app.core.config import settings

async def main():
    print("Starting TQQQ manual fix...")
    
    # Force enable auto fix for this script execution
    settings.ADJUSTMENT_AUTO_FIX = True
    
    async for session in get_session():
        detector = PrecisionAdjustmentDetector()
        
        print("Scanning and fixing TQQQ...")
        # We use scan_all_symbols with a single symbol to leverage the auto_fix logic
        # embedded in the scan process, or we can call auto_fix_symbol directly if we are sure.
        # Let's use auto_fix_symbol directly as per the plan.
        
        # First, let's detect to be sure
        detection = await detector.detect_adjustments(session, "TQQQ")
        if detection.needs_refresh:
            print(f"Adjustment detected: {detection.events}")
            print("Proceeding with auto-fix...")
            
            fix_result = await detector.auto_fix_symbol(session, "TQQQ")
            print("\n--- Fix Result ---")
            print(f"Symbol: {fix_result['symbol']}")
            print(f"Deleted Rows: {fix_result['deleted_rows']}")
            print(f"Job Created: {fix_result['job_created']}")
            print(f"Job ID: {fix_result['job_id']}")
            print(f"Date Range: {fix_result['date_range']}")
            
            if fix_result['error']:
                print(f"Error: {fix_result['error']}")
        else:
            print("No adjustment needed for TQQQ according to detector.")
            # Force fix anyway since user reported it? 
            # The user said "10/22 data is incorrect". 
            # If detector says no, maybe our thresholds are too loose or data is already "fixed" in some way but wrong?
            # But the previous debug run showed "No events detected".
            # Wait, if the previous debug run showed no events, then `detect_adjustments` returned False.
            # If I run this script and it says "No adjustment needed", nothing will happen.
            # I should probably force the fix regardless of detection if the user is sure.
            
            print("Forcing fix based on user request...")
            fix_result = await detector.auto_fix_symbol(session, "TQQQ")
            print("\n--- Fix Result (Forced) ---")
            print(f"Symbol: {fix_result['symbol']}")
            print(f"Deleted Rows: {fix_result['deleted_rows']}")
            print(f"Job Created: {fix_result['job_created']}")
            print(f"Job ID: {fix_result['job_id']}")
        
        break

if __name__ == "__main__":
    asyncio.run(main())
