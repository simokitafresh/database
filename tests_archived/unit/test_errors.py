from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from app.api.errors import init_error_handlers, raise_http_error


def create_app() -> FastAPI:
    app = FastAPI()
    init_error_handlers(app)

    @app.get("/needs-int/{value}")
    async def needs_int(value: int) -> dict[str, int]:
        return {"value": value}

    @app.get("/limited")
    async def limited() -> None:
        raise_http_error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "too large")

    return app


def test_404_error_shape() -> None:
    client = TestClient(create_app())
    resp = client.get("/missing")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json() == {"error": {"code": "404", "message": "Not Found"}}


def test_422_error_shape() -> None:
    client = TestClient(create_app())
    resp = client.get("/needs-int/not-an-int")
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    body = resp.json()
    assert body["error"]["code"] == "422"
    assert "valid integer" in body["error"]["message"]


def test_413_error_shape() -> None:
    client = TestClient(create_app())
    resp = client.get("/limited")
    assert resp.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert resp.json() == {"error": {"code": "413", "message": "too large"}}
