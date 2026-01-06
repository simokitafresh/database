"""List all symbols in the database."""
import asyncio
import sys
sys.path.insert(0, "c:\\Python_app\\database")

from app.db.engine import get_async_session
from sqlalchemy import text


async def main():
    session_factory = get_async_session()
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT symbol, name, exchange, is_active FROM symbols ORDER BY symbol")
        )
        rows = result.fetchall()
        print(f"Total symbols: {len(rows)}")
        print()
        print(f"{'Symbol':<10} | {'Name':<40} | {'Exchange':<10} | {'Active'}")
        print("-" * 80)
        for r in rows:
            print(f"{r[0]:<10} | {str(r[1] or ''):<40} | {str(r[2] or ''):<10} | {r[3]}")


if __name__ == "__main__":
    asyncio.run(main())
