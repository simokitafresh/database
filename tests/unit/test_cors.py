from app.core.config import Settings
from app.core.cors import create_cors_middleware
from fastapi.middleware.cors import CORSMiddleware


def test_cors_middleware_disabled_when_origins_empty():
    settings = Settings(CORS_ALLOW_ORIGINS="")
    assert create_cors_middleware(settings) is None


def test_cors_middleware_enabled_with_origins():
    settings = Settings(CORS_ALLOW_ORIGINS="https://a.com, https://b.com")
    middleware = create_cors_middleware(settings)
    assert middleware is not None
    cls, options = middleware
    assert cls is CORSMiddleware
    assert options["allow_origins"] == ["https://a.com", "https://b.com"]
