#!/usr/bin/env python3
"""Check database structure."""

import asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings


async def check_db():
    """Check current database structure."""
    engine = create_async_engine(settings.DATABASE_URL)
    
    async with engine.connect() as conn:
        # Check symbols table structure
        result = await conn.execute(sa.text("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'symbols' AND table_schema = 'public'
            ORDER BY ordinal_position
        """))
        
        print('Symbols table structure:')
        for row in result:
            print(f'  {row.column_name}: {row.data_type} (nullable: {row.is_nullable})')
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check_db())
