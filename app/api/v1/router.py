from fastapi import APIRouter

from .symbols import router as symbols_router
from .prices import router as prices_router

router = APIRouter(prefix="/v1")
router.include_router(symbols_router)
router.include_router(prices_router)

# Placeholder for future v1 endpoints (metrics)
