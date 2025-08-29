import pytest
from unittest.mock import AsyncMock

from app.db.utils import advisory_lock


@pytest.mark.asyncio
async def test_advisory_lock_executes_correct_sql():
    conn = AsyncMock()
    await advisory_lock(conn, "META")

    conn.execute.assert_awaited_once()
    args, kwargs = conn.execute.call_args
    sql = str(args[0])
    params = args[1]
    assert "pg_advisory_xact_lock" in sql
    assert "hashtext" in sql
    assert params["symbol"] == "META"
