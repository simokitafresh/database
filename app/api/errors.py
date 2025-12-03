from typing import Any, cast
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

# Import asyncpg exceptions for better error handling
try:
    import asyncpg.exceptions as asyncpg_exc
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False

logger = logging.getLogger(__name__)


# Error codes for the API
JOB_NOT_FOUND = "JOB_NOT_FOUND"
JOB_ALREADY_EXISTS = "JOB_ALREADY_EXISTS"
JOB_LIMIT_EXCEEDED = "JOB_LIMIT_EXCEEDED"
INVALID_DATE_RANGE = "INVALID_DATE_RANGE"
TOO_MANY_SYMBOLS = "TOO_MANY_SYMBOLS"
SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
SYMBOL_NOT_EXISTS = "SYMBOL_NOT_EXISTS"
SYMBOL_REGISTRATION_FAILED = "SYMBOL_REGISTRATION_FAILED"
DATA_FETCH_ERROR = "DATA_FETCH_ERROR"
EXPORT_ERROR = "EXPORT_ERROR"
DATABASE_ERROR = "DATABASE_ERROR"
DATABASE_CONNECTION_ERROR = "DATABASE_CONNECTION_ERROR"


class JobNotFoundError(HTTPException):
    """Exception raised when a job is not found."""
    def __init__(self, job_id: str):
        super().__init__(
            status_code=404,
            detail={"code": JOB_NOT_FOUND, "message": f"Job {job_id} not found"}
        )


class JobAlreadyExistsError(HTTPException):
    """Exception raised when trying to create a job that already exists."""
    def __init__(self, job_id: str):
        super().__init__(
            status_code=409,
            detail={"code": JOB_ALREADY_EXISTS, "message": f"Job {job_id} already exists"}
        )


class JobLimitExceededError(HTTPException):
    """Exception raised when job limit is exceeded."""
    def __init__(self, limit: int):
        super().__init__(
            status_code=429,
            detail={"code": JOB_LIMIT_EXCEEDED, "message": f"Job limit exceeded (max: {limit})"}
        )


class InvalidDateRangeError(HTTPException):
    """Exception raised when date range is invalid."""
    def __init__(self, message: str = "Invalid date range"):
        super().__init__(
            status_code=400,
            detail={"code": INVALID_DATE_RANGE, "message": message}
        )


class TooManySymbolsError(HTTPException):
    """Exception raised when too many symbols are requested."""
    def __init__(self, count: int, limit: int):
        super().__init__(
            status_code=400,
            detail={"code": TOO_MANY_SYMBOLS, "message": f"Too many symbols: {count} (max: {limit})"}
        )


class SymbolNotFoundError(HTTPException):
    """Exception raised when a symbol is not found."""
    def __init__(self, symbol: str, source: str = "database"):
        if source == "yfinance":
            message = f"Symbol '{symbol}' does not exist in Yahoo Finance"
            code = SYMBOL_NOT_EXISTS
        else:
            message = f"Symbol '{symbol}' not found in database"
            code = SYMBOL_NOT_FOUND
            
        super().__init__(
            status_code=404,
            detail={
                "code": code, 
                "message": message, 
                "symbol": symbol,
                "source": source
            }
        )


class SymbolRegistrationError(HTTPException):
    """Exception raised when automatic symbol registration fails."""
    def __init__(self, symbol: str, reason: str):
        super().__init__(
            status_code=500,
            detail={
                "code": SYMBOL_REGISTRATION_FAILED,
                "message": f"Failed to auto-register symbol '{symbol}': {reason}",
                "symbol": symbol,
                "reason": reason
            }
        )


class DataFetchError(HTTPException):
    """Exception raised when data fetching fails."""
    def __init__(self, symbol: str, message: str):
        super().__init__(
            status_code=500,
            detail={"code": DATA_FETCH_ERROR, "message": f"Failed to fetch {symbol}: {message}"}
        )


