"""Service for managing price data retrieval and manipulation."""

import logging
import time
from datetime import date, datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import HTTPException

from app.core.config import settings
from app.db import queries
from app.services.normalize import normalize_symbol
from app.services.auto_register import ensure_symbols_registered

logger = logging.getLogger(__name__)


class PriceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_prices(
        self,
        symbols_list: List[str],
        date_from: date,
        date_to: date,
        auto_fetch: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Orchestrate price retrieval:
        1. Auto-register symbols if enabled
        2. Check cache (batch/individual)
        3. Ensure coverage (fetch missing data)
        4. Retrieve resolved prices from DB
        5. Update cache
        6. Return sorted results
        """
        # --- auto-registration (if enabled) ---
        if settings.ENABLE_AUTO_REGISTRATION:
            logger.info(f"Checking auto-registration for symbols: {symbols_list}")
            await ensure_symbols_registered(self.session, symbols_list)

        # Clamp future 'to' to today to avoid yfinance/pandas overflow
        effective_to = date_to
        try:
            today = date.today()
            if effective_to > today:
                effective_to = today
        except Exception:
            pass

        cached_results = []
        uncached_symbols = []
        
        # バッチキャッシュチェック
        if settings.ENABLE_CACHE:
            try:
                from app.services.cache import get_cache
                cache = get_cache()
                
                # 単一のバッチキャッシュキーを作成
                batch_cache_key = f"prices:batch:{','.join(sorted(symbols_list))}:{date_from}:{effective_to}"
                cached_batch_data = await cache.get(batch_cache_key)
                
                if cached_batch_data:
                    cached_results.extend(cached_batch_data)
                    logger.info(f"Batch cache hit for {len(symbols_list)} symbols")
                else:
                    # バッチキャッシュミス - 個別キャッシュをチェック
                    cache_keys = [f"prices:{symbol}:{date_from}:{effective_to}" for symbol in symbols_list]
                    cached_data_dict = await cache.get_multi(cache_keys)
                    
                    for symbol, cache_key in zip(symbols_list, cache_keys):
                        cached_data = cached_data_dict.get(cache_key)
                        if cached_data:
                            cached_results.extend(cached_data)
                            logger.debug(f"Individual cache hit for {symbol}")
                        else:
                            uncached_symbols.append(symbol)
                            logger.debug(f"Cache miss for {symbol}")
                    
                    if not uncached_symbols:
                        logger.info(f"All {len(symbols_list)} symbols from individual cache")
                        await cache.set(batch_cache_key, cached_results)
                        return cached_results
                    
            except ImportError:
                uncached_symbols = symbols_list
            except Exception as e:
                logger.warning(f"Cache check failed: {e}")
                uncached_symbols = symbols_list
        else:
            uncached_symbols = symbols_list
        
        # --- Ensure Coverage ---
        if auto_fetch and uncached_symbols:
            try:
                from app.db.queries import ensure_coverage_parallel
                await ensure_coverage_parallel(
                    session=self.session,
                    symbols=uncached_symbols,
                    date_from=date_from,
                    date_to=effective_to,
                    refetch_days=settings.YF_REFETCH_DAYS,
                )
                logger.info(f"Used parallel coverage for {len(uncached_symbols)} symbols")
            except ImportError:
                await queries.ensure_coverage(
                    session=self.session,
                    symbols=uncached_symbols,
                    date_from=date_from,
                    date_to=effective_to,
                    refetch_days=settings.YF_REFETCH_DAYS,
                )
        elif not auto_fetch:
             await queries.ensure_coverage(
                session=self.session,
                symbols=symbols_list,
                date_from=date_from,
                date_to=effective_to,
                refetch_days=settings.YF_REFETCH_DAYS,
            )

        # --- Retrieve Data ---
        rows = []
        cache_updates = {}
        
        for symbol in uncached_symbols:
            symbol_rows = await queries.get_prices_resolved(
                session=self.session,
                symbols=[symbol],
                date_from=date_from,
                date_to=effective_to,
            )
            rows.extend(symbol_rows)
            
            if settings.ENABLE_CACHE and symbol_rows:
                cache_key = f"prices:{symbol}:{date_from}:{effective_to}"
                cache_updates[cache_key] = symbol_rows
        
        # --- Update Cache ---
        if settings.ENABLE_CACHE and cache_updates:
            try:
                from app.services.cache import get_cache
                cache = get_cache()
                await cache.set_multi(cache_updates)
                # Update batch cache key if we have full results now
                # Re-construct full result set for batch cache
                full_results = rows + cached_results
                batch_cache_key = f"prices:batch:{','.join(sorted(symbols_list))}:{date_from}:{effective_to}"
                await cache.set(batch_cache_key, full_results)
                logger.debug(f"Batch cached {len(cache_updates)} symbol results")
            except Exception as e:
                logger.warning(f"Failed to batch cache updates: {e}")
        
        if cached_results:
            rows.extend(cached_results)
        
        # Sort
        rows.sort(key=lambda r: (r["date"], r["symbol"]))
        
        return rows

    async def delete_prices(
        self,
        symbol: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> int:
        """Delete price data for a symbol."""
        normalized_symbol = normalize_symbol(symbol)
        
        query = "DELETE FROM prices WHERE symbol = :symbol"
        params = {"symbol": normalized_symbol}
        
        if date_from:
            query += " AND date >= :date_from"
            params["date_from"] = date_from
        
        if date_to:
            query += " AND date <= :date_to"
            params["date_to"] = date_to
            
        result = await self.session.execute(text(query), params)
        deleted_rows = result.rowcount
        await self.session.commit()
        
        return deleted_rows
