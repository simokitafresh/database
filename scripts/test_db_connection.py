import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app.db.engine import create_engine_and_sessionmaker
from app.core.config import settings
from app.db.queries.symbols import list_symbols

async def main():
    # Mask password for logging
    safe_url = settings.DATABASE_URL
    if "@" in safe_url:
        safe_url = safe_url.split("@")[-1]
    
    print(f"Connecting to DB: ...@{safe_url}")
    
    try:
        engine, session_factory = create_engine_and_sessionmaker(
            database_url=settings.DATABASE_URL,
            echo=True
        )
        
        async with session_factory() as session:
            try:
                print("Executing list_symbols(active=True)...")
                symbols = await list_symbols(session, active=True)
                print(f"Success! Found {len(symbols)} active symbols.")
                for s in symbols[:5]:
                    print(f" - {s['symbol']}")
            except Exception as e:
                print(f"Error executing query: {e}")
                import traceback
                traceback.print_exc()
        
        await engine.dispose()
        
    except Exception as e:
        print(f"Error creating engine: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
