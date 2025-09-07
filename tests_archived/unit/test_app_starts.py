from fastapi.testclient import TestClient

from app.main import app


def test_app_starts():
    with TestClient(app) as client:
        response = client.get("/__nonexistent__")
        assert response.status_code in (404, 200)
