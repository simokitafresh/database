from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
def lifespan(_: FastAPI):
    """Placeholder lifespan for future DB setup."""
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Health check endpoint returning a simple OK response."""
    return {"status": "ok"}
