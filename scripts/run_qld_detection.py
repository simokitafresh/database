import asyncio
import sys
import os
from sqlalchemy import text

# Add the project root to the python path
sys.path.append(os.getcwd())

from app.core.config import settings
from app.db.engine import create_engine_and_sessionmaker
from app.services.adjustment_detector import PrecisionAdjustmentDetector

async def main():
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Use provided database URL
    settings.DATABASE_URL = "postgresql+asyncpg://postgres.yxmssjhujpazdkzwgvhi:%26K%265sCaJAsT5P-a@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"

    # Create sessionmaker
    engine, sessionmaker = create_engine_and_sessionmaker(
        database_url=settings.DATABASE_URL,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=900,
        echo=False
    )

    async with sessionmaker() as session:
        detector = PrecisionAdjustmentDetector()
        print("Running adjustment detection for QLD...")
        result = await detector.detect_adjustments(session, "QLD")
        
        print("\nDetection Result:")
        print(f"Needs Refresh: {result.needs_refresh}")
        print(f"Error: {result.error}")
        print(f"Max Pct Diff: {result.max_pct_diff}")
        
        if result.events:
            print("\nDetected Events:")
            for event in result.events:
                print(f"- Type: {event.event_type}")
                print(f"  Severity: {event.severity}")
                print(f"  Check Date: {event.check_date}")
                print(f"  DB Price: {event.db_price}")
                print(f"  YF Price: {event.yf_adjusted_price}")
                print(f"  Diff: {event.pct_difference}%")

if __name__ == "__main__":
    asyncio.run(main())
