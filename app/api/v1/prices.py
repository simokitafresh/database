from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from app.api.deps import get_session  # AsyncSession 依存性
from app.api.errors import SymbolNotFoundError, SymbolRegistrationError, DatabaseError, raise_http_error
from app.core.config import settings
from app.db import queries
from app.schemas.prices import PriceRowOut
from app.services.normalize import normalize_symbol
from app.services.auto_register import auto_register_symbol, batch_register_symbols

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


async def ensure_symbols_registered(
    session: AsyncSession, 
    symbols: List[str]
) -> None:
    """
    Ensure all symbols are registered in the database with parallel processing.
    
    For each symbol:
    1. Check if already exists in database
    2. If not, validate with Yahoo Finance
    3. If valid, register in database
    4. If invalid, raise SymbolNotFoundError
    
    Parameters
    ----------
    session : AsyncSession
        Database session
    symbols : List[str] 
        List of normalized symbols to check/register
        
    Raises
    ------
    SymbolNotFoundError
        If a symbol doesn't exist in Yahoo Finance
    SymbolRegistrationError
        If database registration fails
    """
    # Use batch registration for parallel processing
    registration_results = await batch_register_symbols(session, symbols)
    
    # Check results and raise appropriate errors
    for symbol, success in registration_results.items():
        if not success:
            # Check if it was a validation error or registration error
            # Since batch_register_symbols catches exceptions, we need to re-validate
            # to determine the exact error type
            try:
                # Try to register individually to get specific error
                await auto_register_symbol(session, symbol)
            except ValueError as e:
                # Symbol doesn't exist in Yahoo Finance
                logger.warning(f"Symbol validation failed: {e}")
                raise SymbolNotFoundError(symbol, source="yfinance")
            except RuntimeError as e:
                # Database registration failed
                logger.error(f"Symbol registration failed: {e}")
                raise SymbolRegistrationError(symbol, str(e))
            except Exception as e:
                # Unexpected error
                logger.error(f"Unexpected error in symbol registration for {symbol}: {e}", exc_info=True)
                raise SymbolRegistrationError(symbol, f"Unexpected error: {str(e)}")
        else:
            logger.debug(f"Symbol {symbol} is available (existing or newly registered)")


from app.services.profiling import profile_function

