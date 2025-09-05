"""Coverage API endpoints for symbol data coverage information."""

import time
from typing import Optional
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import io

from app.api.deps import get_session
from app.schemas.coverage import CoverageListOut
from app.services.coverage import get_coverage_stats, export_coverage_csv


router = APIRouter()


@router.get("/coverage", response_model=CoverageListOut)
async def get_coverage(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page (max: 1000)"),
    q: Optional[str] = Query(None, description="Search query for symbol/name"),
    sort_by: str = Query("symbol", description="Field to sort by"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="Sort order"),
    has_data: Optional[bool] = Query(None, description="Filter by data availability"),
    start_after: Optional[date] = Query(None, description="Filter by data start date after"),
    end_before: Optional[date] = Query(None, description="Filter by data end date before"),
    updated_after: Optional[datetime] = Query(None, description="Filter by last updated timestamp"),
    session: AsyncSession = Depends(get_session)
) -> CoverageListOut:
    """
    Get symbol data coverage information with filtering, sorting, and pagination.
    
    Returns a paginated list of symbols with their data coverage ranges including:
    - **Data start and end dates**: When price data begins and ends
    - **Number of data points**: Total price records available
    - **Trading days coverage**: Business days with data
    - **Last update timestamp**: When data was last refreshed
    - **Gap detection status**: Whether there are missing data periods
    
    **Parameters:**
    - **page**: Page number starting from 1
    - **page_size**: Number of items per page (1-1000)
    - **q**: Search term to filter symbols by name or code
    - **sort_by**: Field to sort results by (symbol, start_date, end_date, etc.)
    - **order**: Sort direction - 'asc' for ascending, 'desc' for descending
    - **has_data**: Filter to only symbols with data (true) or without data (false)
    - **start_after**: Show only symbols with data starting after this date
    - **end_before**: Show only symbols with data ending before this date
    - **updated_after**: Show only symbols updated after this timestamp
    
    **Examples:**
    - Get all symbols: `GET /v1/coverage`
    - Search for Apple: `GET /v1/coverage?q=AAPL`
    - Only symbols with data: `GET /v1/coverage?has_data=true`
    - Sorted by last update: `GET /v1/coverage?sort_by=last_updated&order=desc`
    """
    try:
        # Validate sort field
        valid_sort_fields = [
            "symbol", "name", "exchange", "currency", "is_active",
            "data_start", "data_end", "data_days", "row_count", "last_updated"
        ]
        
        if sort_by not in valid_sort_fields:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_SORT_FIELD",
                        "message": f"Invalid sort field '{sort_by}'",
                        "details": {
                            "field": "sort_by",
                            "value": sort_by,
                            "allowed_values": valid_sort_fields
                        }
                    }
                }
            )
        
        # Validate date range
        if start_after and end_before and start_after > end_before:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_DATE_RANGE",
                        "message": "start_after must be before end_before",
                        "details": {
                            "start_after": start_after.isoformat(),
                            "end_before": end_before.isoformat()
                        }
                    }
                }
            )
        
        # Get coverage data
        result = await get_coverage_stats(
            session=session,
            page=page,
            page_size=page_size,
            q=q,
            sort_by=sort_by,
            order=order,
            has_data=has_data,
            start_after=start_after,
            end_before=end_before,
            updated_after=updated_after
        )
        
        return CoverageListOut(**result)
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log error and return generic message
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_coverage: {e}", exc_info=True)
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An error occurred while retrieving coverage data",
                    "details": {
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
            }
        )


@router.get("/coverage/export")
async def export_coverage(
    q: Optional[str] = Query(None, description="Search query for symbol/name"),
    sort_by: str = Query("symbol", description="Field to sort by"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="Sort order"),
    has_data: Optional[bool] = Query(None, description="Filter by data availability"),
    start_after: Optional[date] = Query(None, description="Filter by data start date after"),
    end_before: Optional[date] = Query(None, description="Filter by data end date before"),
    updated_after: Optional[datetime] = Query(None, description="Filter by last updated timestamp"),
    max_rows: int = Query(10000, ge=1, le=50000, description="Maximum rows to export"),
    session: AsyncSession = Depends(get_session)
):
    """
    Export symbol coverage information as CSV file.
    
    Downloads coverage data in CSV format with the same filtering options as the main endpoint.
    The exported file includes all symbol metadata and coverage statistics.
    
    **Parameters:**
    Same filtering parameters as the main coverage endpoint, plus:
    - **max_rows**: Maximum number of rows to export (1-50,000)
    
    **CSV Format:**
    Returns a CSV file with columns:
    - `symbol`, `name`, `exchange`, `currency`, `is_active`
    - `data_start`, `data_end`, `data_days`, `row_count`, `last_updated`, `has_gaps`
    
    **Response:**
    - Content-Type: `text/csv; charset=utf-8`
    - Filename format: `coverage_YYYYMMDD_HHMMSS.csv`
    - Streaming response for efficient large dataset handling
    
    **Examples:**
    - Export all data: `GET /v1/coverage/export`
    - Export AAPL data: `GET /v1/coverage/export?q=AAPL`
    - Export only active symbols: `GET /v1/coverage/export?has_data=true`
    """
    try:
        # Validate parameters (same as main endpoint)
        valid_sort_fields = [
            "symbol", "name", "exchange", "currency", "is_active",
            "data_start", "data_end", "data_days", "row_count", "last_updated"
        ]
        
        if sort_by not in valid_sort_fields:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_SORT_FIELD",
                        "message": f"Invalid sort field '{sort_by}'",
                        "details": {
                            "field": "sort_by",
                            "value": sort_by,
                            "allowed_values": valid_sort_fields
                        }
                    }
                }
            )
        
        if start_after and end_before and start_after > end_before:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_DATE_RANGE",
                        "message": "start_after must be before end_before",
                        "details": {
                            "start_after": start_after.isoformat(),
                            "end_before": end_before.isoformat()
                        }
                    }
                }
            )
        
        # Generate CSV content
        csv_content = await export_coverage_csv(
            session=session,
            q=q,
            sort_by=sort_by,
            order=order,
            has_data=has_data,
            start_after=start_after,
            end_before=end_before,
            updated_after=updated_after,
            max_rows=max_rows
        )
        
        # Create filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"coverage_{timestamp}.csv"
        
        # Return streaming response
        return StreamingResponse(
            io.StringIO(csv_content),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log error and return generic message
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in export_coverage: {e}", exc_info=True)
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "EXPORT_ERROR",
                    "message": "An error occurred while exporting coverage data",
                    "details": {
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
            }
        )