class ExportError(HTTPException):
    """Exception raised when export operation fails."""
    def __init__(self, message: str = "Export operation failed"):
        super().__init__(
            status_code=500,
            detail={"code": EXPORT_ERROR, "message": message}
        )


class DatabaseError(HTTPException):
    """Exception raised when database operation fails."""
    def __init__(self, message: str = "Database operation failed"):
        super().__init__(
            status_code=500,
            detail={"code": DATABASE_ERROR, "message": message}
        )


class DatabaseConnectionError(HTTPException):
    """Exception raised when database connection fails after retries."""
    def __init__(self, message: str = "Database connection temporarily unavailable"):
        super().__init__(
            status_code=503,
            detail={
                "code": DATABASE_CONNECTION_ERROR, 
                "message": message,
                "retry_after": 5
            }
        )


def raise_http_error(status_code: int, message: str) -> None:
    """Raise an HTTPException with a unified error structure.

    Parameters
    ----------
    status_code: int
        HTTP status code to raise.
    message: str
        Human readable error message.
    """
    raise HTTPException(status_code=status_code, detail=message)


def _http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    payload = {"error": {"code": str(exc.status_code), "message": message}}
    return JSONResponse(payload, status_code=exc.status_code)


def _validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    message = exc.errors()[0]["msg"] if exc.errors() else "Validation error"
    payload = {"error": {"code": "422", "message": message}}
    return JSONResponse(payload, status_code=422)


def init_error_handlers(app: FastAPI) -> None:
    """Register exception handlers on the given FastAPI app."""
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, cast(Any, _validation_exception_handler))

    async def _not_found(request: Request, exc: HTTPException):
        return _http_exception_handler(request, exc)

    app.add_exception_handler(404, _not_found)
    
    # Handle SQLAlchemy connection errors gracefully
    async def _sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        error_msg = str(exc).lower()
        is_connection_error = any(pattern in error_msg for pattern in [
            "connection was closed",
            "connection does not exist", 
            "connection refused",
            "connection reset",
            "server closed",
        ])
        
        if is_connection_error:
            payload = {
                "error": {
                    "code": DATABASE_CONNECTION_ERROR,
                    "message": "Database connection temporarily unavailable. Please retry.",
                    "retry_after": 5
                }
            }
            return JSONResponse(payload, status_code=503, headers={"Retry-After": "5"})
        else:
            payload = {
                "error": {
                    "code": DATABASE_ERROR,
                    "message": "Database operation failed"
                }
            }
            return JSONResponse(payload, status_code=500)
    
    app.add_exception_handler(SQLAlchemyError, cast(Any, _sqlalchemy_error_handler))
    
    # Handle asyncpg connection errors directly (they may not be wrapped by SQLAlchemy)
    if HAS_ASYNCPG:
        async def _asyncpg_error_handler(request: Request, exc: Exception) -> JSONResponse:
            error_msg = str(exc).lower()
            logger.warning(f"asyncpg error: {exc}")
            
            is_connection_error = any(pattern in error_msg for pattern in [
                "connection was closed",
                "connection does not exist",
                "connection refused",
                "connection reset",
                "server closed",
                "connection lost",
            ])
            
            if is_connection_error:
                payload = {
                    "error": {
                        "code": DATABASE_CONNECTION_ERROR,
                        "message": "Database connection temporarily unavailable. Please retry.",
                        "retry_after": 5
                    }
                }
                return JSONResponse(payload, status_code=503, headers={"Retry-After": "5"})
            else:
                payload = {
                    "error": {
                        "code": DATABASE_ERROR,
                        "message": f"Database operation failed: {type(exc).__name__}"
                    }
                }
                return JSONResponse(payload, status_code=500)
        
        # Register handlers for specific asyncpg exceptions
        app.add_exception_handler(asyncpg_exc.ConnectionDoesNotExistError, cast(Any, _asyncpg_error_handler))
        app.add_exception_handler(asyncpg_exc.InterfaceError, cast(Any, _asyncpg_error_handler))
        app.add_exception_handler(asyncpg_exc.PostgresConnectionError, cast(Any, _asyncpg_error_handler))
