"""API package for FastAPI endpoints and utilities."""

# Import dependencies (avoiding circular imports)
try:
    from .deps import get_db, get_settings
except ImportError:
    pass

try:
    from .errors import (
        JobNotFoundError,
        JobAlreadyExistsError, 
        JobLimitExceededError,
        InvalidDateRangeError,
        TooManySymbolsError,
        SymbolNotFoundError,
        DataFetchError,
        ExportError,
        DatabaseError
    )
except ImportError:
    pass

__all__ = [
    "get_db",
    "get_settings",
    "JobNotFoundError", 
    "JobAlreadyExistsError",
    "JobLimitExceededError",
    "InvalidDateRangeError",
    "TooManySymbolsError", 
    "SymbolNotFoundError",
    "DataFetchError",
    "ExportError", 
    "DatabaseError",
]