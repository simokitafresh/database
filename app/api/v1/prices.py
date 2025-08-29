from __future__ import annotations

import logging
import time
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import settings
from app.schemas.prices import PriceRowOut
from app.services.normalize import normalize_symbol
from app.api.deps import get_session  # AsyncSession 依存性
from app.db import queries


router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_and_validate_symbols(symbols_raw: str) -> List[str]:
    """
    - カンマ分割 → trim → 空要素除去
    - 正規化（大文字、クラス株、サフィックス維持）
    - 去重
    - 上限チェック
    """
    if not symbols_raw:
        return []
    items = [s.strip() for s in symbols_raw.split(",")]
    items = [s for s in items if s]
    normalized = [normalize_symbol(s) for s in items]
    # unique & stable order
    seen = set()
    uniq = []
    for s in normalized:
        if s not in seen:
            uniq.append(s)
            seen.add(s)
    if len(uniq) > settings.API_MAX_SYMBOLS:
        raise HTTPException(status_code=422, detail="too many symbols requested")
    return uniq


@router.get("/prices", response_model=List[PriceRowOut])
async def get_prices(
    symbols: str = Query(..., description="Comma-separated symbols"),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    session=Depends(get_session),
):
    # --- validation ---
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="invalid date range")
    symbols_list = _parse_and_validate_symbols(symbols)
    if not symbols_list:
        return []

    # --- orchestration (欠損検出・再取得は内部サービスに委譲してもよい) ---
    # 1) 欠損カバレッジを確認し、不足分＋直近N日を取得してUPSERT（冪等）
    t0 = time.perf_counter()
    await queries.ensure_coverage(
        session=session,
        symbols=symbols_list,
        date_from=date_from,
        date_to=date_to,
        refetch_days=settings.YF_REFETCH_DAYS,
    )

    # 2) 透過解決済み結果を取得
    rows = await queries.get_prices_resolved(
        session=session,
        symbols=symbols_list,
        date_from=date_from,
        date_to=date_to,
    )

    n = len(rows)
    if n > settings.API_MAX_ROWS:
        raise HTTPException(status_code=413, detail="response too large")
    dt_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "prices served",
        extra=dict(
            symbols=symbols_list,
            date_from=str(date_from),
            date_to=str(date_to),
            rows=n,
            duration_ms=dt_ms,
        ),
    )
    return rows


__all__ = ["router", "get_prices"]
