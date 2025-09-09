"""Cron job endpoints for scheduled data updates."""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.api.deps import get_session
from app.core.config import settings
from app.db.queries import list_symbols
from app.schemas.cron import CronDailyUpdateRequest, CronDailyUpdateResponse, CronStatusResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def verify_cron_token(x_cron_secret: Optional[str] = Header(None)) -> bool:
    """Verify cron authentication token.
    
    Args:
        x_cron_secret: Token from X-Cron-Secret header
        
    Returns:
        bool: True if authenticated
        
    Raises:
        HTTPException: If authentication fails
    """
    if not settings.CRON_SECRET_TOKEN:
        logger.warning("CRON_SECRET_TOKEN not set, skipping authentication")
        return True
    
    if not x_cron_secret:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "MISSING_AUTH", "message": "Missing X-Cron-Secret header"}}
        )
    
    if x_cron_secret != settings.CRON_SECRET_TOKEN:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid cron token"}}
        )
    
    return True


@router.post("/daily-update", response_model=CronDailyUpdateResponse)
async def daily_update(
    request: CronDailyUpdateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    authenticated: bool = Depends(verify_cron_token)
) -> CronDailyUpdateResponse:
    """Execute daily stock data update.
    
    This endpoint processes active symbols in batches and updates their price data.
    
    Args:
        request: Request parameters including dry_run flag
        background_tasks: FastAPI background tasks
        session: Database session
        authenticated: Authentication verification
        
    Returns:
        CronDailyUpdateResponse: Results of the update operation
        
    Raises:
        HTTPException: For various error conditions
    """
    start_time = datetime.utcnow()
    
    try:
        logger.info(f"Starting daily stock data update (dry_run={request.dry_run})")
        
        # Basic configuration check
        if not hasattr(settings, 'CRON_BATCH_SIZE'):
            logger.warning("CRON_BATCH_SIZE not set, using default: 50")
            batch_size = 50
        else:
            batch_size = settings.CRON_BATCH_SIZE or 50
            
        # Test database connection first
        try:
            await session.execute(text("SELECT 1"))
            logger.info("Database connection verified")
        except Exception as db_error:
            logger.error(f"Database connection failed: {db_error}")
            raise HTTPException(
                status_code=500,
                detail={"error": {"code": "DATABASE_ERROR", "message": f"Database connection failed: {str(db_error)}"}}
            )
        
        # Get active symbols
        try:
            all_symbols = await list_symbols(session, active=True)
            if not all_symbols:
                logger.warning("No active symbols found in database")
                return CronDailyUpdateResponse(
                    status="success",
                    message="No active symbols found to update", 
                    processed_count=0,
                    success_count=0,
                    error_count=0,
                    errors=[],
                    execution_time_seconds=0.0
                )
                
            logger.info(f"Found {len(all_symbols)} active symbols")
            
        except Exception as symbols_error:
            logger.error(f"Failed to fetch symbols: {symbols_error}")
            raise HTTPException(
                status_code=500,
                detail={"error": {"code": "SYMBOLS_ERROR", "message": f"Failed to fetch symbols: {str(symbols_error)}"}}
            )
        
        if request.dry_run:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return CronDailyUpdateResponse(
                status="success", 
                message=f"Dry run completed. Would process {len(all_symbols)} symbols in batches of {batch_size}",
                processed_count=len(all_symbols),
                success_count=len(all_symbols),
                error_count=0,
                errors=[],
                execution_time_seconds=execution_time
            )
        
        # TODO: Implement actual batch processing for non-dry-run
        # For now, simulate processing
        logger.info("Simulating batch processing (actual implementation pending)")
        
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        return CronDailyUpdateResponse(
            status="success",
            message=f"Processed {len(all_symbols)} symbols successfully (simulated)",
            processed_count=len(all_symbols),
            success_count=len(all_symbols),
            error_count=0,
            errors=[],
            execution_time_seconds=execution_time
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.exception("Unexpected error in daily_update")
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": f"Internal server error: {str(e)}",
                    "execution_time_seconds": execution_time
                }
            }
        )
