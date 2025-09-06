"""Database access helpers for price coverage and retrieval."""

from __future__ import annotations

from datetime import date, timedelta
import logging
from typing import Any, List, Mapping, Optional, Sequence, cast, Dict

import anyio
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.db.utils import advisory_lock
from app.services.fetcher import fetch_prices
from app.services.upsert import df_to_rows, upsert_prices_sql


# Preserve legacy alias for tests and backward compatibility
async def with_symbol_lock(session: AsyncSession, symbol: str) -> None:
    """Acquire an advisory lock for the given symbol within a transaction."""
    conn = await session.connection()
    await advisory_lock(conn, symbol)


_fetch_semaphore = anyio.Semaphore(settings.YF_REQ_CONCURRENCY)


async def fetch_prices_df(symbol: str, start: date, end: date):
    """Background wrapper around :func:`fetch_prices`.

    ``fetch_prices`` is synchronous; run it in a thread to avoid blocking.
    """

    async with _fetch_semaphore:
        return await run_in_threadpool(fetch_prices, symbol, start, end, settings=settings)


async def _get_coverage(session: AsyncSession, symbol: str, date_from: date, date_to: date) -> dict:
    """Return coverage information with weekday gap detection.

    Weekends (Saturday and Sunday) are ignored when detecting gaps. This
    function reports the first missing weekday if any. Exchange-specific
    holidays are not considered; a dedicated holiday table could be joined in
    the future to refine gap detection.
    """

    sql = text(
        """
        WITH rng AS (
            SELECT CAST(:date_from AS date) AS dfrom, CAST(:date_to AS date) AS dto
        ),
        cov AS (
            SELECT MIN(date) AS first_date,
                   MAX(date) AS last_date,
                   COUNT(*)  AS cnt
            FROM prices
            WHERE symbol = :symbol
              AND date BETWEEN (SELECT dfrom FROM rng) AND (SELECT dto FROM rng)
        ),
        gaps AS (
            SELECT p.date AS cur_date,
                   LEAD(p.date) OVER (ORDER BY p.date) AS next_date
            FROM prices p
            WHERE p.symbol = :symbol
              AND p.date BETWEEN (SELECT dfrom FROM rng) AND (SELECT dto FROM rng)
        ),
        weekdays_between AS (
            SELECT g.cur_date, g.next_date, (gs.d)::date AS d
            FROM (
                SELECT * FROM gaps WHERE next_date IS NOT NULL
            ) AS g
            JOIN LATERAL generate_series(
                g.cur_date + INTERVAL '1 day',
                g.next_date - INTERVAL '1 day',
                INTERVAL '1 day'
            ) AS gs(d) ON TRUE
            WHERE EXTRACT(ISODOW FROM gs.d) BETWEEN 1 AND 5
        ),
        weekday_gaps AS (
            SELECT cur_date, next_date, MIN(d)::date AS first_weekday_missing
            FROM weekdays_between
            GROUP BY cur_date, next_date
        )
        SELECT
            (SELECT first_date FROM cov) AS first_date,
            (SELECT last_date  FROM cov) AS last_date,
            (SELECT cnt        FROM cov) AS cnt,
            EXISTS (SELECT 1 FROM weekday_gaps) AS has_weekday_gaps,
            (SELECT MIN(first_weekday_missing) FROM weekday_gaps) AS first_missing_weekday
        """
    )

    res = await session.execute(
        sql, {"symbol": symbol, "date_from": date_from, "date_to": date_to}
    )
    row = cast(Mapping[str, Any], res.mappings().first() or {})
    return dict(row)


