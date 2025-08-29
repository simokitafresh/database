from datetime import date
import inspect
from unittest.mock import AsyncMock

import pytest

from app.db import queries


@pytest.mark.asyncio
async def test_get_prices_resolved_signature_and_sql():
    sig = inspect.signature(queries.get_prices_resolved)
    assert list(sig.parameters) == ["session", "symbol", "from_", "to"]

    session = AsyncMock()
    session.execute.return_value.fetchall.return_value = []
    await queries.get_prices_resolved(session, "AAA", date(2024, 1, 1), date(2024, 1, 2))
    executed_sql = session.execute.call_args[0][0].text
    assert "get_prices_resolved" in executed_sql


@pytest.mark.asyncio
async def test_list_symbols_signature_and_sql():
    sig = inspect.signature(queries.list_symbols)
    assert list(sig.parameters) == ["session", "active"]

    session = AsyncMock()
    session.execute.return_value.fetchall.return_value = []
    await queries.list_symbols(session, active=True)
    executed_sql = session.execute.call_args[0][0].text
    assert "FROM symbols" in executed_sql
