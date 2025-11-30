"""Service for handling daily data updates and maintenance tasks."""

import logging
import asyncio
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import HTTPException

from app.core.config import settings
from app.db.queries import list_symbols, ensure_coverage
from app.schemas.cron import CronDailyUpdateRequest, CronDailyUpdateResponse

logger = logging.getLogger(__name__)


class DailyUpdateService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute_daily_update(
        self,
        request: CronDailyUpdateRequest,
    ) -> CronDailyUpdateResponse:
        """Execute daily stock data update."""
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Starting daily stock data update (dry_run={request.dry_run})")
            
            # Basic configuration check
            batch_size = settings.CRON_BATCH_SIZE or 50
            
            # Test database connection
            try:
                await self.session.execute(text("SELECT 1"))
            except Exception as db_error:
                logger.error(f"Database connection failed: {db_error}")
                raise HTTPException(
                    status_code=500,
                    detail={"error": {"code": "DATABASE_ERROR", "message": f"Database connection failed: {str(db_error)}"}}
                )
            
            # Get active symbols
            try:
                all_symbols_data = await list_symbols(self.session, active=True)
                all_symbols = [row["symbol"] for row in all_symbols_data]
                
                if not all_symbols:
                    logger.warning("No active symbols found in database")
                    return CronDailyUpdateResponse(
                        status="success",
                        message="No active symbols found to update",
                        total_symbols=0,
                        batch_count=0,
                        date_range={"from": "N/A", "to": "N/A"},
                        timestamp=start_time.isoformat(),
                        success_count=None
                    )
                
                logger.info(f"Found {len(all_symbols)} active symbols")
            except Exception as symbols_error:
                logger.error(f"Failed to fetch symbols: {symbols_error}")
                raise HTTPException(
                    status_code=500,
                    detail={"error": {"code": "SYMBOLS_ERROR", "message": f"Failed to fetch symbols: {str(symbols_error)}"}}
                )
            
            # Calculate date range
            date_from = self._calculate_date_from(request.date_from)
            date_to = self._calculate_date_to(request.date_to)
            
            logger.info(f"Date range for update: {date_from} to {date_to}")
            
            if request.dry_run:
                return CronDailyUpdateResponse(
                    status="success",
                    message=f"Dry run completed. Would process {len(all_symbols)} symbols in batches of {batch_size}",
                    total_symbols=len(all_symbols),
                    batch_count=(len(all_symbols) + batch_size - 1) // batch_size,
                    date_range={"from": str(date_from), "to": str(date_to)},
                    timestamp=start_time.isoformat(),
                    batch_size=batch_size,
                    success_count=None
                )
            
            # Actual processing
            success_count, failed_symbols, batch_number = await self._process_batches(
                all_symbols, batch_size, date_from, date_to
            )
            
            # Determine status
            final_status, final_message = self._determine_status(
                len(all_symbols), success_count, failed_symbols
            )
            
            # Adjustment check
            adjustment_result = await self._run_adjustment_check(request)
            
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
                adjustment_check=adjustment_result,
            )
            
        except HTTPException:
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

    async def execute_economic_update(
        self,
        request: CronDailyUpdateRequest,
    ) -> CronDailyUpdateResponse:
        """Execute daily economic data update (FRED)."""
        start_time = datetime.utcnow()
        logger.info(f"Starting daily economic data update (dry_run={request.dry_run})")
        
        try:
            date_from, date_to = await self._determine_economic_date_range(request)
            
            if date_from > date_to:
                logger.info(f"Data is up to date. Skipping update.")
                return CronDailyUpdateResponse(
                    status="success",
                    message="Data is up to date",
                    total_symbols=1,
                    batch_count=0,
                    date_range={"from": str(date_from), "to": str(date_to)},
                    timestamp=start_time.isoformat(),
                    success_count=0
                )
            
            if request.dry_run:
                return CronDailyUpdateResponse(
                    status="success",
                    message="Dry run completed for economic update",
                    total_symbols=1,
                    batch_count=1,
                    date_range={"from": str(date_from), "to": str(date_to)},
                    timestamp=start_time.isoformat(),
                    success_count=None
                )
            
            from app.services.fred_service import get_fred_service
            fred_service = get_fred_service()
            data = fred_service.fetch_dtb3_data(start_date=date_from, end_date=date_to)
            
            if data:
                await fred_service.save_economic_data_async(self.session, data)
                success_count = len(data)
                message = f"Successfully updated {success_count} data points for DTB3"
            else:
                success_count = 0
                message = "No data found to update"
            
            return CronDailyUpdateResponse(
                status="success",
                message=message,
                total_symbols=1,
                batch_count=1,
                date_range={"from": str(date_from), "to": str(date_to)},
                timestamp=start_time.isoformat(),
                success_count=success_count
            )
            
        except Exception as e:
            logger.exception("Unexpected error in daily_economic_update")
            raise HTTPException(
                status_code=500,
                detail={"error": {"code": "INTERNAL_ERROR", "message": f"Internal server error: {str(e)}"}}
            )

    async def check_adjustments(
        self,
        symbols: Optional[List[str]] = None,
        auto_fix: bool = False,
    ) -> Dict[str, Any]:
        """Check for and optionally fix price adjustments."""
        start_time = datetime.utcnow()
        
        if not settings.ADJUSTMENT_CHECK_ENABLED:
            return {
                "status": "skipped",
                "message": "Adjustment checking is disabled",
                "timestamp": start_time.isoformat(),
            }
        
        try:
            from app.services.adjustment_detector import PrecisionAdjustmentDetector
            detector = PrecisionAdjustmentDetector()
            
            scan_result = await detector.scan_all_symbols(
                session=self.session,
                symbols=symbols,
                auto_fix=auto_fix and settings.ADJUSTMENT_AUTO_FIX,
            )
            
            end_time = datetime.utcnow()
            duration_seconds = (end_time - start_time).total_seconds()
            
            response = {
                "status": "success",
                "message": f"Scanned {scan_result['scanned']} symbols, {len(scan_result['needs_refresh'])} need refresh",
                "timestamp": start_time.isoformat(),
                "duration_seconds": round(duration_seconds, 2),
                "total_symbols": scan_result["total_symbols"],
                "scanned": scan_result["scanned"],
                "needs_refresh_count": len(scan_result["needs_refresh"]),
                "errors_count": len(scan_result["errors"]),
                "summary": scan_result["summary"],
            }
            
            if auto_fix and scan_result.get("fixed"):
                response["fixed_count"] = len(scan_result["fixed"])
                response["fixed_symbols"] = [f["symbol"] for f in scan_result["fixed"]]
            
            affected = [r["symbol"] for r in scan_result["needs_refresh"][:20]]
            if affected:
                response["affected_symbols"] = affected
                if len(scan_result["needs_refresh"]) > 20:
                    response["affected_symbols_truncated"] = True
            
            return response
            
        except Exception as e:
            logger.exception("Unexpected error in adjustment_check")
            raise HTTPException(
                status_code=500,
                detail={"error": {"code": "INTERNAL_ERROR", "message": f"Adjustment check failed: {str(e)}"}}
            )

    # Helper methods
    def _calculate_date_from(self, date_str: Optional[str]) -> date:
        if date_str:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        return date.today() - timedelta(days=settings.CRON_UPDATE_DAYS)

    def _calculate_date_to(self, date_str: Optional[str]) -> date:
        if date_str:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        return date.today() - timedelta(days=1)

    async def _process_batches(self, all_symbols, batch_size, date_from, date_to):
        success_count = 0
        failed_symbols = []
        processed_count = 0
        batch_number = 0
        
        for batch_start in range(0, len(all_symbols), batch_size):
            batch_end = min(batch_start + batch_size, len(all_symbols))
            batch_symbols = all_symbols[batch_start:batch_end]
            batch_number += 1
            
            logger.info(f"Processing batch {batch_number}: symbols {batch_start+1} to {batch_end}")
            
            for symbol in batch_symbols:
                processed_count += 1
                try:
                    await asyncio.wait_for(
                        ensure_coverage(
                            session=self.session,
                            symbols=[symbol],
                            date_from=date_from,
                            date_to=date_to,
                            refetch_days=settings.YF_REFETCH_DAYS,
                        ),
                        timeout=30.0,
                    )
                    await self.session.commit()
                    success_count += 1
                except asyncio.TimeoutError:
                    logger.error(f"Timeout updating {symbol}")
                    failed_symbols.append(symbol)
                    await self.session.rollback()
                except Exception as e:
                    logger.error(f"Failed to update {symbol}: {e}")
                    failed_symbols.append(symbol)
                    await self.session.rollback()
                
                if processed_count % 10 == 0:
                    await asyncio.sleep(1)
        
        return success_count, failed_symbols, batch_number

    def _determine_status(self, total, success, failed):
        if failed:
            if success == 0:
                return "failed", f"All {total} symbols failed to update"
            return "completed_with_errors", f"Updated {success}/{total} symbols successfully"
        return "success", f"Successfully updated all {success} symbols"

    async def _run_adjustment_check(self, request):
        if request.check_adjustments and settings.ADJUSTMENT_CHECK_ENABLED:
            try:
                return await self.check_adjustments(
                    auto_fix=request.auto_fix_adjustments
                )
            except Exception as e:
                logger.error(f"Adjustment check failed: {e}")
                return {"error": str(e)}
        return None

    async def _determine_economic_date_range(self, request):
        date_from = self._calculate_date_from(request.date_from) if request.date_from else None
        date_to = self._calculate_date_to(request.date_to) if request.date_to else date.today()
        
        if date_from is None:
            from sqlalchemy import func, select
            from app.db.models import EconomicIndicator
            
            stmt = select(func.min(EconomicIndicator.date), func.max(EconomicIndicator.date)).where(EconomicIndicator.symbol == "DTB3")
            result = await self.session.execute(stmt)
            min_date, max_date = result.one()
            
            HISTORY_START = date(1954, 1, 1)
            
            if min_date and max_date:
                if min_date > date(1955, 1, 1):
                    date_from = HISTORY_START
                else:
                    date_from = max_date + timedelta(days=1)
            else:
                date_from = HISTORY_START
        
        return date_from, date_to
