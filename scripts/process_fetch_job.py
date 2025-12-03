import asyncio
import sys
import os
from sqlalchemy import select

# Add the project root to the python path
sys.path.append(os.getcwd())

from app.core.config import settings
from app.db.engine import create_engine_and_sessionmaker
from app.db.models import FetchJob

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
        # Find the pending job
        result = await session.execute(
            select(FetchJob).where(FetchJob.status == "pending").limit(1)
        )
        job = result.scalar_one_or_none()
        
        if job:
            print(f"Processing job {job.job_id} for {job.symbols}...")
            from app.services.fetch_worker import process_fetch_job
            
            await process_fetch_job(
                job_id=job.job_id,
                symbols=job.symbols,
                date_from=job.date_from,
                date_to=job.date_to,
                interval=job.interval,
                force=job.force_refresh
            )
            await session.commit()
            print("Job processed successfully.")
        else:
            print("No pending jobs found.")

if __name__ == "__main__":
    asyncio.run(main())
