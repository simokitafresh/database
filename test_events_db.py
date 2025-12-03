"""Test script to verify corporate_events table and API functionality."""
import asyncio
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Use the Supabase connection string
DATABASE_URL = "postgresql+asyncpg://postgres.yxmssjhujpazdkzwgvhi:%26K%265sCaJAsT5P-a@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"

async def test_corporate_events():
    """Test corporate_events table."""
    print("Testing database connection...")
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Test 1: Check if table exists
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'corporate_events'
            )
        """))
        table_exists = result.scalar()
        print(f"✓ corporate_events table exists: {table_exists}")
        
        if not table_exists:
            print("✗ Table does not exist! Migration may have failed.")
            return
        
        # Test 2: Check table structure
        result = await session.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'corporate_events'
            ORDER BY ordinal_position
        """))
        columns = result.fetchall()
        print(f"\n✓ Table has {len(columns)} columns:")
        for col in columns:
            print(f"  - {col[0]}: {col[1]}")
        
        # Test 3: Count existing events
        result = await session.execute(text("SELECT COUNT(*) FROM corporate_events"))
        count = result.scalar()
        print(f"\n✓ Current event count: {count}")
        
        # Test 4: Get recent events (if any)
        if count > 0:
            result = await session.execute(text("""
                SELECT id, symbol, event_type, status, detected_at 
                FROM corporate_events 
                ORDER BY detected_at DESC 
                LIMIT 5
            """))
            events = result.fetchall()
            print(f"\n✓ Recent events:")
            for event in events:
                print(f"  - ID:{event[0]} {event[1]} {event[2]} status:{event[3]}")
        
    await engine.dispose()
    print("\n✅ All database tests passed!")

if __name__ == "__main__":
    asyncio.run(test_corporate_events())
