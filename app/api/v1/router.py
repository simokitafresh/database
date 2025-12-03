from fastapi import APIRouter

from .coverage import router as coverage_router
from .fetch import router as fetch_router
from .prices import router as prices_router
from .symbols import router as symbols_router
from .cron import router as cron_router
from .debug import router as debug_router
from .economic import router as economic_router
from .maintenance import router as maintenance_router
from .events import router as events_router

router = APIRouter(prefix="/v1")
router.include_router(symbols_router)
router.include_router(prices_router)
router.include_router(coverage_router)
router.include_router(fetch_router)
router.include_router(cron_router)
router.include_router(debug_router)
router.include_router(economic_router)
router.include_router(maintenance_router)
router.include_router(events_router)


@router.get("/health")
async def v1_health() -> dict:
    """Simple v1 health endpoint for platform health checks."""
    return {"status": "ok", "service": "Stock OHLCV API", "scope": "v1"}
