import asyncio
import sys
import os
from sqlalchemy import text

# Add the project root to the python path
sys.path.append(os.getcwd())

from app.core.config import settings
from app.db.engine import create_engine_and_sessionmaker

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
        result = await session.execute(
            text("SELECT COUNT(*) FROM prices WHERE symbol = 'TQQQ'")
        )
        count = result.scalar()
        print(f"TQQQ record count: {count}")

if __name__ == "__main__":
    asyncio.run(main())
