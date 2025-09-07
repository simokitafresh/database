from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.db.queries import list_symbols as db_list_symbols
from app.schemas.symbols import SymbolOut

router = APIRouter()


@router.get("/symbols", response_model=list[SymbolOut])
async def list_symbols(
    active: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[SymbolOut]:
    """Return symbols, optionally filtered by active flag.

    This uses the database query function to properly retrieve all symbol data
    including metadata like creation dates and symbol details.
    """
    rows = await db_list_symbols(session, active)
    return [SymbolOut(**row) for row in rows]
