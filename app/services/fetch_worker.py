"""Background worker for processing fetch jobs."""

import asyncio
import logging
from datetime import date, datetime
from typing import Any, Dict, List

from sqlalchemy import text

from app.core.config import settings
from app.db.engine import create_engine_and_sessionmaker
from app.schemas.fetch_jobs import FetchJobProgress, FetchJobResult
from app.services.fetch_jobs import (
    save_job_results,
    update_job_progress,
    update_job_status,
)

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
            results = []

            async def fetch_single_symbol(symbol: str) -> FetchJobResult:
                async with semaphore:
                    try:
                        # Update current symbol in progress
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
        import pandas as pd
        import yfinance as yf

        from app.services.upsert import upsert_prices

        # Create ticker
        ticker = yf.Ticker(symbol)

        # Download data
        logger.info(f"Downloading {symbol} from {date_from} to {date_to}")
        df = ticker.history(
            start=date_from,
            end=date_to,
            interval=interval,
            auto_adjust=True,
            prepost=False,
        )

        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return FetchJobResult(
                symbol=symbol,
                status="no_data",
                rows_fetched=0,
                date_from=None,
                date_to=None,
                error="No data available for the specified date range",
            )

        # Reset index to get date as column
        df = df.reset_index()

        # Prepare data for upsert
        rows_to_upsert = []
        for _, row in df.iterrows():
            price_data = {
                "symbol": symbol,
                "date": row["Date"].date() if hasattr(row["Date"], "date") else row["Date"],
                "open": float(row["Open"]) if pd.notna(row["Open"]) else None,
                "high": float(row["High"]) if pd.notna(row["High"]) else None,
                "low": float(row["Low"]) if pd.notna(row["Low"]) else None,
                "close": float(row["Close"]) if pd.notna(row["Close"]) else None,
                "volume": int(row["Volume"]) if pd.notna(row["Volume"]) else None,
                "last_updated": datetime.utcnow(),
            }
            rows_to_upsert.append(price_data)

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
                date_from=None,  # Remove date fields to avoid JSON serialization issues
                date_to=None,
                error=None,
            )

    except ImportError:
        logger.error("yfinance not installed. Install with: pip install yfinance")
        return FetchJobResult(
            symbol=symbol,
            status="failed",
            rows_fetched=0,
            date_from=None,
            date_to=None,
            error="yfinance package not installed",
        )
    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
        return FetchJobResult(
            symbol=symbol,
            status="failed",
            rows_fetched=0,
            date_from=None,
            date_to=None,
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
