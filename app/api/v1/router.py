from fastapi import APIRouter

from .symbols import router as symbols_router

router = APIRouter(prefix="/v1")
router.include_router(symbols_router)

# Placeholder for future v1 endpoints (prices, metrics)
