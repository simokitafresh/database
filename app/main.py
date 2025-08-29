from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import init_error_handlers
from app.api.v1.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.cors import create_cors_middleware
from app.core.middleware import RequestIDMiddleware


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
init_error_handlers(app)

app.add_middleware(RequestIDMiddleware)
cors = create_cors_middleware(settings)
if cors:
    app.add_middleware(*cors)

app.include_router(health_router)
app.include_router(v1_router)