async def ensure_coverage(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
    refetch_days: int,
) -> None:
    """Ensure price data coverage for symbols.

    For each symbol the function acquires an advisory lock, checks coverage
    with weekday-aware gap detection and fetches the minimal range required to
    bring the database up to date including ``refetch_days`` worth of recent
    history.
    
    Note: This function does not manage transactions. The caller should
    ensure proper transaction management.
    """

    logger = logging.getLogger(__name__)
    for symbol in symbols:
        # アドバイザリロック取得→欠損判定→取得→UPSERT（トランザクション管理は呼び出し側に委ねる）
        await with_symbol_lock(session, symbol)

        cov = await _get_coverage(session, symbol, date_from, date_to)

        last_date: Optional[date] = cov.get("last_date")
        first_date: Optional[date] = cov.get("first_date")
        has_gaps: bool = bool(cov.get("has_weekday_gaps") or cov.get("has_gaps"))
        first_missing_weekday: Optional[date] = cov.get("first_missing_weekday")

        logger.debug(
            "coverage result",
            extra=dict(
                symbol=symbol,
                date_from=str(date_from),
                date_to=str(date_to),
                first_date=str(first_date) if first_date else None,
                last_date=str(last_date) if last_date else None,
                has_gaps=has_gaps,
                first_missing_weekday=str(first_missing_weekday)
                if first_missing_weekday
                else None,
            ),
        )

        # 取得範囲を決定（重複を避けるため、本当に必要な部分のみ取得）
        fetch_ranges = []
        
        # 1) 最新データの再取得（refetch_days分のみ、ただし最新データが新しい場合はスキップ）
        if last_date and date_to >= last_date:
            # 最新データが1日以内の場合は再取得をスキップ（市場時間を考慮）
            days_since_last = (date_to - last_date).days
            if days_since_last > 1:  # 1日より古い場合のみ再取得
                refetch_start = max(date_from, last_date - timedelta(days=refetch_days))
                if refetch_start <= date_to:
                    fetch_ranges.append((refetch_start, date_to))
                    logger.debug(
                        "adding recent data refetch range",
                        extra=dict(symbol=symbol, start=str(refetch_start), end=str(date_to), days_since_last=days_since_last)
                    )
            else:
                logger.debug(
                    "skipping recent data refetch - data is fresh",
                    extra=dict(symbol=symbol, last_date=str(last_date), days_since_last=days_since_last)
                )

        # 2) ギャップの埋め込み（欠損部分のみ）
        if has_gaps and first_missing_weekday:
            # ギャップの開始日から最初のデータまでの範囲
            gap_end = first_date if first_date else date_to
            gap_start = max(date_from, first_missing_weekday)
            if gap_start < gap_end:
                # 既存の範囲と重複しないように調整
                if not fetch_ranges or gap_start < fetch_ranges[0][0]:
                    fetch_ranges.append((gap_start, min(gap_end, date_to)))
                    logger.debug(
                        "adding gap fill range",
                        extra=dict(symbol=symbol, start=str(gap_start), end=str(min(gap_end, date_to)))
                    )

        # 3) 初期データ（データベースに何もない場合）
        if not first_date:
            fetch_ranges.append((date_from, date_to))
            logger.debug(
                "adding initial data range",
                extra=dict(symbol=symbol, start=str(date_from), end=str(date_to))
            )

        # 範囲をマージして重複を避ける
        if not fetch_ranges:
            logger.debug(
                "no data fetch needed - database coverage is complete",
                extra=dict(symbol=symbol)
            )
            continue

        # 取得範囲を統合
        fetch_ranges.sort()
        merged_ranges = [fetch_ranges[0]]
        for start, end in fetch_ranges[1:]:
            last_start, last_end = merged_ranges[-1]
            if start <= last_end + timedelta(days=1):
                # 重複または隣接する範囲をマージ
                merged_ranges[-1] = (last_start, max(last_end, end))
            else:
                merged_ranges.append((start, end))

        # 各範囲について個別に取得
        for start, end in merged_ranges:
            logger.debug(
                "fetching data range",
                extra=dict(symbol=symbol, start=str(start), end=str(end))
            )

            df = await fetch_prices_df(symbol=symbol, start=start, end=end)
            if df is None or df.empty:
                logger.debug(
                    "yfinance returned empty frame",
                    extra=dict(symbol=symbol, start=str(start), end=str(end)),
                )
                continue
            
            rows = df_to_rows(df, symbol=symbol, source="yfinance")
            if not rows:
                logger.debug(
                    "no valid rows after NaN filtering",
                    extra=dict(symbol=symbol, start=str(start), end=str(end)),
                )
                continue
            
            up_sql = text(upsert_prices_sql())
            await session.execute(up_sql, rows)
            logger.debug(
                "upserted rows for range",
                extra=dict(symbol=symbol, n_rows=len(rows), start=str(start), end=str(end)),
            )


