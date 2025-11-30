"""Cron job endpoints for scheduled data updates."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.api.deps import get_session
from app.core.config import settings
from app.schemas.cron import CronDailyUpdateRequest, CronDailyUpdateResponse, CronStatusResponse
from app.services.daily_update_service import DailyUpdateService

router = APIRouter()
logger = logging.getLogger(__name__)


def verify_cron_token(x_cron_secret: Optional[str] = Header(None)) -> bool:
    """Verify cron authentication token."""
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
    """Execute daily stock data update."""
    service = DailyUpdateService(session)
    return await service.execute_daily_update(request)


@router.get("/status", response_model=CronStatusResponse, summary="Get cron job status")
async def get_cron_status(
    cron_token: str = Header(None, alias="X-Cron-Secret"),
    session: AsyncSession = Depends(get_session),
) -> CronStatusResponse:
    """Get current status of cron jobs"""
    verify_cron_token(cron_token)

    try:
        # Check if we can access symbols table
        result = await session.execute(
            text("SELECT COUNT(*) as count FROM symbols WHERE is_active = true")
        )
        active_symbols = result.scalar()

        return CronStatusResponse(
            status="active",
            last_run=None,
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


@router.post("/daily-economic-update", response_model=CronDailyUpdateResponse)
async def daily_economic_update(
    request: CronDailyUpdateRequest,
    session: AsyncSession = Depends(get_session),
    authenticated: bool = Depends(verify_cron_token),
) -> CronDailyUpdateResponse:
    """Execute daily economic data update (FRED)."""
    service = DailyUpdateService(session)
    return await service.execute_economic_update(request)


@router.post("/adjustment-check", response_model=dict, summary="Check for price adjustments")
async def adjustment_check(
    symbols: Optional[list[str]] = None,
    auto_fix: bool = False,
    session: AsyncSession = Depends(get_session),
    authenticated: bool = Depends(verify_cron_token),
) -> dict:
    """Check for and optionally fix price adjustments."""
    service = DailyUpdateService(session)
    return await service.check_adjustments(symbols, auto_fix)
