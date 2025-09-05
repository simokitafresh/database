"""Symbol validation service using Yahoo Finance API."""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional
from urllib.error import HTTPError as URLlibHTTPError

import yfinance as yf
from requests.exceptions import HTTPError as RequestsHTTPError, Timeout, ConnectionError

from app.core.config import settings

logger = logging.getLogger(__name__)


def validate_symbol_exists(symbol: str, timeout: Optional[int] = None) -> bool:
    """
    Validate if a symbol exists in Yahoo Finance.
    
    Parameters
    ----------
    symbol : str
        Ticker symbol to validate
    timeout : int, optional
        Timeout in seconds (default: YF_VALIDATE_TIMEOUT from settings)
        
    Returns
    -------
    bool
        True if symbol exists, False otherwise
    """
    try:
        if timeout is None:
            timeout = getattr(settings, 'YF_VALIDATE_TIMEOUT', 10)
        
        logger.debug(f"Validating symbol existence: {symbol}")
        
        # Create ticker object
        ticker = yf.Ticker(symbol)
        
        # Try to get basic info - this will raise HTTPError if symbol doesn't exist
        info = ticker.info
        
        # Check if we got meaningful data
        if not info or not isinstance(info, dict):
            logger.warning(f"Symbol {symbol}: Empty or invalid info response")
            return False
            
        # Yahoo Finance sometimes returns empty dict for invalid symbols
        if len(info) < 5:  # Valid symbols typically have many fields
            logger.warning(f"Symbol {symbol}: Insufficient info data (possibly invalid)")
            return False
            
        # Check for symbol field as additional validation
        symbol_from_info = info.get('symbol')
        if symbol_from_info and symbol_from_info.upper() != symbol.upper():
            logger.warning(f"Symbol mismatch: requested {symbol}, got {symbol_from_info}")
            return False
            
        logger.info(f"Symbol {symbol} validated successfully")
        return True
        
    except (URLlibHTTPError, RequestsHTTPError) as e:
        if hasattr(e, 'code') and e.code == 404:
            logger.info(f"Symbol {symbol} not found in Yahoo Finance (404)")
            return False
        elif hasattr(e, 'response') and e.response.status_code == 404:
            logger.info(f"Symbol {symbol} not found in Yahoo Finance (404)")
            return False
        else:
            logger.error(f"HTTP error validating {symbol}: {e}")
            return False
    except (Timeout, ConnectionError) as e:
        logger.error(f"Network error validating {symbol}: {e}")
        return False
    except KeyError as e:
        logger.warning(f"Symbol {symbol}: Missing expected data field: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error validating {symbol}: {e}", exc_info=True)
        return False


def get_symbol_info(symbol: str, timeout: Optional[int] = None) -> Dict[str, Any]:
    """
    Get detailed information about a symbol's existence and basic data.
    
    Parameters
    ----------
    symbol : str
        Ticker symbol to check
    timeout : int, optional
        Timeout in seconds
        
    Returns
    -------
    Dict[str, Any]
        Dictionary containing:
        - symbol: The requested symbol
        - exists: Boolean indicating if symbol exists
        - error: Error message if validation failed, None otherwise
        - info: Basic symbol info if available, None otherwise
    """
    result = {
        "symbol": symbol,
        "exists": False,
        "error": None,
        "info": None
    }
    
    try:
        if timeout is None:
            timeout = getattr(settings, 'YF_VALIDATE_TIMEOUT', 10)
            
        logger.debug(f"Getting symbol info for: {symbol}")
        
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        if not info or not isinstance(info, dict) or len(info) < 5:
            result["error"] = f"Symbol '{symbol}' not found in Yahoo Finance"
            return result
            
        # Extract basic information
        basic_info = {
            "symbol": info.get("symbol", symbol),
            "shortName": info.get("shortName"),
            "longName": info.get("longName"), 
            "exchange": info.get("exchange"),
            "currency": info.get("currency"),
            "marketCap": info.get("marketCap"),
            "sector": info.get("sector"),
            "industry": info.get("industry")
        }
        
        result["exists"] = True
        result["info"] = basic_info
        logger.info(f"Symbol {symbol} info retrieved successfully")
        
    except (URLlibHTTPError, RequestsHTTPError) as e:
        if (hasattr(e, 'code') and e.code == 404) or (hasattr(e, 'response') and e.response.status_code == 404):
            result["error"] = f"Symbol '{symbol}' not found in Yahoo Finance"
        else:
            result["error"] = f"HTTP error retrieving {symbol}: {str(e)}"
    except (Timeout, ConnectionError) as e:
        result["error"] = f"Network timeout or connection error for {symbol}: {str(e)}"
    except Exception as e:
        result["error"] = f"Unexpected error retrieving {symbol}: {str(e)}"
        logger.error(f"Unexpected error in get_symbol_info for {symbol}: {e}", exc_info=True)
    
    return result


__all__ = ["validate_symbol_exists", "get_symbol_info"]
