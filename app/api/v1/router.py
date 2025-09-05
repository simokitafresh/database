from fastapi import APIRouter

from .coverage import router as coverage_router
from .fetch import router as fetch_router
from .prices import router as prices_router
from .symbols import router as symbols_router

router = APIRouter(prefix="/v1")
router.include_router(symbols_router)
router.include_router(prices_router)
router.include_router(coverage_router)
router.include_router(fetch_router)


@router.get("/health")
async def v1_health() -> dict:
    """Simple v1 health endpoint for platform health checks."""
    return {"status": "ok", "service": "Stock OHLCV API", "scope": "v1"}
