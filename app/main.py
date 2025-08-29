from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Placeholder lifespan for future DB setup.

    FastAPI requires an *asynchronous* generator when using
    ``@asynccontextmanager``. Returning a synchronous generator causes
    ``AttributeError('__anext__')`` during application startup. This async
    variant ensures compatibility.
    """
    try:
        # Startup hooks (e.g., schedule DB initialisation) would go here.
        yield
    finally:
        # Shutdown hooks (cleanup resources) would go here.
        pass


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Health check endpoint returning a simple OK response."""
    return {"status": "ok"}
