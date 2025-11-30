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

    # Disable auto-registration for this script
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
        
        print("Deleting existing TQQQ data...")
        try:
            deleted = await service.delete_prices("TQQQ")
            print(f"Deleted {deleted} rows.")
        except Exception as e:
            print(f"Error deleting prices: {e}")
            return

        # Fetch full history (TQQQ inception was Feb 2010)
        start_date = date(2010, 1, 1)
        end_date = date.today()
        
        print(f"Re-fetching TQQQ prices from {start_date} to {end_date}...")
        
        try:
            prices = await service.get_prices(
                symbols_list=["TQQQ"],
                date_from=start_date,
                date_to=end_date,
                auto_fetch=True # This triggers the download from Yahoo Finance
            )
            
            print(f"Found {len(prices)} records.")
            
            # Check specific dates
            target_dates = [date(2025, 10, 21), date(2025, 10, 22), date(2025, 10, 23), date(2025, 10, 24)]
            
            print("\nVerifying data around split (Oct 22-23):")
            with open("fix_output.txt", "w") as f:
                for p in prices:
                    if p['date'] in target_dates:
                        line = f"Date: {p['date']}, Close: {p['close']}, Volume: {p['volume']}\n"
                        print(line.strip())
                        f.write(line)
            
            # Commit the changes to the database
            await session.commit()
            print("Successfully committed changes to database.")
                
        except Exception as e:
            print(f"Error fetching prices: {e}")

if __name__ == "__main__":
    asyncio.run(main())
