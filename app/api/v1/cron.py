"""Cron job endpoints for scheduled data updates."""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.api.deps import get_session
from app.core.config import settings
from app.db.queries import list_symbols, ensure_coverage
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
            detail={"error": {"code": "MISSING_AUTH", "message": "Missing X-Cron-Secret header"}},
        )

    if x_cron_secret != settings.CRON_SECRET_TOKEN:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid cron token"}},
        )

    return True


@router.post("/daily-update", response_model=CronDailyUpdateResponse)
async def daily_update(
    request: CronDailyUpdateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    authenticated: bool = Depends(verify_cron_token),
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
        if not hasattr(settings, "CRON_BATCH_SIZE"):
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
                detail={
                    "error": {
                        "code": "DATABASE_ERROR",
                        "message": f"Database connection failed: {str(db_error)}",
                    }
                },
            )

        # Get active symbols
        try:
            all_symbols_data = await list_symbols(session, active=True)
            all_symbols = [row["symbol"] for row in all_symbols_data]  # 辞書からsymbolを抽出

            if not all_symbols:
                logger.warning("No active symbols found in database")
                return CronDailyUpdateResponse(
                    status="success",
                    message="No active symbols found to update",
                    total_symbols=0,
                    batch_count=0,
                    date_range={"from": "N/A", "to": "N/A"},
                    timestamp=start_time.isoformat(),
                    job_ids=None,
                    estimated_completion_minutes=None,
                    batch_size=None,
                    failed_symbols=None,
                    success_count=None
                )

            logger.info(f"Found {len(all_symbols)} active symbols")

        except Exception as symbols_error:
            logger.error(f"Failed to fetch symbols: {symbols_error}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": "SYMBOLS_ERROR",
                        "message": f"Failed to fetch symbols: {str(symbols_error)}",
                    }
                },
            )

        # Calculate date range for updates
        if request.date_from:
            try:
                date_from = datetime.strptime(request.date_from, "%Y-%m-%d").date()
            except ValueError:
                date_from = date.today() - timedelta(days=settings.CRON_UPDATE_DAYS)
        else:
            date_from = date.today() - timedelta(days=settings.CRON_UPDATE_DAYS)

        if request.date_to:
            try:
                date_to = datetime.strptime(request.date_to, "%Y-%m-%d").date()
            except ValueError:
                date_to = date.today() - timedelta(days=1)
        else:
            date_to = date.today() - timedelta(days=1)  # Yesterday

        logger.info(f"Date range for update: {date_from} to {date_to}")

        if request.dry_run:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return CronDailyUpdateResponse(
                status="success",
                message=(
                    f"Dry run completed. Would process {len(all_symbols)} symbols "
                    f"in batches of {batch_size}"
                ),
                total_symbols=len(all_symbols),
                batch_count=(len(all_symbols) + batch_size - 1) // batch_size,
                date_range={"from": str(date_from), "to": str(date_to)},  # 実際の日付を使用
                timestamp=start_time.isoformat(),
                batch_size=batch_size,
                job_ids=None,
                estimated_completion_minutes=None,
                failed_symbols=None,
                success_count=None
            )

        # Actual data update processing
        logger.info(f"Starting actual data update for {len(all_symbols)} symbols")

        # Initialize counters and tracking
        success_count = 0
        failed_symbols = []
        processed_count = 0
        batch_number = 0

        # Process symbols in batches for better resource management
        for batch_start in range(0, len(all_symbols), batch_size):
            batch_end = min(batch_start + batch_size, len(all_symbols))
            batch_symbols = all_symbols[batch_start:batch_end]
            batch_number += 1

            logger.info(f"Processing batch {batch_number}: symbols {batch_start+1} to {batch_end}")

            # Process each symbol in the batch
            for symbol in batch_symbols:
                processed_count += 1
                logger.debug(f"Processing symbol {processed_count}/{len(all_symbols)}: {symbol}")

                try:
                    # Use ensure_coverage to fetch and update data with timeout
                    import asyncio

                    await asyncio.wait_for(
                        ensure_coverage(
                            session=session,
                            symbols=[symbol],
                            date_from=date_from,
                            date_to=date_to,
                            refetch_days=settings.YF_REFETCH_DAYS,
                        ),
                        timeout=30.0,  # 30 seconds timeout per symbol
                    )

                    # Commit after each successful symbol
                    await session.commit()
                    success_count += 1
                    logger.info(
                        f"Successfully updated {symbol} ({success_count}/{processed_count})"
                    )

                except asyncio.TimeoutError:
                    logger.error(f"Timeout updating {symbol} (exceeded 30 seconds)")
                    failed_symbols.append(symbol)
                    await session.rollback()
                except Exception as symbol_error:
                    # Log the error but continue with next symbol
                    logger.error(f"Failed to update {symbol}: {str(symbol_error)}", exc_info=True)
                    failed_symbols.append(symbol)

                    # Rollback the failed transaction
                    await session.rollback()

                # Add small delay to avoid overwhelming Yahoo Finance API
                if processed_count % 10 == 0:
                    import asyncio

                    await asyncio.sleep(1)  # 1 second delay every 10 symbols

        # Determine final status based on results
        if failed_symbols:
            if success_count == 0:
                final_status = "failed"
                final_message = f"All {len(all_symbols)} symbols failed to update"
            else:
                final_status = "completed_with_errors"
                final_message = f"Updated {success_count}/{len(all_symbols)} symbols successfully"
        else:
            final_status = "success"
            final_message = f"Successfully updated all {success_count} symbols"

        logger.info(f"Data update completed: {final_message}")
        if failed_symbols:
            logger.warning(
                f"Failed symbols: {', '.join(failed_symbols[:10])}"
                + (f" and {len(failed_symbols)-10} more" if len(failed_symbols) > 10 else "")
            )

        execution_time = (datetime.utcnow() - start_time).total_seconds()
        return CronDailyUpdateResponse(
            status=final_status,
            message=final_message,
            total_symbols=len(all_symbols),
            batch_count=batch_number,
            date_range={"from": str(date_from), "to": str(date_to)},
            timestamp=start_time.isoformat(),
            batch_size=batch_size,
            success_count=success_count,
            failed_symbols=failed_symbols if failed_symbols else None,
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
                    "execution_time_seconds": execution_time,
                }
            },
        )


@router.get("/status", response_model=CronStatusResponse, summary="Get cron job status")
async def get_cron_status(
    cron_token: str = Header(None, alias="X-Cron-Secret"),
    session: AsyncSession = Depends(get_session),
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
                "yf_concurrency": getattr(settings, "YF_REQ_CONCURRENCY", 5),
                "active_symbols": active_symbols,
            },
        )

    except Exception as e:
        logger.error(f"Failed to get cron status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cron status: {str(e)}")
