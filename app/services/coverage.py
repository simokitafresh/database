"""Coverage service for symbol data coverage information with performance optimization."""

import time
from typing import Optional, Dict, Any, List
from datetime import date, datetime
import math

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.schemas.coverage import CoverageItemOut, CoverageListOut, PaginationMeta, QueryMeta
from app.services.query_optimizer import (
    get_optimized_coverage_query, 
    analyze_query_performance,
    create_query_performance_log
)


async def get_coverage_stats(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    q: Optional[str] = None,
    sort_by: str = "symbol",
    order: str = "asc",
    has_data: Optional[bool] = None,
    start_after: Optional[date] = None,
    end_before: Optional[date] = None,
    updated_after: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Get symbol coverage statistics with filtering, sorting, and pagination.
    
    Args:
        session: Database session
        page: Page number (1-based)
        page_size: Number of items per page
        q: Search query for symbol/name
        sort_by: Field to sort by
        order: Sort order ('asc' or 'desc')
        has_data: Filter by data availability
        start_after: Filter by data start date
        end_before: Filter by data end date
        updated_after: Filter by last updated timestamp
        
    Returns:
        Dictionary containing items, pagination, and metadata
    """
    start_time = time.time()
    
    # Use optimized query with performance enhancements
    base_query = get_optimized_coverage_query(use_materialized_view=False)
    
    count_query = """
    SELECT COUNT(*) as total 
    FROM symbols s
    LEFT JOIN (
        SELECT DISTINCT symbol FROM prices
        WHERE date >= CURRENT_DATE - INTERVAL '5 years'
    ) p_exists ON s.symbol = p_exists.symbol
    WHERE 1=1
    """
    
    conditions = []
    params = {}
    
    # Apply filters
    if q:
        conditions.append("(symbol ILIKE :q OR name ILIKE :q)")
        params["q"] = f"%{q}%"
    
    if has_data is not None:
        if has_data:
            conditions.append("data_start IS NOT NULL")
        else:
            conditions.append("data_start IS NULL")
    
    if start_after:
        conditions.append("data_start >= :start_after")
        params["start_after"] = start_after
    
    if end_before:
        conditions.append("data_end <= :end_before")
        params["end_before"] = end_before
    
    if updated_after:
        conditions.append("last_updated >= :updated_after")
        params["updated_after"] = updated_after
    
    # Add conditions to queries
    if conditions:
        condition_str = " AND " + " AND ".join(conditions)
        base_query += condition_str
        count_query += condition_str
    
    # Get total count
    count_result = await session.execute(text(count_query), params)
    total_items = count_result.scalar() or 0
    total_pages = math.ceil(total_items / page_size) if total_items > 0 else 1
    
    # Apply sorting
    valid_sort_fields = [
        "symbol", "name", "exchange", "currency", "is_active",
        "data_start", "data_end", "data_days", "row_count", "last_updated"
    ]
    
    if sort_by not in valid_sort_fields:
        sort_by = "symbol"
    
    order_clause = f"ORDER BY {sort_by} {'DESC' if order.lower() == 'desc' else 'ASC'}, symbol ASC"
    base_query += f" {order_clause}"
    
    # Apply pagination
    offset = (page - 1) * page_size
    base_query += f" LIMIT :limit OFFSET :offset"
    params["limit"] = page_size
    params["offset"] = offset
    
    # Execute main query
    result = await session.execute(text(base_query), params)
    rows = result.fetchall()
    
    # Convert to response objects
    items = []
    for row in rows:
        items.append(CoverageItemOut(
            symbol=row.symbol,
            name=row.name,
            exchange=row.exchange,
            currency=row.currency,
            is_active=row.is_active,
            data_start=row.data_start,
            data_end=row.data_end,
            data_days=row.data_days or 0,
            row_count=row.row_count or 0,
            last_updated=row.last_updated,
            has_gaps=row.has_gaps or False
        ))
    
    # Calculate query time
    query_time_ms = int((time.time() - start_time) * 1000)
    
    # Log performance for optimization analysis
    await create_query_performance_log(
        session=session,
        query_name="get_coverage_stats",
        execution_time_ms=query_time_ms,
        row_count=len(items),
        params={
            'page': page,
            'page_size': page_size,
            'q': q,
            'has_data': has_data,
            'sort_by': sort_by,
            'order': order
        }
    )
    
    return {
        "items": items,
        "pagination": PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages
        ),
        "meta": QueryMeta(
            query_time_ms=query_time_ms,
            cached=False,
            cache_updated_at=None
        )
    }


async def export_coverage_csv(
    session: AsyncSession,
    q: Optional[str] = None,
    sort_by: str = "symbol",
    order: str = "asc",
    has_data: Optional[bool] = None,
    start_after: Optional[date] = None,
    end_before: Optional[date] = None,
    updated_after: Optional[datetime] = None,
    max_rows: int = 10000
) -> str:
    """
    Export coverage data as CSV string.
    
    Args:
        session: Database session
        (same filter parameters as get_coverage_stats)
        max_rows: Maximum number of rows to export
        
    Returns:
        CSV string
    """
    import csv
    import io
    
    # Get data without pagination
    data = await get_coverage_stats(
        session=session,
        page=1,
        page_size=max_rows,
        q=q,
        sort_by=sort_by,
        order=order,
        has_data=has_data,
        start_after=start_after,
        end_before=end_before,
        updated_after=updated_after
    )
    
    # Generate CSV
    output = io.StringIO()
    fieldnames = [
        'symbol', 'name', 'exchange', 'currency', 'is_active',
        'data_start', 'data_end', 'data_days', 'row_count', 
        'last_updated', 'has_gaps'
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for item in data["items"]:
        row_data = {
            'symbol': item.symbol,
            'name': item.name or '',
            'exchange': item.exchange or '',
            'currency': item.currency or '',
            'is_active': item.is_active if item.is_active is not None else '',
            'data_start': item.data_start.isoformat() if item.data_start else '',
            'data_end': item.data_end.isoformat() if item.data_end else '',
            'data_days': item.data_days,
            'row_count': item.row_count,
            'last_updated': item.last_updated.isoformat() if item.last_updated else '',
            'has_gaps': item.has_gaps
        }
        writer.writerow(row_data)
    
    return output.getvalue()


async def refresh_coverage_cache(session: AsyncSession) -> Dict[str, Any]:
    """
    Refresh coverage cache (placeholder for future materialized view refresh).
    
    Args:
        session: Database session
        
    Returns:
        Refresh status information
    """
    # For now, just return status since we're using a regular view
    # In the future, this would refresh materialized views
    
    start_time = time.time()
    
    # Test query to ensure view is accessible
    test_result = await session.execute(text("SELECT COUNT(*) FROM v_symbol_coverage"))
    total_symbols = test_result.scalar()
    
    refresh_time_ms = int((time.time() - start_time) * 1000)
    
    return {
        "status": "completed",
        "total_symbols": total_symbols,
        "refresh_time_ms": refresh_time_ms,
        "refreshed_at": datetime.utcnow()
    }