async def find_earliest_available_date(symbol: str, target_date: date) -> date:
    """
    効率的に最古の利用可能日を探索

    Parameters
    ----------
    symbol : str
        検索対象のシンボル
    target_date : date
        要求された開始日

    Returns
    -------
    date
        実際に利用可能な最古日
    """
    import yfinance as yf
    from datetime import timedelta

    test_dates = [
        date(1970, 1, 1),
        date(1980, 1, 1),
        date(1990, 1, 1),
        date(2000, 1, 1),
        date(2010, 1, 1),
    ]

    for test_date in test_dates:
        if test_date >= target_date:
            try:
                df = yf.download(
                    symbol,
                    start=test_date,
                    end=test_date + timedelta(days=30),
                    progress=False,
                    timeout=5
                )
                if not df.empty:
                    return df.index[0].date()
            except:
                continue

    return max(target_date, date(2000, 1, 1))


async def ensure_coverage_with_auto_fetch(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
    refetch_days: int,
) -> Dict[str, Any]:
    """
    データカバレッジ確保（最古日自動検出付き）

    Parameters
    ----------
    session : AsyncSession
        データベースセッション
    symbols : Sequence[str]
        対象シンボルリスト
    date_from : date
        要求開始日
    date_to : date
        要求終了日
    refetch_days : int
        再取得日数

    Returns
    -------
    Dict[str, Any]
        取得結果のメタ情報
    """
    logger = logging.getLogger(__name__)
    result_meta = {
        "fetched_ranges": {},
        "row_counts": {},
        "adjustments": {}
    }

    for symbol in symbols:
        await with_symbol_lock(session, symbol)

        cov = await _get_coverage(session, symbol, date_from, date_to)

        if not cov.get("first_date") or cov.get("has_gaps"):
            logger.info(f"Detecting available date range for {symbol}")

            actual_start = await find_earliest_available_date(symbol, date_from)

            if actual_start > date_from:
                result_meta["adjustments"][symbol] = (
                    f"requested {date_from}, actual {actual_start}"
                )
                logger.warning(
                    f"Symbol {symbol}: Auto-adjusting date_from "
                    f"from {date_from} to {actual_start}"
                )

            logger.info(f"Auto-fetching {symbol} from {actual_start} to {date_to}")
            df = await fetch_prices_df(symbol=symbol, start=actual_start, end=date_to)

            if df is not None and not df.empty:
                rows = df_to_rows(df, symbol=symbol, source="yfinance")
                if rows:
                    up_sql = text(upsert_prices_sql())
                    await session.execute(up_sql, rows)

                    result_meta["fetched_ranges"][symbol] = {
                        "from": str(actual_start),
                        "to": str(date_to)
                    }
                    result_meta["row_counts"][symbol] = len(rows)

                    logger.info(
                        f"Saved {len(rows)} rows for {symbol} "
                        f"({actual_start} to {date_to})"
                    )

    return result_meta


async def get_prices_resolved(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
) -> List[dict]:
    """Fetch price rows via the ``get_prices_resolved`` SQL function.

    The function accepts multiple symbols and returns a combined, sorted list
    of dictionaries.
    """

    out: List[dict] = []
    sql = text("SELECT * FROM get_prices_resolved(:symbol, :date_from, :date_to)")
    for s in symbols:
        res = await session.execute(
            sql, {"symbol": s, "date_from": date_from, "date_to": date_to}
        )
        out.extend([dict(m) for m in res.mappings().all()])
    out.sort(key=lambda r: (r["date"], r["symbol"]))
    return out


LIST_SYMBOLS_SQL = (
    "SELECT symbol, name, exchange, currency, is_active, first_date, last_date "
    "FROM symbols "
    "WHERE (:active::boolean IS NULL OR is_active = :active) "
    "ORDER BY symbol"
)


async def list_symbols(session: AsyncSession, active: bool | None = None) -> Sequence[Any]:
    """Return symbol metadata optionally filtered by activity."""

    result = await session.execute(text(LIST_SYMBOLS_SQL), {"active": active})
    return result.fetchall()


__all__ = [
    "ensure_coverage",
    "ensure_coverage_with_auto_fetch",  # 追加
    "find_earliest_available_date",  # 追加
    "get_prices_resolved",
    "list_symbols",
    "LIST_SYMBOLS_SQL",
]
