from __future__ import annotations

from datetime import date
from typing import Dict, List

import pandas as pd
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.errors import raise_http_error
from app.schemas.metrics import MetricsOut
from app.services import normalize
from app.services.metrics import compute_metrics

router = APIRouter()


def _as_mapping(row: object) -> dict:  # pragma: no cover - helper
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    if isinstance(row, dict):
        return row
    return {k: getattr(row, k) for k in row.__dict__}


@router.get("/metrics", response_model=list[MetricsOut])
async def get_metrics(
    symbols: str = Query(..., description="Comma separated symbols"),
    from_: date = Query(..., alias="from"),
    to: date = Query(..., alias="to"),
    session: AsyncSession = Depends(get_session),
) -> List[MetricsOut]:
    """Compute metrics for the given symbols and date range.

    Database access is intentionally represented via a simple SQL query whose
    result is transformed into DataFrames before passing to
    :func:`compute_metrics`. The query is expected to be mocked in tests.
    """

    if to < from_:
        raise_http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "'from' must be on or before 'to'",
        )

    symbol_list = [normalize.normalize_symbol(s) for s in symbols.split(",") if s]
    result = await session.execute(
        "SELECT symbol, date, close FROM prices WHERE symbol = ANY(:symbols) "
        "AND date BETWEEN :from AND :to",
        {"symbols": symbol_list, "from": from_, "to": to},
    )
    rows = [_as_mapping(r) for r in result.fetchall()]

    frames: Dict[str, pd.DataFrame] = {}
    for sym in symbol_list:
        sym_rows = [r for r in rows if r["symbol"] == sym]
        if sym_rows:
            frames[sym] = pd.DataFrame(sym_rows)
        else:
            frames[sym] = pd.DataFrame()

    metrics = compute_metrics(frames)
    return [MetricsOut(**m) for m in metrics]


__all__ = ["router", "get_metrics"]
