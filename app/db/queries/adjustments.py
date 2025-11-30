"""Database queries related to price adjustment detection."""

from datetime import date
from typing import List, Tuple

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Price, Symbol


async def get_adjustment_sample_data(
    session: AsyncSession,
    symbol: str,
    cutoff_date: date,
) -> List[Tuple[date, float]]:
    """
    Get all price points for a symbol before the cutoff date.
    
    Args:
        session: Async database session.
        symbol: Ticker symbol.
        cutoff_date: Date to filter prices (prices < cutoff_date).
        
    Returns:
        List of (date, close_price) tuples, ordered by date.
    """
    result = await session.execute(
        select(Price.date, Price.close)
        .where(and_(Price.symbol == symbol, Price.date < cutoff_date))
        .order_by(Price.date.asc())
    )
    return [(row[0], float(row[1])) for row in result.fetchall()]


async def get_closest_price_before_date(
    session: AsyncSession,
    symbol: str,
    target_date: date,
) -> Tuple[date, float] | None:
    """
    Get the closest price point for a symbol before the target date.
    
    Args:
        session: Async database session.
        symbol: Ticker symbol.
        target_date: Target date.
        
    Returns:
        Tuple of (date, close_price) or None if no data found.
    """
    result = await session.execute(
        select(Price.date, Price.close)
        .where(and_(Price.symbol == symbol, Price.date < target_date))
        .order_by(Price.date.desc())
        .limit(1)
    )
    row = result.fetchone()
    if row:
        return (row[0], float(row[1]))
    return None


async def get_symbols_for_scan(session: AsyncSession) -> List[str]:
    """
    Get all active symbols for scanning.
    
    Args:
        session: Async database session.
        
    Returns:
        List of symbol strings.
    """
    result = await session.execute(
        select(Symbol.symbol).where(Symbol.is_active == True)
    )
    return [row[0] for row in result.fetchall()]
