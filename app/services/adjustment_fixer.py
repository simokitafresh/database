"""Service for fixing detected price adjustments."""

import logging
import uuid
from datetime import date, timedelta, datetime
from typing import Any, Dict, Optional

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Price, FetchJob

logger = logging.getLogger(__name__)

class AdjustmentFixer:
    """Handles fixing of detected price adjustments by refetching data."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        
    async def auto_fix_symbol(self, symbol: str) -> Dict[str, Any]:
        """Automatically fix a symbol by deleting and re-fetching data.
        
        Deletes all existing price data for the symbol and creates a
        fetch job to retrieve fresh data from yfinance with full history.
        
        Args:
            symbol: Symbol to fix.
            
        Returns:
            Dictionary containing fix operation results.
        """
        result = {
            "symbol": symbol,
            "deleted_rows": 0,
            "job_created": False,
            "job_id": None,
            "date_range": None,
            "error": None,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        try:
            # Get the date range of existing data before deletion
            range_result = await self.session.execute(
                select(
                    func.min(Price.date).label("first_date"),
                    func.max(Price.date).label("last_date")
                ).where(Price.symbol == symbol)
            )
            date_range = range_result.fetchone()
            
            # Determine date range for refetch
            if date_range and date_range.first_date:
                # Use existing data range, extended to today
                fetch_from = date_range.first_date
                fetch_to = date.today()
            else:
                # Default to 20 years of history
                fetch_from = date.today() - timedelta(days=365 * 20)
                fetch_to = date.today()
            
            result["date_range"] = {
                "from": fetch_from.isoformat(),
                "to": fetch_to.isoformat(),
            }
            
            # Delete existing price data
            delete_stmt = delete(Price).where(Price.symbol == symbol)
            delete_result = await self.session.execute(delete_stmt)
            result["deleted_rows"] = delete_result.rowcount
            
            # Create a fetch job to re-download data with full history
            job_id = str(uuid.uuid4())[:8]  # Short UUID for job ID
            job = FetchJob(
                job_id=job_id,
                symbols=[symbol],
                status="pending",
                date_from=fetch_from,
                date_to=fetch_to,
                interval="1d",
                force_refresh=True,  # Force fresh data
                priority="high",  # High priority for fixes
            )
            self.session.add(job)
            await self.session.flush()
            
            result["job_created"] = True
            result["job_id"] = job_id
            
            await self.session.commit()
            
            logger.info(
                f"Auto-fix for {symbol}: deleted {result['deleted_rows']} rows, "
                f"created job {result['job_id']} for {fetch_from} to {fetch_to}"
            )
            
        except Exception as e:
            logger.error(f"Auto-fix failed for {symbol}: {str(e)}")
            result["error"] = str(e)
            await self.session.rollback()
        
        return result
