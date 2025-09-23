import pytest


@pytest.mark.asyncio
async def test_v1_health(async_client):
    response = await async_client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Stock OHLCV API", "scope": "v1"}
