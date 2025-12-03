"""Automatic symbol registration service."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
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


async def symbol_exists_in_db(session: AsyncSession, symbol: str) -> bool:
    """
    Check if a symbol already exists in the symbols table.
    
    Parameters
    ----------
    session : AsyncSession
        Database session
    symbol : str
        Symbol to check (should be normalized)
        
    Returns
    -------
    bool
        True if symbol exists in database, False otherwise
    """
    for attempt in range(MAX_DB_RETRIES):
        try:
            result = await session.execute(
                text("SELECT COUNT(*) FROM symbols WHERE symbol = :symbol"),
                {"symbol": symbol}
            )
            count = result.scalar()
            exists = count > 0
            
            if exists:
                logger.debug(f"Symbol {symbol} already exists in database")
            else:
                logger.debug(f"Symbol {symbol} not found in database")
                
            return exists
            
        except SQLAlchemyError as e:
            error_msg = str(e)
            is_transient = "connection was closed" in error_msg or "connection" in error_msg.lower()
            
            if is_transient and attempt < MAX_DB_RETRIES - 1:
                logger.warning(f"Transient DB error checking symbol {symbol} (attempt {attempt + 1}): {e}")
                await asyncio.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            
            logger.error(f"Database error checking symbol existence for {symbol}: {e}")
            raise
    
    # Should not reach here, but just in case
    raise SQLAlchemyError(f"Failed to check symbol {symbol} after {MAX_DB_RETRIES} attempts")


async def insert_symbol(session: AsyncSession, symbol: str) -> bool:
    """
    Insert a new symbol into the symbols table with minimal information.
    
    Parameters
    ----------
    session : AsyncSession
        Database session
    symbol : str
        Symbol to insert (should be normalized)
        
    Returns
    -------
    bool
        True if insertion was successful, False otherwise
    """
    for attempt in range(MAX_DB_RETRIES):
        try:
            # Insert with minimal required information
            # name, exchange, currency will be NULL and can be updated later
            result = await session.execute(
                text("""
                    INSERT INTO symbols (symbol, is_active, first_date, last_date, created_at)
                    VALUES (:symbol, true, NULL, NULL, :created_at)
                    ON CONFLICT (symbol) DO NOTHING
                    RETURNING symbol
                """),
                {
                    "symbol": symbol,
                    "created_at": datetime.now(UTC)
                }
            )
            
            # Check if a row was actually inserted
            inserted_symbol = result.fetchone()
            
            if inserted_symbol:
                logger.info(f"Successfully inserted symbol {symbol} into database")
                return True
            else:
                # Symbol already existed (ON CONFLICT DO NOTHING was triggered)
                logger.debug(f"Symbol {symbol} already exists, insertion skipped")
                return True  # Still consider this a success
                
        except IntegrityError as e:
            logger.error(f"Integrity error inserting symbol {symbol}: {e}")
            return False
        except SQLAlchemyError as e:
            error_msg = str(e)
            is_transient = "connection was closed" in error_msg or "connection" in error_msg.lower()
            
            if is_transient and attempt < MAX_DB_RETRIES - 1:
                logger.warning(f"Transient DB error inserting symbol {symbol} (attempt {attempt + 1}): {e}")
                await asyncio.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            
            logger.error(f"Database error inserting symbol {symbol}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error inserting symbol {symbol}: {e}", exc_info=True)
            return False
    
    # Should not reach here normally
    logger.error(f"Failed to insert symbol {symbol} after {MAX_DB_RETRIES} attempts")
    return False


async def auto_register_symbol(session: AsyncSession, symbol: str) -> bool:
    """
    Automatically register a symbol if it doesn't exist in the database.
    
    This function performs the complete auto-registration workflow:
    1. Normalize the symbol
    2. Check if it already exists in the database
    3. If not, validate it exists in Yahoo Finance
    4. If valid, insert it into the symbols table
    
    Parameters
    ----------
    session : AsyncSession
        Database session
    symbol : str
        Raw symbol to register
        
    Returns
    -------
    bool
        True if symbol is available (already existed or was successfully registered)
        
    Raises
    ------
    ValueError
        If symbol doesn't exist in Yahoo Finance
    RuntimeError
        If database operations fail
    """
    try:
        # Step 1: Normalize symbol
        normalized_symbol = normalize_symbol(symbol)
        logger.debug(f"Normalized symbol: {symbol} -> {normalized_symbol}")
        
        # Step 2: Check if already exists in database
        if await symbol_exists_in_db(session, normalized_symbol):
            logger.debug(f"Symbol {normalized_symbol} already registered, skipping")
            return True
        
        # Step 3: Validate symbol exists in Yahoo Finance
        # Note: This is done BEFORE any pending DB operations to avoid
        # connection timeouts during external API calls
        logger.info(f"Validating new symbol {normalized_symbol} with Yahoo Finance")
        
        yf_valid = await validate_symbol_exists_async(normalized_symbol)
        if not yf_valid:
            error_msg = f"Symbol '{normalized_symbol}' does not exist in Yahoo Finance"
            logger.warning(error_msg)
            raise ValueError(error_msg)
        
        # Step 4: Insert symbol into database
        # At this point, we've validated with YF so DB insert should be quick
        logger.info(f"Registering new symbol {normalized_symbol}")
        
        if not await insert_symbol(session, normalized_symbol):
            error_msg = f"Failed to insert symbol '{normalized_symbol}' into database"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        logger.info(f"Successfully auto-registered symbol {normalized_symbol}")
        return True
        
    except ValueError:
        # Re-raise validation errors (symbol doesn't exist)
        raise
    except RuntimeError:
        # Re-raise runtime errors (DB failures)
        raise
    except SQLAlchemyError as e:
        # Database connection errors
        error_msg = f"Database error during auto-registration for symbol '{symbol}': {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = f"Auto-registration failed for symbol '{symbol}': {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


async def batch_register_symbols(
    session: AsyncSession, 
    symbols: List[str]
) -> Dict[str, Tuple[bool, Optional[str]]]:
    """
    Register multiple symbols in batch with sequential processing.
    
    This function processes multiple symbols sequentially and returns the results
    for each one individually, including error information for failures.
    
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
        
    Note
    ----
    This function does not raise exceptions for individual symbol failures.
    Check the return dictionary to see which symbols failed.
    """
    async def register_one(symbol: str) -> Tuple[str, bool, Optional[str]]:
        """Register a single symbol and return result with error type."""
        try:
            result = await auto_register_symbol(session, symbol)
            return symbol, result, None
        except ValueError as e:
            logger.error(f"Failed to register {symbol} (validation): {e}")
            return symbol, False, "validation"
        except RuntimeError as e:
            logger.error(f"Failed to register {symbol} (registration): {e}")
            return symbol, False, "registration"
        except Exception as e:
            logger.error(f"Failed to register {symbol} (unknown): {e}")
            return symbol, False, "registration"
    
    # Process all symbols sequentially to avoid concurrent session usage
    results: Dict[str, Tuple[bool, Optional[str]]] = {}
    for symbol in symbols:
        sym, success, error_type = await register_one(symbol)
        results[sym] = (success, error_type)
    
    success_count = sum(1 for success, _ in results.values() if success)
    logger.info(f"Batch registration completed: {success_count}/{len(symbols)} successful")
    
    return results


async def ensure_symbols_registered(
    session: AsyncSession, 
    symbols: List[str]
) -> None:
    """
    Ensure all symbols are registered in the database.
    
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
    from app.api.errors import SymbolNotFoundError, SymbolRegistrationError

    # Use batch registration - now returns error type info
    registration_results = await batch_register_symbols(session, symbols)
    
    # Check results and raise appropriate errors
    # We use the error_type from the first attempt to avoid re-trying with
    # potentially invalid session state
    for symbol, (success, error_type) in registration_results.items():
        if not success:
            if error_type == "validation":
                # Symbol doesn't exist in Yahoo Finance
                logger.warning(f"Symbol {symbol} not found in Yahoo Finance")
                raise SymbolNotFoundError(symbol, source="yfinance")
            else:
                # Database registration failed
                logger.error(f"Symbol {symbol} registration failed (DB error)")
                raise SymbolRegistrationError(
                    symbol, 
                    f"Database registration failed for symbol '{symbol}'. Please retry."
                )
        else:
            logger.debug(f"Symbol {symbol} is available (existing or newly registered)")


__all__ = [
    "symbol_exists_in_db",
    "insert_symbol", 
    "auto_register_symbol",
    "batch_register_symbols",
    "ensure_symbols_registered"
]
