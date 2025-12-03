
import asyncio
import os
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import create_async_engine

# Use the same DB URL as the app
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres?sslmode=disable")

async def inspect_db():
    print(f"Connecting to {DATABASE_URL}")
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.connect() as conn:
        print("Connected!")
        
        # Check symbols table columns using raw SQL (easiest for async)
        result = await conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'symbols'"
        ))
        columns = result.fetchall()
        print("\nColumns in 'symbols' table:")
        for col in columns:
            print(f"- {col[0]} ({col[1]})")
            
        # Check if created_at exists
        has_created_at = any(col[0] == 'created_at' for col in columns)
        print(f"\nHas 'created_at' column: {has_created_at}")
        
        # Check alembic version
        try:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar()
            print(f"\nAlembic version: {version}")
        except Exception as e:
            print(f"\nCould not get alembic version: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_db())
