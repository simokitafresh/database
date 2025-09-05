from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from app.api.deps import get_session  # AsyncSession 依存性
from app.api.errors import SymbolNotFoundError, DatabaseError, raise_http_error
from app.core.config import settings
from app.db import queries
from app.schemas.prices import PriceRowOut
from app.services.normalize import normalize_symbol

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_and_validate_symbols(symbols_raw: str) -> List[str]:
    """
    - カンマ分割 → trim → 空要素除去
    - 正規化（大文字、クラス株、サフィックス維持）
    - 去重
    - 上限チェック
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
    if len(uniq) > settings.API_MAX_SYMBOLS:
        raise HTTPException(status_code=422, detail="too many symbols requested")
    return uniq


@router.get("/prices", response_model=List[PriceRowOut])
async def get_prices(
    symbols: str = Query(..., description="Comma-separated symbols"),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    session=Depends(get_session),
):
    # --- validation ---
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="invalid date range")
    symbols_list = _parse_and_validate_symbols(symbols)
    if not symbols_list:
        return []

    # --- orchestration (欠損検出・再取得は内部サービスに委譲してもよい) ---
    # 1) 欠損カバレッジを確認し、不足分＋直近N日を取得してUPSERT（冪等）
    t0 = time.perf_counter()
    await queries.ensure_coverage(
        session=session,
        symbols=symbols_list,
        date_from=date_from,
        date_to=date_to,
        refetch_days=settings.YF_REFETCH_DAYS,
    )

    # 2) 透過解決済み結果を取得
    rows = await queries.get_prices_resolved(
        session=session,
        symbols=symbols_list,
        date_from=date_from,
        date_to=date_to,
    )

    if len(rows) > settings.API_MAX_ROWS:
        raise HTTPException(status_code=413, detail="response too large")
    dt_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "prices served",
        extra=dict(
            symbols=symbols_list,
            date_from=str(date_from),
            date_to=str(date_to),
            rows=len(rows),
            duration_ms=dt_ms,
        ),
    )
    return rows


@router.delete("/prices/{symbol}")
async def delete_prices(
    symbol: str,
    date_from: Optional[date] = Query(None, description="Start date for deletion (inclusive)"),
    date_to: Optional[date] = Query(None, description="End date for deletion (inclusive)"),
    confirm: bool = Query(False, description="Confirmation flag to prevent accidental deletion"),
    session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """
    Delete price data for a specific symbol.
    
    **⚠️ WARNING: This operation permanently deletes data and cannot be undone!**
    
    Deletes price records for the specified symbol within the given date range.
    If no date range is specified, ALL data for the symbol will be deleted.
    
    ## Path Parameters
    
    - **symbol**: The symbol to delete data for (will be normalized)
    
    ## Query Parameters
    
    - **date_from**: Start date for deletion (optional)
    - **date_to**: End date for deletion (optional)  
    - **confirm**: Must be set to `true` to confirm the deletion
    
    ## Examples
    
    Delete all data for AAPL:
    ```
    DELETE /v1/prices/AAPL?confirm=true
    ```
    
    Delete AAPL data for 2024:
    ```
    DELETE /v1/prices/AAPL?date_from=2024-01-01&date_to=2024-12-31&confirm=true
    ```
    
    ## Response
    
    Returns information about the deletion including the number of rows deleted.
    """
    try:
        # Normalize symbol
        normalized_symbol = normalize_symbol(symbol)
        
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
                            "date_from": date_from.isoformat() if date_from else None,
                            "date_to": date_to.isoformat() if date_to else None,
                            "warning": "This operation permanently deletes data and cannot be undone!"
                        }
                    }
                }
            )
        
        # Validate date range
        if date_from and date_to and date_from > date_to:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_DATE_RANGE",
                        "message": "date_from must be before or equal to date_to",
                        "details": {
                            "date_from": date_from.isoformat(),
                            "date_to": date_to.isoformat()
                        }
                    }
                }
            )
        
        # Build delete query
        query = "DELETE FROM prices WHERE symbol = :symbol"
        params = {"symbol": normalized_symbol}
        
        if date_from:
            query += " AND date >= :date_from"
            params["date_from"] = date_from
        
        if date_to:
            query += " AND date <= :date_to"
            params["date_to"] = date_to
        
        # Log the deletion attempt
        logger.warning(
            f"Price data deletion requested for symbol {normalized_symbol}",
            extra={
                "symbol": normalized_symbol,
                "date_from": str(date_from) if date_from else None,
                "date_to": str(date_to) if date_to else None,
                "query": query,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        # Execute deletion
        result = await session.execute(text(query), params)
        deleted_rows = result.rowcount
        
        # Commit the transaction
        await session.commit()
        
        # Log successful deletion
        logger.warning(
            f"Price data deleted: {deleted_rows} rows for symbol {normalized_symbol}",
            extra={
                "symbol": normalized_symbol,
                "deleted_rows": deleted_rows,
                "date_from": str(date_from) if date_from else None,
                "date_to": str(date_to) if date_to else None,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        return {
            "symbol": normalized_symbol,
            "deleted_rows": deleted_rows,
            "date_range": {
                "from": date_from.isoformat() if date_from else None,
                "to": date_to.isoformat() if date_to else None
            },
            "deleted_at": datetime.utcnow().isoformat(),
            "message": f"Successfully deleted {deleted_rows} price records"
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log error and rollback
        logger.error(f"Error deleting prices for {symbol}: {e}", exc_info=True)
        await session.rollback()
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "DELETION_ERROR",
                    "message": "Failed to delete price data",
                    "details": {
                        "symbol": symbol,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
            }
        )


__all__ = ["router", "get_prices", "delete_prices"]
