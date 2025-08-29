from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.symbols import SymbolOut

router = APIRouter()


@router.get("/symbols", response_model=list[SymbolOut])
async def list_symbols(
    active: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[SymbolOut]:
    """Return symbols, optionally filtered by active flag.

    This is a stub implementation that delegates to raw SQL execution
    on the provided session. The repository layer will replace this
    logic in later tasks.
    """
    stmt = text("SELECT symbol FROM symbols")
    params: dict[str, Any] = {}
    if active is not None:
        stmt = text("SELECT symbol FROM symbols WHERE is_active = :active")
        params["active"] = active

    result = await session.execute(stmt, params)
    rows = result.fetchall()
    return [SymbolOut(symbol=row.symbol) for row in rows]
