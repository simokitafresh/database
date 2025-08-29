import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middleware import RequestIDMiddleware, get_request_id


def test_request_id_header_and_logging(caplog):
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        logging.getLogger("test").info("req %s", get_request_id())
        return {"status": "ok"}

    caplog.set_level(logging.INFO)
    client = TestClient(app)
    resp = client.get("/ping")
    rid = resp.headers.get("X-Request-ID")
    assert rid
    assert any(rid in r.message for r in caplog.records)
