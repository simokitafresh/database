"""Background worker for processing fetch jobs."""

import asyncio
import logging
from datetime import date, datetime
from typing import Any, Dict, List

from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from decimal import Decimal

from app.core.config import settings
from app.db.engine import create_engine_and_sessionmaker
from app.schemas.fetch_jobs import FetchJobProgress, FetchJobResult
from app.schemas.events import CorporateEventCreate, EventTypeEnum
from app.services.fetch_jobs import (
    save_job_results,
    update_job_progress,
    update_job_status,
)
from app.services.fetcher import fetch_prices_and_events
from app.services.upsert import upsert_prices, df_to_rows
from app.services.event_service import record_event

logger = logging.getLogger(__name__)


async def process_fetch_job(
    job_id: str,
    symbols: List[str],
    date_from: date,
    date_to: date,
    interval: str = "1d",
    force: bool = False,
    max_concurrency: int = 1,  # Reduced to 1 for Supabase NullPool compatibility
) -> None:
    """
    Process a fetch job by downloading data for all symbols.

    Args:
        job_id: Job ID to process
        symbols: List of symbols to fetch
        date_from: Start date
        date_to: End date
        interval: Data interval
        force: Whether to force refresh existing data
        max_concurrency: Maximum concurrent fetches
    """
    logger.info(f"Starting job {job_id} with {len(symbols)} symbols")

    # 独立したセッションファクトリを作成
    _, SessionLocal = create_engine_and_sessionmaker(
        database_url=settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=settings.DB_POOL_PRE_PING,
        pool_recycle=settings.DB_POOL_RECYCLE,
        echo=settings.DB_ECHO,
    )

    async with SessionLocal() as session:
        try:
            # Mark job as processing
            await update_job_status(session, job_id, "processing", started_at=datetime.utcnow())

            # Initialize progress
            progress = FetchJobProgress(
                total_symbols=len(symbols),
                completed_symbols=0,
                current_symbol=None,
                total_rows=0,
                fetched_rows=0,
                percent=0.0,
            )
            await update_job_progress(session, job_id, progress)

            # Process symbols with concurrency control
            semaphore = asyncio.Semaphore(max_concurrency)
            # Lock for synchronizing session access (specifically for progress updates)
            session_lock = asyncio.Lock()
            results = []

            async def fetch_single_symbol(symbol: str) -> FetchJobResult:
                async with semaphore:
                    try:
                        # Update current symbol in progress
                        async with session_lock:
                            progress.current_symbol = symbol
                            await update_job_progress(session, job_id, progress)

                        # Fetch data for the symbol
                        result = await fetch_symbol_data(
                            symbol=symbol,
                            date_from=date_from,
                            date_to=date_to,
                            interval=interval,
                            force=force,
                        )

                        # Update progress
                        async with session_lock:
                            progress.completed_symbols += 1
                            progress.fetched_rows += result.rows_fetched
                            progress.percent = (
                                progress.completed_symbols / progress.total_symbols
                            ) * 100.0
                            progress.current_symbol = None

                            await update_job_progress(session, job_id, progress)

                        logger.info(f"Completed {symbol}: {result.rows_fetched} rows")
                        return result

                    except Exception as e:
                        logger.error(f"Failed to fetch {symbol}: {e}")
                        
                        async with session_lock:
                            progress.completed_symbols += 1
                            progress.percent = (
                                progress.completed_symbols / progress.total_symbols
                            ) * 100.0
                            progress.current_symbol = None

                            await update_job_progress(session, job_id, progress)

                        return FetchJobResult(
                            symbol=symbol, status="failed", rows_fetched=0, error=str(e)
                        )

            # Execute all fetches concurrently
            tasks = [fetch_single_symbol(symbol) for symbol in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and count successes/failures
            processed_results = []
            success_count = 0
            error_count = 0

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Task failed for {symbols[i]}: {result}")
                    processed_results.append(
                        FetchJobResult(
                            symbol=symbols[i], status="failed", rows_fetched=0, error=str(result)
                        )
                    )
                    error_count += 1
                else:
                    processed_results.append(result)
                    if result.status == "success":
                        success_count += 1
                    else:
                        error_count += 1

            # Save results
            await save_job_results(session, job_id, processed_results)

            # Mark job as completed
            final_status = "completed" if error_count == 0 else "completed_errors"
            await update_job_status(session, job_id, final_status, completed_at=datetime.utcnow())

            logger.info(f"Job {job_id} completed: {success_count} success, {error_count} errors")

        except Exception as e:
            logger.error(f"Job {job_id} failed with exception: {e}")

            # Mark job as failed
            await update_job_status(session, job_id, "failed", completed_at=datetime.utcnow())

            # Save error information
            error_results = [
                FetchJobResult(
                    symbol=symbol, status="failed", rows_fetched=0, error=f"Job failed: {str(e)}"
                )
                for symbol in symbols
            ]
            await save_job_results(session, job_id, error_results)


async def fetch_symbol_data(
    symbol: str, date_from: date, date_to: date, interval: str = "1d", force: bool = False
) -> FetchJobResult:
    """
    Fetch data for a single symbol using yfinance.

    Args:
        symbol: Symbol to fetch
        date_from: Start date
        date_to: End date
        interval: Data interval
        force: Whether to force refresh existing data

    Returns:
        FetchJobResult with fetch status and row count
    """
    try:
        # Fetch data using the robust fetcher service
        logger.info(f"Downloading {symbol} from {date_from} to {date_to}")
        
        # Run synchronous fetch in thread pool to avoid blocking event loop
        df, events = await run_in_threadpool(
            fetch_prices_and_events,
            symbol=symbol,
            start=date_from,
            end=date_to,
            settings=settings
        )

        if df is None or df.empty:
            logger.warning(f"No data returned for {symbol}")
            # Even if no price data, we might have events? 
            # Usually yfinance returns empty df if no data, but events might be separate.
            # But fetch_prices_and_events implementation returns empty df and empty events if fetch fails.
            if not events:
                return FetchJobResult(
                    symbol=symbol,
                    status="no_data",
                    rows_fetched=0,
                    error="No data available for the specified date range",
                )

        # Record events if any
        if events:
            # Create a separate session for events to ensure they are committed
            # regardless of price upsert success/failure, or to keep transactions separate.
            _, SessionLocalEvents = create_engine_and_sessionmaker(
                database_url=settings.DATABASE_URL,
                pool_size=1,
                max_overflow=0,
                pool_pre_ping=settings.DB_POOL_PRE_PING,
                pool_recycle=settings.DB_POOL_RECYCLE,
                echo=False,
            )
            
            async with SessionLocalEvents() as event_session:
                try:
                    event_count = 0
                    for event_dict in events:
                        # Map string type to Enum
                        event_type_str = event_dict.get("type")
                        if event_type_str == "stock_split":
                            event_type = EventTypeEnum.STOCK_SPLIT
                        elif event_type_str == "reverse_split":
                            event_type = EventTypeEnum.REVERSE_SPLIT
                        elif event_type_str == "dividend":
                            event_type = EventTypeEnum.DIVIDEND
                        elif event_type_str == "special_dividend":
                            event_type = EventTypeEnum.SPECIAL_DIVIDEND
                        else:
                            event_type = EventTypeEnum.UNKNOWN

                        event_data = CorporateEventCreate(
                            symbol=event_dict["symbol"],
                            event_date=event_dict["date"],
                            event_type=event_type,
                            ratio=Decimal(str(event_dict["ratio"])) if "ratio" in event_dict else None,
                            amount=Decimal(str(event_dict["amount"])) if "amount" in event_dict else None,
                            detection_method="daily_fetch",
                            source_data={"source": "yfinance", "job_type": "daily_fetch"}
                        )
                        await record_event(event_session, event_data)
                        event_count += 1
                    
                    logger.info(f"Recorded {event_count} events for {symbol}")
                    
                    # Auto-fix for splits if enabled
                    if settings.ADJUSTMENT_AUTO_FIX and events:
                        from app.services.adjustment_fixer import AdjustmentFixer
                        from app.db.models import CorporateEvent
                        from sqlalchemy import select
                        
                        split_events = [e for e in events if e.get("type") in ("stock_split", "reverse_split")]
                        
                        if split_events:
                            logger.info(f"Found {len(split_events)} split event(s) for {symbol}, triggering auto-fix")
                            
                            # Create separate session for fix to avoid transaction conflicts
                            _, SessionLocalFix = create_engine_and_sessionmaker(
                                database_url=settings.DATABASE_URL,
                                pool_size=1,
                                max_overflow=0,
                                pool_pre_ping=settings.DB_POOL_PRE_PING,
                                pool_recycle=settings.DB_POOL_RECYCLE,
                                echo=False,
                            )
                            
                            async with SessionLocalFix() as fix_session:
                                try:
                                    fixer = AdjustmentFixer(fix_session)
                                    
                                    # Find the most recent split event we just created
                                    for split_event in split_events:
                                        stmt = select(CorporateEvent).where(
                                            CorporateEvent.symbol == symbol,
                                            CorporateEvent.event_date == split_event["date"],
                                            CorporateEvent.event_type.in_(["stock_split", "reverse_split"])
                                        ).order_by(CorporateEvent.id.desc()).limit(1)
                                        
                                        result = await fix_session.execute(stmt)
                                        event_obj = result.scalar_one_or_none()
                                        
                                        if event_obj:
                                            fix_result = await fixer.auto_fix_symbol(symbol, event_obj.id)
                                            logger.info(
                                                f"Auto-fix for {symbol}: job_id={fix_result.get('job_id')}, "
                                                f"deleted_rows={fix_result.get('deleted_rows')}"
                                            )
                                        else:
                                            logger.warning(f"Could not find event object for {symbol} split on {split_event['date']}")
                                    
                                except Exception as fix_error:
                                    logger.error(f"Auto-fix failed for {symbol}: {fix_error}", exc_info=True)
                                    # Don't fail the entire job if auto-fix fails
                
                except Exception as e:
                    logger.error(f"Failed to record events for {symbol}: {e}")
                    # Continue to upsert prices even if event recording fails

        if df is None or df.empty:
             return FetchJobResult(
                symbol=symbol,
                status="no_data",
                rows_fetched=0,
                error="No data available (events recorded: {len(events)})" if events else "No data available",
            )

        # Prepare data for upsert using the helper
        rows_to_upsert = df_to_rows(df, symbol=symbol, source="yfinance")

        # 独立したセッションを作成（単一タスク用）
        _, SessionLocal = create_engine_and_sessionmaker(
            database_url=settings.DATABASE_URL,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=settings.DB_POOL_PRE_PING,
            pool_recycle=settings.DB_POOL_RECYCLE,
            echo=False,
        )

        async with SessionLocal() as session:
            try:
                inserted_count, updated_count = await upsert_prices(
                    session, rows_to_upsert, force_update=force
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

            total_rows = inserted_count + updated_count
            logger.info(
                f"Upserted {total_rows} rows for {symbol} ({inserted_count} new, {updated_count} updated)"
            )

            return FetchJobResult(
                symbol=symbol,
                status="success",
                rows_fetched=total_rows,
                error=None,
            )

    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
        return FetchJobResult(
            symbol=symbol,
            status="failed",
            rows_fetched=0,
            error=str(e),
        )


async def get_job_queue_status() -> Dict[str, Any]:
    """
    Get current job queue status.

    Returns:
        Dictionary with queue statistics
    """
    _, SessionLocal = create_engine_and_sessionmaker(
        database_url=settings.DATABASE_URL, pool_size=1, max_overflow=0
    )

    async with SessionLocal() as session:
        # Count jobs by status
        status_query = """
        SELECT status, COUNT(*) as count
        FROM fetch_jobs
        GROUP BY status
        """

        result = await session.execute(text(status_query))
        status_counts = {row.status: row.count for row in result.fetchall()}

        # Get recent job statistics
        recent_query = """
        SELECT
            COUNT(*) as total_recent,
            COUNT(*) FILTER (WHERE status = 'completed') as completed_recent,
            COUNT(*) FILTER (WHERE status = 'failed') as failed_recent,
            AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration
        FROM fetch_jobs
        WHERE created_at >= NOW() - INTERVAL '24 hours'
        """

        result = await session.execute(text(recent_query))
        recent_stats = result.first()

        return {
            "status_counts": status_counts,
            "recent_24h": {
                "total": recent_stats.total_recent or 0,
                "completed": recent_stats.completed_recent or 0,
                "failed": recent_stats.failed_recent or 0,
                "avg_duration_seconds": int(recent_stats.avg_duration or 0),
            },
            "timestamp": datetime.utcnow(),
        }


# Background job processor function
async def start_job_processor():
    """
    Start background job processor (for future use with task queue).
    This would integrate with Celery or similar in production.
    """
    logger.info("Job processor started (placeholder)")
    # In production, this would:
    # 1. Connect to a task queue (Redis/RabbitMQ)
    # 2. Listen for new jobs
    # 3. Process jobs as they arrive
    # 4. Handle job retries and failures
    pass
