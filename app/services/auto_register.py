"""Automatic symbol registration service."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.services.symbol_validator import validate_symbol_exists_async
from app.services.normalize import normalize_symbol

logger = logging.getLogger(__name__)

# Retry configuration for transient connection errors
MAX_DB_RETRIES = 3
RETRY_DELAY_SECONDS = 0.5


async def get_existing_symbols(session: AsyncSession, symbols: List[str]) -> Set[str]:
    """
    Check which symbols already exist in the database (batch operation).
    
    Parameters
    ----------
    session : AsyncSession
        Database session
    symbols : List[str]
        List of symbols to check (should be normalized)
        
    Returns
    -------
    Set[str]
        Set of symbols that exist in the database
    """
    if not symbols:
        return set()
    
    for attempt in range(MAX_DB_RETRIES):
        try:
            result = await session.execute(
                text("SELECT symbol FROM symbols WHERE symbol = ANY(:symbols)"),
                {"symbols": symbols}
            )
            existing = {row[0] for row in result.fetchall()}
            logger.debug(f"Found {len(existing)} existing symbols out of {len(symbols)}")
            return existing
            
        except SQLAlchemyError as e:
            error_msg = str(e)
            is_transient = "connection was closed" in error_msg or "closed" in error_msg.lower()
            
            if is_transient and attempt < MAX_DB_RETRIES - 1:
                logger.warning(f"Transient DB error checking symbols (attempt {attempt + 1}): {e}")
                await asyncio.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            
            logger.error(f"Database error checking symbol existence: {e}")
            raise
    
    raise SQLAlchemyError(f"Failed to check symbols after {MAX_DB_RETRIES} attempts")


async def insert_symbols_batch(session: AsyncSession, symbols: List[str]) -> Dict[str, bool]:
    """
    Insert multiple symbols into the symbols table in a single batch operation.
    
    Parameters
    ----------
    session : AsyncSession
        Database session
    symbols : List[str]
        Symbols to insert (should be normalized)
        
    Returns
    -------
    Dict[str, bool]
        Dictionary mapping symbol to insertion success
    """
    if not symbols:
        return {}
    
    results = {}
    
    for attempt in range(MAX_DB_RETRIES):
        try:
            now = datetime.now(UTC)
            
            # Use batch insert with ON CONFLICT DO NOTHING
            # This handles concurrent insertions gracefully
            values_list = [{"symbol": sym, "created_at": now} for sym in symbols]
            
            for sym_data in values_list:
                try:
                    result = await session.execute(
                        text("""
                            INSERT INTO symbols (symbol, is_active, first_date, last_date, created_at)
                            VALUES (:symbol, true, NULL, NULL, :created_at)
                            ON CONFLICT (symbol) DO NOTHING
                            RETURNING symbol
                        """),
                        sym_data
                    )
                    inserted = result.fetchone()
                    results[sym_data["symbol"]] = True  # Success (inserted or already exists)
                    if inserted:
                        logger.info(f"Successfully inserted symbol {sym_data['symbol']}")
                    else:
                        logger.debug(f"Symbol {sym_data['symbol']} already exists")
                except IntegrityError:
                    results[sym_data["symbol"]] = True  # Already exists
                except SQLAlchemyError as e:
                    logger.error(f"Failed to insert {sym_data['symbol']}: {e}")
                    results[sym_data["symbol"]] = False
            
            return results
            
        except SQLAlchemyError as e:
            error_msg = str(e)
            is_transient = "connection was closed" in error_msg or "closed" in error_msg.lower()
            
            if is_transient and attempt < MAX_DB_RETRIES - 1:
                logger.warning(f"Transient DB error inserting symbols (attempt {attempt + 1}): {e}")
                await asyncio.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                results.clear()
                continue
            
            logger.error(f"Database error inserting symbols: {e}")
            # Mark all remaining as failed
            for sym in symbols:
                if sym not in results:
                    results[sym] = False
            return results
    
    # Should not reach here normally
    for sym in symbols:
        if sym not in results:
            results[sym] = False
    return results


async def batch_register_symbols(
    session: AsyncSession, 
    symbols: List[str]
) -> Dict[str, Tuple[bool, Optional[str]]]:
    """
    Register multiple symbols in batch with optimized DB/API separation.
    
    This function uses a three-phase approach to minimize connection timeout issues:
    1. Phase 1 (DB): Check which symbols already exist
    2. Phase 2 (External API): Validate missing symbols with Yahoo Finance
    3. Phase 3 (DB): Insert validated symbols
    
    This approach ensures external API calls don't hold DB connections open.
    
    Parameters
    ----------
    session : AsyncSession
        Database session
    symbols : List[str]
        List of symbols to register
        
    Returns
    -------
    Dict[str, Tuple[bool, Optional[str]]]
        Dictionary mapping each symbol to a tuple of:
        - success: True if registered/already existed, False if failed
        - error_type: 'validation' if YF validation failed, 'registration' if DB failed,
                      None if successful
    """
    if not symbols:
        return {}
    
    # Normalize all symbols first
    normalized_map = {sym: normalize_symbol(sym) for sym in symbols}
    normalized_symbols = list(set(normalized_map.values()))
    
    results: Dict[str, Tuple[bool, Optional[str]]] = {}
    
    # Phase 1: Check existing symbols (DB operation)
    try:
        existing_symbols = await get_existing_symbols(session, normalized_symbols)
        logger.debug(f"Phase 1: Found {len(existing_symbols)} existing symbols")
    except SQLAlchemyError as e:
        logger.error(f"Phase 1 failed - DB error checking existing symbols: {e}")
        # Mark all as registration failure
        for sym in symbols:
            results[sym] = (False, "registration")
        return results
    
    # Mark existing symbols as successful
    for sym, normalized in normalized_map.items():
        if normalized in existing_symbols:
            results[sym] = (True, None)
    
    # Get symbols that need registration
    missing_normalized = [s for s in normalized_symbols if s not in existing_symbols]
    
    if not missing_normalized:
        logger.info(f"All {len(symbols)} symbols already exist in database")
        return results
    
    logger.info(f"Phase 2: Validating {len(missing_normalized)} new symbols with Yahoo Finance")
    
    # Phase 2: Validate missing symbols with Yahoo Finance (External API)
    # This is done WITHOUT holding any DB connection
    validated_symbols: List[str] = []
    invalid_symbols: Set[str] = set()
    
    for normalized in missing_normalized:
        try:
            is_valid = await validate_symbol_exists_async(normalized)
            if is_valid:
                validated_symbols.append(normalized)
                logger.debug(f"Symbol {normalized} validated with Yahoo Finance")
            else:
                invalid_symbols.add(normalized)
                logger.warning(f"Symbol {normalized} not found in Yahoo Finance")
        except Exception as e:
            logger.error(f"Error validating symbol {normalized}: {e}")
            invalid_symbols.add(normalized)
    
    # Mark invalid symbols
    for sym, normalized in normalized_map.items():
        if normalized in invalid_symbols and sym not in results:
            results[sym] = (False, "validation")
    
    if not validated_symbols:
        logger.info("No new valid symbols to insert")
        # Fill in remaining results
        for sym in symbols:
            if sym not in results:
                results[sym] = (False, "validation")
        return results
    
    logger.info(f"Phase 3: Inserting {len(validated_symbols)} validated symbols")
    
    # Phase 3: Insert validated symbols (DB operation)
    try:
        insert_results = await insert_symbols_batch(session, validated_symbols)
        
        for sym, normalized in normalized_map.items():
            if sym not in results:
                if normalized in insert_results:
                    if insert_results[normalized]:
                        results[sym] = (True, None)
                    else:
                        results[sym] = (False, "registration")
                else:
                    # Should not happen, but handle gracefully
                    results[sym] = (False, "registration")
                    
    except SQLAlchemyError as e:
        logger.error(f"Phase 3 failed - DB error inserting symbols: {e}")
        for sym in symbols:
            if sym not in results:
                results[sym] = (False, "registration")
    
    success_count = sum(1 for success, _ in results.values() if success)
    logger.info(f"Batch registration completed: {success_count}/{len(symbols)} successful")
    
    return results


async def ensure_symbols_registered(
    session: AsyncSession, 
    symbols: List[str]
) -> None:
    """
    Ensure all symbols are registered in the database.
    
    Uses optimized three-phase batch registration to minimize connection issues.
    
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
    from app.api.errors import SymbolNotFoundError, SymbolRegistrationError

    # Use optimized batch registration
    registration_results = await batch_register_symbols(session, symbols)
    
    # Check results and raise appropriate errors
    for symbol, (success, error_type) in registration_results.items():
        if not success:
            if error_type == "validation":
                logger.warning(f"Symbol {symbol} not found in Yahoo Finance")
                raise SymbolNotFoundError(symbol, source="yfinance")
            else:
                logger.error(f"Symbol {symbol} registration failed (DB error)")
                raise SymbolRegistrationError(
                    symbol, 
                    f"Database registration failed for symbol '{symbol}'. Please retry."
                )
        else:
            logger.debug(f"Symbol {symbol} is available (existing or newly registered)")


# Keep legacy function for backward compatibility
async def auto_register_symbol(session: AsyncSession, symbol: str) -> bool:
    """
    Automatically register a single symbol if it doesn't exist.
    
    This is a convenience wrapper around batch_register_symbols for single-symbol use.
    For multiple symbols, use batch_register_symbols directly for better performance.
    """
    results = await batch_register_symbols(session, [symbol])
    
    if symbol not in results:
        raise RuntimeError(f"Failed to process symbol '{symbol}'")
    
    success, error_type = results[symbol]
    
    if not success:
        if error_type == "validation":
            raise ValueError(f"Symbol '{symbol}' does not exist in Yahoo Finance")
        else:
            raise RuntimeError(f"Failed to register symbol '{symbol}' in database")
    
    return True


__all__ = [
    "get_existing_symbols",
    "insert_symbols_batch", 
    "auto_register_symbol",
    "batch_register_symbols",
    "ensure_symbols_registered"
]
