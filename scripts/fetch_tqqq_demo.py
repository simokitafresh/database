import asyncio
import sys
import os
from datetime import date, timedelta

# Add the project root to the python path
sys.path.append(os.getcwd())

from app.core.config import settings
from app.db.engine import create_engine_and_sessionmaker
from app.services.price_service import PriceService

async def main():
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Disable auto-registration for this demo to avoid external calls/errors
    settings.ENABLE_AUTO_REGISTRATION = False
    
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
        service = PriceService(session)
        
        # Fetch data around the reported split date (Oct 22-23)
        start_date = date(2025, 10, 15)
        end_date = date(2025, 10, 30)
        
        print(f"Fetching TQQQ prices from {start_date} to {end_date}...")
        
        try:
            prices = await service.get_prices(
                symbols_list=["TQQQ"],
                date_from=start_date,
                date_to=end_date,
                auto_fetch=False
            )
            
            with open("tqqq_prices.txt", "w") as f:
                f.write(f"Found {len(prices)} records.\n")
                for p in prices:
                    line = f"Date: {p['date']}, Close: {p['close']}, Volume: {p['volume']}\n"
                    print(line.strip())
                    f.write(line)
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
