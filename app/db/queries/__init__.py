"""Database access helpers for price coverage and retrieval.

This module is now a facade for:
- app.services.coverage_service
- app.core.locking
- app.db.queries.prices
- app.db.queries.symbols
"""

from app.core.locking import with_symbol_lock
from app.services.coverage_service import (
    ensure_coverage,
    ensure_coverage_unified,
    ensure_coverage_with_auto_fetch,
    ensure_coverage_parallel,
    find_earliest_available_date,
    fetch_prices_df,
)
from app.db.queries.prices import get_prices_resolved, _symbol_has_any_prices
from app.db.queries.symbols import list_symbols, LIST_SYMBOLS_SQL

__all__ = [
    "ensure_coverage",
    "ensure_coverage_unified",
    "ensure_coverage_with_auto_fetch",
    "ensure_coverage_parallel",
    "find_earliest_available_date",
    "get_prices_resolved",
    "list_symbols",
    "LIST_SYMBOLS_SQL",
    "with_symbol_lock",
    "fetch_prices_df",
    "_symbol_has_any_prices",
]
