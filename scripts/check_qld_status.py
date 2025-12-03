import asyncio
import sys
import os
from datetime import date
from sqlalchemy import text

# Add the project root to the python path
sys.path.append(os.getcwd())

from app.core.config import settings
from app.db.engine import create_engine_and_sessionmaker
from app.services.price_service import PriceService

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
        # Check record count
        result = await session.execute(
            text("SELECT COUNT(*) FROM prices WHERE symbol = 'QLD'")
        )
        count = result.scalar()
        print(f"QLD record count: {count}")
        
        if count > 0:
            # Check prices around Oct 2025 (assuming similar split timing to TQQQ)
            service = PriceService(session)
            prices = await service.get_prices(
                symbols_list=["QLD"],
                date_from=date(2025, 10, 15),
                date_to=date(2025, 10, 30),
                auto_fetch=False 
            )
            
            print("\nQLD Prices (Oct 15-30, 2025):")
            for p in prices:
                print(f"Date: {p['date']}, Close: {p['close']}")

if __name__ == "__main__":
    asyncio.run(main())