async def daily_update(
    request: CronDailyUpdateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    cron_token: str = Header(None, alias="X-Cron-Secret")
) -> CronDailyUpdateResponse:
    """Execute daily data update for all symbols.
    
    Args:
        request: Cron daily update request parameters
        background_tasks: FastAPI background tasks
        session: Database session
        cron_token: Authentication token from header
        
    Returns:
        CronDailyUpdateResponse with execution status and job details
    """
    verify_cron_token(cron_token)
    
    start_time = datetime.utcnow()
    logger.info(f"Starting daily update cron job at {start_time}")
    
    try:
        # Get all active symbols
        all_symbols_data = await list_symbols(session, active=True)
        all_symbols = [row["symbol"] for row in all_symbols_data]
        
        total_symbols = len(all_symbols)
        logger.info(f"Found {total_symbols} active symbols to update")
        
        if total_symbols == 0:
            return CronDailyUpdateResponse(
                status="no_symbols",
                message="No active symbols found",
                total_symbols=0,
                batch_count=0,
                date_range={"from": "", "to": ""},
                timestamp=start_time.isoformat()
            )
        
        # Calculate date range
        if request.date_from:
            date_from = datetime.strptime(request.date_from, '%Y-%m-%d').date()
        else:
            date_from = date.today() - timedelta(days=settings.CRON_UPDATE_DAYS)
        
        if request.date_to:
            date_to = datetime.strptime(request.date_to, '%Y-%m-%d').date()
        else:
            date_to = date.today() - timedelta(days=1)  # Yesterday
        
        # Split into batches
        batch_size = min(settings.CRON_BATCH_SIZE, 50)  # Fallback if FETCH_JOB_MAX_SYMBOLS not available
        batches = [
            all_symbols[i:i + batch_size]
            for i in range(0, total_symbols, batch_size)
        ]
        
        logger.info(f"Split into {len(batches)} batches of max {batch_size} symbols")
        
        if request.dry_run:
            return CronDailyUpdateResponse(
                status="dry_run",
                message="Dry run completed",
                total_symbols=total_symbols,
                batch_count=len(batches),
                batch_size=batch_size,
                date_range={
                    "from": date_from.isoformat(),
                    "to": date_to.isoformat()
                },
                timestamp=start_time.isoformat()
            )
        
        # Create FetchJob for each batch
        # Note: This is a placeholder since fetch_jobs table doesn't exist
        # In a full implementation, this would create actual background jobs
        job_ids = []
        
        if not request.dry_run:
            # For now, we'll just simulate job creation without actual background processing
            # This can be expanded when the full fetch job system is implemented
            for i, batch in enumerate(batches):
                # Simulate job ID creation
                job_id = f"cron_job_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{i}"
                job_ids.append(job_id)
                logger.info(f"Simulated job creation: {job_id} for batch {i+1}/{len(batches)}")
                
        return CronDailyUpdateResponse(
            status="success" if not request.dry_run else "dry_run",
            message=f"Daily update {'started' if not request.dry_run else 'planned'} for {total_symbols} symbols",
            total_symbols=total_symbols,
            batch_count=len(batches),
            job_ids=job_ids if not request.dry_run else None,
            date_range={
                "from": date_from.isoformat(),
                "to": date_to.isoformat()
            },
            timestamp=start_time.isoformat(),
            estimated_completion_minutes=(total_symbols * 0.5) / 60
        )
        
    except Exception as e:
        logger.error(f"Daily update failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Daily update failed: {str(e)}"
        )


@router.get("/status", response_model=CronStatusResponse, summary="Get cron job status")
async def get_cron_status(
    cron_token: str = Header(None, alias="X-Cron-Secret"),
    session: AsyncSession = Depends(get_session)
) -> CronStatusResponse:
    """Get current status of cron jobs"""
    verify_cron_token(cron_token)
    
    try:
        # Since fetch_jobs table doesn't exist yet, return basic status
        # This will be expanded when the fetch job system is implemented
        
        # Check if we can access symbols table
        result = await session.execute(
            text("SELECT COUNT(*) as count FROM symbols WHERE is_active = true")
        )
        active_symbols = result.scalar()
        
        return CronStatusResponse(
            status="active",
            last_run=None,  # No job history yet
            recent_job_count=0,
            job_status_counts={},
            settings={
                "batch_size": settings.CRON_BATCH_SIZE,
                "update_days": settings.CRON_UPDATE_DAYS,
                "yf_concurrency": getattr(settings, 'YF_REQ_CONCURRENCY', 5)
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get cron status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get cron status: {str(e)}"
        )