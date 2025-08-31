from fastapi import APIRouter

from .metrics import router as metrics_router
from .prices import router as prices_router
from .symbols import router as symbols_router

router = APIRouter(prefix="/v1")
router.include_router(symbols_router)
router.include_router(prices_router)
router.include_router(metrics_router)


@router.get("/health")
async def v1_health() -> dict:
    """Simple v1 health endpoint for platform health checks."""
    return {"status": "ok", "service": "Stock OHLCV API", "scope": "v1"}
