from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.config import settings
from app.schemas.prices import PriceRowOut
from app.services.normalize import normalize_symbol
from app.services.price_service import PriceService
from app.services.profiling import profile_function

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_and_validate_symbols(symbols_raw: str, auto_fetch: bool = True) -> List[str]:
    """
    - Parse comma-separated string
    - Normalize
    - Deduplicate
    - Check limit
    """
    if not symbols_raw:
        return []
    items = [s.strip() for s in symbols_raw.split(",")]
    items = [s for s in items if s]
    normalized = [normalize_symbol(s) for s in items]
    # unique & stable order
    seen = set()
    uniq = []
    for s in normalized:
        if s not in seen:
            uniq.append(s)
            seen.add(s)
            
    # Check limit based on auto_fetch setting
    max_symbols = settings.API_MAX_SYMBOLS if auto_fetch else settings.API_MAX_SYMBOLS_LOCAL
    
    if len(uniq) > max_symbols:
        raise HTTPException(
            status_code=422, 
            detail=f"too many symbols requested (max: {max_symbols})"
        )
    return uniq


@router.get("/prices", response_model=List[PriceRowOut])
@profile_function("get_prices_api")
async def get_prices(
    symbols: str = Query(..., description="Comma-separated symbols"),
    date_from: str = Query(..., alias="from", description="Start date (YYYY-MM-DD)"),
    date_to: str = Query(..., alias="to", description="End date (YYYY-MM-DD)"),
    auto_fetch: bool = Query(True, description="Auto-fetch all available data if missing"),
    session: AsyncSession = Depends(get_session),
):
    # Parse dates
    try:
        date_from_parsed = date.fromisoformat(date_from)
        date_to_parsed = date.fromisoformat(date_to)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {e}")
    
    # Validation
    if date_to_parsed < date_from_parsed:
        raise HTTPException(status_code=422, detail="invalid date range")
    
    symbols_list = _parse_and_validate_symbols(symbols, auto_fetch=auto_fetch)
    if not symbols_list:
        return []

    service = PriceService(session)
    
    t0 = time.perf_counter()
    
    try:
        rows = await service.get_prices(
            symbols_list=symbols_list,
            date_from=date_from_parsed,
            date_to=date_to_parsed,
            auto_fetch=auto_fetch,
        )
    except Exception as e:
        logger.error(f"Error fetching prices: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

    max_rows = settings.API_MAX_ROWS if auto_fetch else settings.API_MAX_ROWS_LOCAL
    
    if len(rows) > max_rows:
        raise HTTPException(status_code=413, detail=f"response too large (max: {max_rows} rows)")
        
    dt_ms = int((time.perf_counter() - t0) * 1000)
    
    logger.info(
        "prices served",
        extra=dict(
            symbols=symbols_list,
            date_from=str(date_from_parsed),
            date_to=str(date_to_parsed),
            rows=len(rows),
            duration_ms=dt_ms,
        ),
    )
    return rows


@router.delete("/prices/{symbol}")
async def delete_prices(
    symbol: str,
    date_from: Optional[str] = Query(None, description="Start date for deletion (inclusive)"),
    date_to: Optional[str] = Query(None, description="End date for deletion (inclusive)"),
    confirm: bool = Query(False, description="Confirmation flag to prevent accidental deletion"),
    session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Delete price data for a specific symbol."""
    try:
        # Normalize symbol
        normalized_symbol = normalize_symbol(symbol)
        
        # Parse dates
        date_from_parsed = date.fromisoformat(date_from) if date_from else None
        date_to_parsed = date.fromisoformat(date_to) if date_to else None
        
        # Require confirmation
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "CONFIRMATION_REQUIRED",
                        "message": "Deletion requires confirmation. Set 'confirm=true' to proceed.",
                        "details": {
                            "symbol": normalized_symbol,
                            "date_from": date_from_parsed.isoformat() if date_from_parsed else None,
                            "date_to": date_to_parsed.isoformat() if date_to_parsed else None,
                            "warning": "This operation permanently deletes data and cannot be undone!"
                        }
                    }
                }
            )
        
        # Validate date range
        if date_from_parsed and date_to_parsed and date_from_parsed > date_to_parsed:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_DATE_RANGE",
                        "message": "date_from must be before or equal to date_to",
                        "details": {
                            "date_from": date_from_parsed.isoformat(),
                            "date_to": date_to_parsed.isoformat()
                        }
                    }
                }
            )
        
        service = PriceService(session)
        
        try:
            deleted_rows = await service.delete_prices(
                symbol=normalized_symbol,
                date_from=date_from_parsed,
                date_to=date_to_parsed,
            )
        except Exception as e:
            logger.error(f"Error deleting prices for {symbol}: {e}", exc_info=True)
            await session.rollback()
            raise HTTPException(status_code=500, detail="Failed to delete price data")
        
        return {
            "symbol": normalized_symbol,
            "deleted_rows": deleted_rows,
            "date_range": {
                "from": date_from_parsed.isoformat() if date_from_parsed else None,
                "to": date_to_parsed.isoformat() if date_to_parsed else None
            },
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "message": f"Successfully deleted {deleted_rows} price records"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in delete_prices: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/prices/count/{symbol}")
async def get_price_count(
    symbol: str,
    session=Depends(get_session),
):
    """Get the count of price records for a symbol (for debugging data persistence)."""
    from sqlalchemy import text
    
    result = await session.execute(
        text("SELECT COUNT(*) FROM prices WHERE symbol = :symbol"),
        {"symbol": symbol.upper()}
    )
    count = result.scalar()
    
    # Also get date range
    date_result = await session.execute(
        text("SELECT MIN(date) as min_date, MAX(date) as max_date FROM prices WHERE symbol = :symbol"),
        {"symbol": symbol.upper()}
    )
    date_row = date_result.fetchone()
    
    return {
        "symbol": symbol.upper(),
        "count": count,
        "date_range": {
            "min": date_row.min_date.isoformat() if date_row.min_date else None,
            "max": date_row.max_date.isoformat() if date_row.max_date else None
        } if date_row else None
    }


@router.get("/performance/report")
async def get_performance_report():
    """Get performance profiling report for debugging bottlenecks."""
    from app.services.profiling import get_profiler
    
    profiler = get_profiler()
    report = profiler.get_performance_report()
    
    return {
        "performance_report": report,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


__all__ = ["router", "get_prices", "delete_prices", "get_price_count", "get_performance_report"]
