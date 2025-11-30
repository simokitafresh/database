"""Maintenance API endpoints for price adjustment detection and correction."""

from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.config import settings
from app.schemas.maintenance import (
    AdjustmentCheckRequest,
    AdjustmentCheckResponse,
    AdjustmentReportResponse,
    AdjustmentFixRequest,
    AdjustmentFixResponse,
    AdjustmentEventResponse,
    ScanResultResponse,
    FixResultItem,
)
from app.services.adjustment_detector import PrecisionAdjustmentDetector


router = APIRouter(prefix="/maintenance", tags=["maintenance"])


# In-memory cache for last scan results (for demo/single-instance use)
# In production, consider using Redis or DB storage
_last_scan_result: dict | None = None


@router.post("/check-adjustments", response_model=AdjustmentCheckResponse)
async def check_adjustments(
    request: AdjustmentCheckRequest,
    session: AsyncSession = Depends(get_session),
) -> AdjustmentCheckResponse:
    """
    Check symbols for potential price adjustments (splits, dividends, etc.).
    
    This endpoint scans the specified symbols (or all symbols if none specified)
    for inconsistencies between stored prices and current yfinance data that may
    indicate corporate actions like stock splits or dividend adjustments.
    
    **Parameters:**
    - **symbols**: Optional list of specific symbols to check. If not provided, 
      scans all active symbols.
    - **threshold_pct**: Minimum percentage difference to flag as adjustment 
      (default: 0.001%)
    - **auto_fix**: Whether to automatically fix detected issues (default: false)
    
    **Returns:**
    - Summary of scan results including detected adjustments
    - List of symbols requiring attention with event details
    - Scan metadata (duration, timestamp)
    
    **Example:**
    ```json
    POST /v1/maintenance/check-adjustments
    {
        "symbols": ["AAPL", "MSFT"],
        "threshold_pct": 1.0
    }
    ```
    """
    global _last_scan_result
    
    if not settings.ADJUSTMENT_CHECK_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "ADJUSTMENT_CHECK_DISABLED",
                    "message": "Adjustment checking is disabled",
                    "details": {"setting": "ADJUSTMENT_CHECK_ENABLED"}
                }
            }
        )
    
    try:
        detector = PrecisionAdjustmentDetector()
        
        # Perform scan
        scan_result = await detector.scan_all_symbols(
            session=session,
            symbols=request.symbols,
            auto_fix=request.auto_fix and settings.ADJUSTMENT_AUTO_FIX,
        )
        
        # Cache results for later retrieval
        _last_scan_result = scan_result
        
        # Convert service result to schema response
        needs_refresh = []
        for item in scan_result["needs_refresh"]:
            events = [
                AdjustmentEventResponse(
                    symbol=ev["symbol"],
                    event_type=ev["event_type"],
                    severity=ev["severity"],
                    pct_difference=ev["pct_difference"],
                    check_date=ev["check_date"],
                    db_price=ev["db_price"],
                    yf_adjusted_price=ev["yf_adjusted_price"],
                    details=ev.get("details", {}),
                    recommendation=ev.get("recommendation", ""),
                )
                for ev in item.get("events", [])
            ]
            needs_refresh.append(
                ScanResultResponse(
                    symbol=item["symbol"],
                    needs_refresh=item["needs_refresh"],
                    events=events,
                    max_pct_diff=item.get("max_pct_diff", 0.0),
                    error=item.get("error"),
                )
            )
        
        return AdjustmentCheckResponse(
            scan_timestamp=scan_result["scan_timestamp"],
            total_symbols=scan_result["total_symbols"],
            scanned=scan_result["scanned"],
            needs_refresh=needs_refresh,
            no_change=scan_result["no_change"],
            errors=scan_result["errors"],
            fixed=scan_result.get("fixed", []),
            summary=scan_result["summary"],
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "SCAN_FAILED",
                    "message": f"Adjustment scan failed: {str(e)}",
                    "details": {"symbols": request.symbols}
                }
            }
        )