@router.get("/prices", response_model=List[PriceRowOut])
@profile_function("get_prices_api")
async def get_prices(
    symbols: str = Query(..., description="Comma-separated symbols"),
    date_from: str = Query(..., alias="from", description="Start date (YYYY-MM-DD)"),
    date_to: str = Query(..., alias="to", description="End date (YYYY-MM-DD)"),
    auto_fetch: bool = Query(True, description="Auto-fetch all available data if missing"),  # 追加
    session=Depends(get_session),
):
    # Parse dates
    try:
        date_from_parsed = date.fromisoformat(date_from)
        date_to_parsed = date.fromisoformat(date_to)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {e}")
    
    # --- validation ---
    if date_to_parsed < date_from_parsed:
        raise HTTPException(status_code=422, detail="invalid date range")
    symbols_list = _parse_and_validate_symbols(symbols)
    if not symbols_list:
        return []

    # --- auto-registration (if enabled) ---
    if settings.ENABLE_AUTO_REGISTRATION:
        logger.info(f"Checking auto-registration for symbols: {symbols_list}")
        await ensure_symbols_registered(session, symbols_list)

    # --- orchestration (欠損検出・再取得は内部サービスに委譲してもよい) ---
    # 1) 欠損カバレッジを確認し、不足分＋直近N日を取得してUPSERT（冪等）
    t0 = time.perf_counter()
    # Clamp future 'to' to today to avoid yfinance/pandas overflow
    effective_to = date_to_parsed
    try:
        today = date.today()
        if effective_to > today:
            effective_to = today
    except Exception:
        pass

    # === ここから新規追加 ===
    cached_results = []
    uncached_symbols = []
    
    # バッチキャッシュチェック（TASK-SPD-005: 複数シンボルのキャッシュをバッチでチェック）
    if settings.ENABLE_CACHE:
        try:
            from app.services.cache import get_cache
            cache = get_cache()
            
            # 単一のバッチキャッシュキーを作成（N+1問題の解決）
            batch_cache_key = f"prices:batch:{','.join(sorted(symbols_list))}:{date_from_parsed}:{effective_to}"
            cached_batch_data = await cache.get(batch_cache_key)
            
            if cached_batch_data:
                # バッチキャッシュヒット
                cached_results.extend(cached_batch_data)
                logger.info(f"Batch cache hit for {len(symbols_list)} symbols")
            else:
                # バッチキャッシュミス - 個別キャッシュをチェック
                cache_keys = [f"prices:{symbol}:{date_from_parsed}:{effective_to}" for symbol in symbols_list]
                cached_data_dict = await cache.get_multi(cache_keys)
                
                # キャッシュヒット/ミスを分類
                for symbol, cache_key in zip(symbols_list, cache_keys):
                    cached_data = cached_data_dict.get(cache_key)
                    if cached_data:
                        # 個別キャッシュヒット
                        cached_results.extend(cached_data)
                        logger.debug(f"Individual cache hit for {symbol}")
                    else:
                        # キャッシュミス
                        uncached_symbols.append(symbol)
                        logger.debug(f"Cache miss for {symbol}")
                
                # 全て個別キャッシュにあれば即座に返却
                if not uncached_symbols:
                    logger.info(f"All {len(symbols_list)} symbols from individual cache")
                    # バッチキャッシュに保存
                    await cache.set(batch_cache_key, cached_results)
                    return cached_results
                
        except ImportError:
            # キャッシュモジュールがない場合は全て取得
            uncached_symbols = symbols_list
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
            uncached_symbols = symbols_list
    else:
        uncached_symbols = symbols_list
    
    # === 並行処理版の使用（TASK-007の成果を利用） ===
    if auto_fetch and uncached_symbols:
        # ensure_coverage_parallelが存在すれば使用、なければ通常版
        try:
            from app.db.queries import ensure_coverage_parallel
            await ensure_coverage_parallel(
                session=session,
                symbols=uncached_symbols,
                date_from=date_from_parsed,
                date_to=effective_to,
                refetch_days=settings.YF_REFETCH_DAYS,
            )
            logger.info(f"Used parallel coverage for {len(uncached_symbols)} symbols")
        except ImportError:
            # 並行版がなければ既存の逐次版を使用
            await queries.ensure_coverage(
                session=session,
                symbols=uncached_symbols,
                date_from=date_from,
                date_to=effective_to,
                refetch_days=settings.YF_REFETCH_DAYS,
            )
    else:
        # 自動取得なしの場合
        await queries.ensure_coverage(
            session=session,
            symbols=symbols_list,
            date_from=date_from_parsed,
            date_to=effective_to,
            refetch_days=settings.YF_REFETCH_DAYS,
        )

    # 2) 透過解決済み結果を取得
    rows = []
    cache_updates = {}  # バッチキャッシュ更新用
    
    for symbol in uncached_symbols:
        symbol_rows = await queries.get_prices_resolved(
            session=session,
            symbols=[symbol],
            date_from=date_from_parsed,
            date_to=effective_to,
        )
        rows.extend(symbol_rows)
        
        # キャッシュ更新データを準備（ENABLE_CACHEがTrueの場合）
        if settings.ENABLE_CACHE and symbol_rows:
            cache_key = f"prices:{symbol}:{date_from_parsed}:{effective_to}"
            cache_updates[cache_key] = symbol_rows
    
    # バッチキャッシュ保存（TASK-SPD-005: Redisパイプラインを使用）
    if settings.ENABLE_CACHE and cache_updates:
        try:
            await cache.set_multi(cache_updates)
            # バッチキャッシュも保存
            await cache.set(batch_cache_key, rows)
            logger.debug(f"Batch cached {len(cache_updates)} symbol results")
        except Exception as e:
            logger.warning(f"Failed to batch cache updates: {e}")
    
    # キャッシュ済みと新規取得を結合
    if cached_results:
        rows.extend(cached_results)
    
    # ソート（日付、シンボル順）
    rows.sort(key=lambda r: (r["date"], r["symbol"]))

    if len(rows) > settings.API_MAX_ROWS:
        raise HTTPException(status_code=413, detail="response too large")
    dt_ms = int((time.perf_counter() - t0) * 1000)
    cache_hit_count = len(cached_results) if settings.ENABLE_CACHE else 0
    
    logger.info(
        "prices served",
        extra=dict(
            symbols=symbols_list,
            date_from=str(date_from_parsed),
            date_to=str(effective_to),
            rows=len(rows),
            duration_ms=dt_ms,
            cache_hits=cache_hit_count,
            cache_hit_ratio=cache_hit_count/len(symbols_list) if symbols_list else 0,
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
        
        # Build delete query
        query = "DELETE FROM prices WHERE symbol = :symbol"
        params = {"symbol": normalized_symbol}
        
        if date_from_parsed:
            query += " AND date >= :date_from"
            params["date_from"] = date_from_parsed
        
        if date_to_parsed:
            query += " AND date <= :date_to"
            params["date_to"] = date_to_parsed
        
        # Log the deletion attempt
        logger.warning(
            f"Price data deletion requested for symbol {normalized_symbol}",
            extra={
                "symbol": normalized_symbol,
                "date_from": str(date_from_parsed) if date_from_parsed else None,
                "date_to": str(date_to_parsed) if date_to_parsed else None,
                "query": query,
                "timestamp": datetime.now(timezone.utc).isoformat()
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
                "date_from": str(date_from_parsed) if date_from_parsed else None,
                "date_to": str(date_to_parsed) if date_to_parsed else None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
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
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                }
            }
        )


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
