"""Automatic symbol registration service."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.services.symbol_validator import validate_symbol_exists_async
from app.services.normalize import normalize_symbol

logger = logging.getLogger(__name__)


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
        logger.error(f"Database error checking symbol existence for {symbol}: {e}")
        raise


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
        logger.error(f"Database error inserting symbol {symbol}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error inserting symbol {symbol}: {e}", exc_info=True)
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
        logger.info(f"Validating new symbol {normalized_symbol} with Yahoo Finance")
        
        if not await validate_symbol_exists_async(normalized_symbol):
            error_msg = f"Symbol '{normalized_symbol}' does not exist in Yahoo Finance"
            logger.warning(error_msg)
            raise ValueError(error_msg)
        
        # Step 4: Insert symbol into database
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
    except Exception as e:
        error_msg = f"Auto-registration failed for symbol '{symbol}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e


async def batch_register_symbols(
    session: AsyncSession, 
    symbols: List[str]
) -> Dict[str, bool]:
    """
    Register multiple symbols in batch with parallel processing.
    
    This function processes multiple symbols concurrently and returns the results
    for each one individually.
    
    Parameters
    ----------
    session : AsyncSession
        Database session
    symbols : List[str]
        List of symbols to register
        
    Returns
    -------
    Dict[str, bool]
        Dictionary mapping each symbol to its registration result
        True = successfully registered/already existed
        False = failed to register
        
    Note
    ----
    This function does not raise exceptions for individual symbol failures.
    Check the return dictionary to see which symbols failed.
    """
    async def register_one(symbol: str) -> tuple[str, bool]:
        """Register a single symbol and return result."""
        try:
            result = await auto_register_symbol(session, symbol)
            return symbol, result
        except (ValueError, RuntimeError) as e:
            logger.error(f"Failed to register {symbol}: {e}")
            return symbol, False
    
    # Process all symbols sequentially to avoid concurrent session usage
    results = []
    for symbol in symbols:
        result = await register_one(symbol)
        results.append(result)
    
    # Convert to dictionary
    result_dict = dict(results)
    
    success_count = sum(1 for success in result_dict.values() if success)
    logger.info(f"Batch registration completed: {success_count}/{len(symbols)} successful")
    
    return result_dict



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
    from app.api.errors import SymbolNotFoundError, SymbolRegistrationError

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


__all__ = [
    "symbol_exists_in_db",
    "insert_symbol", 
    "auto_register_symbol",
    "batch_register_symbols",
    "ensure_symbols_registered"
]