@router.get("/adjustment-report", response_model=AdjustmentReportResponse)
async def get_adjustment_report(
    symbols: Optional[List[str]] = Query(None, description="Filter by specific symbols"),
    severity: Optional[str] = Query(
        None, 
        pattern="^(info|warning|critical|low|normal|high|unknown)$",
        description="Filter by severity level"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results to return"),
    session: AsyncSession = Depends(get_session),
) -> AdjustmentReportResponse:
    """
    Get the latest adjustment detection report.
    
    Returns cached results from the most recent adjustment scan. Use the
    `/check-adjustments` endpoint first to populate the report.
    
    **Parameters:**
    - **symbols**: Optional list of symbols to filter the report
    - **severity**: Filter by event severity (low, normal, high, critical)
    - **limit**: Maximum number of results to return (default: 100)
    
    **Returns:**
    - List of symbols with detected adjustments
    - Filtering metadata
    
    **Example:**
    ```
    GET /v1/maintenance/adjustment-report?severity=critical&limit=10
    ```
    """
    if not settings.ADJUSTMENT_CHECK_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "ADJUSTMENT_CHECK_DISABLED",
                    "message": "Adjustment checking is disabled",
                    "details": {"setting": "ADJUSTMENT_CHECK_ENABLED"}
                }
            }
        )
    
    if _last_scan_result is None:
        return AdjustmentReportResponse(
            last_scan_timestamp=None,
            total_symbols=0,
            needs_refresh_count=0,
            needs_refresh=[],
            summary={},
            available=False,
        )
    
    # Filter cached results
    results = _last_scan_result.get("needs_refresh", [])
    
    # Apply symbol filter
    if symbols:
        symbol_set = {s.upper() for s in symbols}
        results = [r for r in results if r["symbol"].upper() in symbol_set]
    
    # Apply severity filter
    if severity:
        filtered_results = []
        for result in results:
            filtered_events = [
                e for e in result.get("events", [])
                if e.get("severity") == severity
            ]
            if filtered_events:
                filtered_results.append({
                    **result,
                    "events": filtered_events,
                })
        results = filtered_results
    
    # Apply limit
    results = results[:limit]
    
    # Convert to response schema
    needs_refresh = []
    for item in results:
        events = [
            AdjustmentEventResponse(
                symbol=ev["symbol"],
                event_type=ev["event_type"],
                severity=ev["severity"],
                pct_difference=ev["pct_difference"],
                check_date=ev["check_date"],
                db_price=ev["db_price"],
                yf_adjusted_price=ev["yf_adjusted_price"],
                details=ev.get("details", {}),
                recommendation=ev.get("recommendation", ""),
            )
            for ev in item.get("events", [])
        ]
        needs_refresh.append(
            ScanResultResponse(
                symbol=item["symbol"],
                needs_refresh=item.get("needs_refresh", True),
                events=events,
                max_pct_diff=item.get("max_pct_diff", 0.0),
                error=item.get("error"),
            )
        )
    
    return AdjustmentReportResponse(
        last_scan_timestamp=_last_scan_result.get("scan_timestamp"),
        total_symbols=_last_scan_result.get("total_symbols", 0),
        needs_refresh_count=len(needs_refresh),
        needs_refresh=needs_refresh,
        summary=_last_scan_result.get("summary", {}),
        available=True,
    )


@router.post("/fix-adjustments", response_model=AdjustmentFixResponse)
async def fix_adjustments(
    request: AdjustmentFixRequest,
    session: AsyncSession = Depends(get_session),
) -> AdjustmentFixResponse:
    """
    Fix detected price adjustments by deleting affected data and scheduling re-fetch.
    
    This endpoint will:
    1. Delete all price data for the specified symbols
    2. Create fetch jobs to re-download fresh data from yfinance
    
    **Safety Features:**
    - Requires explicit `confirm=true` to execute
    - Auto-fix must be enabled via `ADJUSTMENT_AUTO_FIX` setting
    - Can specify subset of symbols from the last scan
    
    **Parameters:**
    - **symbols**: List of symbols to fix. If not provided, fixes all symbols 
      from the last scan.
    - **confirm**: Must be `true` to execute the fix (safety check)
    
    **Returns:**
    - List of fixed symbols with job IDs for tracking
    - Summary statistics
    
    **Example:**
    ```json
    POST /v1/maintenance/fix-adjustments
    {
        "symbols": ["AAPL"],
        "confirm": true
    }
    ```
    """
    from datetime import datetime
    
    if not settings.ADJUSTMENT_CHECK_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "ADJUSTMENT_CHECK_DISABLED",
                    "message": "Adjustment checking is disabled",
                    "details": {"setting": "ADJUSTMENT_CHECK_ENABLED"}
                }
            }
        )
    
    if not settings.ADJUSTMENT_AUTO_FIX:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "AUTO_FIX_DISABLED",
                    "message": "Automatic adjustment fixing is disabled",
                    "details": {"setting": "ADJUSTMENT_AUTO_FIX"}
                }
            }
        )
    
    if not request.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "CONFIRMATION_REQUIRED",
                    "message": "Fix operation requires explicit confirmation",
                    "details": {"hint": "Set 'confirm': true to proceed"}
                }
            }
        )
    
    # Determine symbols to fix
    symbols_to_fix = request.symbols
    if not symbols_to_fix:
        # Use all symbols from last scan that need refresh
        if _last_scan_result:
            symbols_to_fix = [
                item["symbol"] for item in _last_scan_result.get("needs_refresh", [])
            ]
    
    if not symbols_to_fix:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "NO_SYMBOLS_TO_FIX",
                    "message": "No symbols specified and no previous scan results available",
                    "details": {"hint": "Run /check-adjustments first or specify symbols"}
                }
            }
        )
    
    fixed: List[FixResultItem] = []
    errors: List[dict] = []
    
    try:
        detector = PrecisionAdjustmentDetector()
        
        for symbol in symbols_to_fix:
            try:
                result = await detector.auto_fix_symbol(session, symbol)
                fixed.append(
                    FixResultItem(
                        symbol=symbol,
                        deleted_rows=result.get("deleted_rows", 0),
                        job_created=result.get("job_created", False),
                        job_id=result.get("job_id"),
                        error=result.get("error"),
                        timestamp=result.get("timestamp", datetime.utcnow().isoformat()),
                    )
                )
            except Exception as e:
                errors.append({"symbol": symbol, "error": str(e)})
        
        success_count = sum(1 for f in fixed if f.job_created and not f.error)
        
        return AdjustmentFixResponse(
            total_requested=len(symbols_to_fix),
            fixed=fixed,
            errors=errors,
            summary={
                "requested": len(symbols_to_fix),
                "success": success_count,
                "failed": len(errors) + len([f for f in fixed if f.error]),
            },
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "FIX_FAILED",
                    "message": f"Adjustment fix operation failed: {str(e)}",
                    "details": {"symbols": symbols_to_fix}
                }
            }
        )
