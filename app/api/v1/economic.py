"""Economic indicators API endpoints for DTB3 and other FRED data."""

import logging
from datetime import date, datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.deps import get_session
from app.db.models import EconomicIndicator
from app.schemas.economic import EconomicDataOut, EconomicDataListOut, EconomicSeriesInfoOut

router = APIRouter()
logger = logging.getLogger(__name__)

# Supported economic series with metadata
SUPPORTED_SERIES = {
    "DTB3": {
        "name": "3-Month Treasury Bill Secondary Market Rate",
        "description": "The 3-Month Treasury Bill rate is the yield received for investing in a US government issued treasury bill with a 3-month maturity.",
        "frequency": "Daily",
        "units": "Percent",
        "source": "FRED (Federal Reserve Economic Data)"
    }
}


@router.get("/economic", response_model=List[EconomicSeriesInfoOut])
async def list_economic_series(
    session: AsyncSession = Depends(get_session)
) -> List[EconomicSeriesInfoOut]:
    """
    List all available economic data series.
    
    Returns metadata about each supported economic indicator series including:
    - Series identifier (symbol)
    - Name and description
    - Data frequency and units
    - Available date range
    - Number of data points
    
    **Examples:**
    ```
    GET /v1/economic
    ```
    """
    results = []
    
    for symbol, info in SUPPORTED_SERIES.items():
        # Get stats from database
        stmt = select(
            func.min(EconomicIndicator.date).label("data_start"),
            func.max(EconomicIndicator.date).label("data_end"),
            func.count(EconomicIndicator.date).label("row_count"),
            func.max(EconomicIndicator.last_updated).label("last_updated")
        ).where(EconomicIndicator.symbol == symbol)
        
        result = await session.execute(stmt)
        row = result.one()
        
        results.append(EconomicSeriesInfoOut(
            symbol=symbol,
            name=info["name"],
            description=info["description"],
            frequency=info["frequency"],
            units=info["units"],
            source=info["source"],
            data_start=row.data_start,
            data_end=row.data_end,
            row_count=row.row_count or 0,
            last_updated=row.last_updated
        ))
    
    return results


@router.get("/economic/{symbol}", response_model=EconomicDataListOut)
async def get_economic_data(
    symbol: str,
    date_from: Optional[date] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, alias="to", description="End date (YYYY-MM-DD)"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of records to return"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="Sort order by date"),
    session: AsyncSession = Depends(get_session)
) -> EconomicDataListOut:
    """
    Get economic indicator data for a specific series.
    
    Retrieves historical data for economic indicators like DTB3 (3-Month Treasury Bill Rate).
    
    **Path Parameters:**
    - **symbol**: The series identifier (e.g., 'DTB3')
    
    **Query Parameters:**
    - **from**: Start date for data range (optional)
    - **to**: End date for data range (optional)
    - **limit**: Maximum records to return (1-10000, default: 1000)
    - **order**: Sort order - 'asc' for oldest first, 'desc' for newest first
    
    **Examples:**
    ```
    GET /v1/economic/DTB3
    GET /v1/economic/DTB3?from=2024-01-01&to=2024-12-31
    GET /v1/economic/DTB3?limit=30&order=desc
    ```
    
    **Response:**
    Returns the requested data points with:
    - Symbol identifier
    - Array of data points (date, value, last_updated)
    - Total count and date range
    """
    # Normalize symbol
    symbol_upper = symbol.upper()
    
    # Validate symbol
    if symbol_upper not in SUPPORTED_SERIES:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SERIES_NOT_FOUND",
                    "message": f"Economic series '{symbol}' not found",
                    "details": {
                        "symbol": symbol,
                        "supported_series": list(SUPPORTED_SERIES.keys())
                    }
                }
            }
        )
    
    # Validate date range
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_DATE_RANGE",
                    "message": "date_from must be before or equal to date_to",
                    "details": {
                        "date_from": date_from.isoformat(),
                        "date_to": date_to.isoformat()
                    }
                }
            }
        )
    
    # Build query
    stmt = select(EconomicIndicator).where(EconomicIndicator.symbol == symbol_upper)
    
    if date_from:
        stmt = stmt.where(EconomicIndicator.date >= date_from)
    
    if date_to:
        stmt = stmt.where(EconomicIndicator.date <= date_to)
    
    # Apply ordering
    if order == "desc":
        stmt = stmt.order_by(EconomicIndicator.date.desc())
    else:
        stmt = stmt.order_by(EconomicIndicator.date.asc())
    
    # Apply limit
    stmt = stmt.limit(limit)
    
    # Execute query
    result = await session.execute(stmt)
    rows = result.scalars().all()
    
    # Convert to response format
    data = [
        EconomicDataOut(
            symbol=row.symbol,
            date=row.date,
            value=row.value,
            last_updated=row.last_updated
        )
        for row in rows
    ]
    
    # Get actual date range from results
    date_range = {
        "from": data[0].date.isoformat() if data else None,
        "to": data[-1].date.isoformat() if data else None
    }
    
    # For desc order, swap the range
    if order == "desc" and data:
        date_range = {
            "from": data[-1].date.isoformat(),
            "to": data[0].date.isoformat()
        }
    
    return EconomicDataListOut(
        symbol=symbol_upper,
        data=data,
        count=len(data),
        date_range=date_range
    )


@router.get("/economic/{symbol}/latest", response_model=EconomicDataOut)
async def get_latest_economic_data(
    symbol: str,
    session: AsyncSession = Depends(get_session)
) -> EconomicDataOut:
    """
    Get the most recent data point for an economic series.
    
    **Path Parameters:**
    - **symbol**: The series identifier (e.g., 'DTB3')
    
    **Examples:**
    ```
    GET /v1/economic/DTB3/latest
    ```
    
    **Response:**
    Returns the most recent data point with date, value, and last_updated timestamp.
    """
    # Normalize symbol
    symbol_upper = symbol.upper()
    
    # Validate symbol
    if symbol_upper not in SUPPORTED_SERIES:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SERIES_NOT_FOUND",
                    "message": f"Economic series '{symbol}' not found",
                    "details": {
                        "symbol": symbol,
                        "supported_series": list(SUPPORTED_SERIES.keys())
                    }
                }
            }
        )
    
    # Get latest data point
    stmt = select(EconomicIndicator).where(
        EconomicIndicator.symbol == symbol_upper
    ).order_by(EconomicIndicator.date.desc()).limit(1)
    
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    
    if not row:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "NO_DATA",
                    "message": f"No data available for series '{symbol_upper}'",
                    "details": {
                        "symbol": symbol_upper,
                        "suggestion": "Run /v1/daily-economic-update to fetch data"
                    }
                }
            }
        )
    
    return EconomicDataOut(
        symbol=row.symbol,
        date=row.date,
        value=row.value,
        last_updated=row.last_updated
    )
