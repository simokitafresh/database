from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.cors import create_cors_middleware


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
    assert options["allow_credentials"] is True


def test_cors_middleware_wildcard_disables_credentials_and_uses_regex():
    settings = Settings(CORS_ALLOW_ORIGINS="*")
    middleware = create_cors_middleware(settings)
    assert middleware is not None
    cls, options = middleware
    assert cls is CORSMiddleware
    assert options["allow_origin_regex"] == ".*"
    assert options["allow_credentials"] is False


def test_cors_basic_flow_allows_origin_without_credentials():
    app = FastAPI()
    cls, kwargs = create_cors_middleware(Settings(CORS_ALLOW_ORIGINS="*"))
    app.add_middleware(cls, **kwargs)

    @app.get("/healthz")
    def _healthz() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    origin = "https://example.com"
    resp = client.get("/healthz", headers={"Origin": origin})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origin
    assert "access-control-allow-credentials" not in resp.headers
