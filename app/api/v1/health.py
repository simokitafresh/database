from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Health check endpoint returning a simple OK response."""
    return {"status": "ok"}
