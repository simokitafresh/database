from fastapi import APIRouter

from .symbols import router as symbols_router
from .prices import router as prices_router
from .metrics import router as metrics_router

router = APIRouter(prefix="/v1")
router.include_router(symbols_router)
router.include_router(prices_router)
router.include_router(metrics_router)
