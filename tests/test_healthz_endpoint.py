import pytest


@pytest.mark.asyncio
async def test_healthz_endpoint(async_client):
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
