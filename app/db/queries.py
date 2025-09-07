"""Database access helpers for price coverage and retrieval."""

from __future__ import annotations

import logging
import inspect
from datetime import date, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, cast

import anyio
from sqlalchemy import text
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

    res = await session.execute(sql, {"symbol": symbol, "date_from": date_from, "date_to": date_to})
    mappings = res.mappings()
    first = getattr(mappings, "first", None)
    row_obj = first() if callable(first) else None
    if inspect.isawaitable(row_obj):
        row_obj = await row_obj
    row = cast(Mapping[str, Any], row_obj or {})
    return dict(row)


async def _symbol_has_any_prices(session: AsyncSession, symbol: str) -> bool:
    """Return True if any price rows exist for the symbol (any date)."""
    res = await session.execute(text("SELECT 1 FROM prices WHERE symbol = :symbol LIMIT 1"), {"symbol": symbol})
    first = getattr(res, "first", None)
    row = first() if callable(first) else None
    if inspect.isawaitable(row):
        row = await row
    return row is not None


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

        # Prefetch full history if not yet fully cached (flag-based, single full-range fetch)
        try:
            # Ensure symbol row exists (FK safety); ignore if exists
            await session.execute(
                text("INSERT INTO symbols (symbol, is_active) VALUES (:symbol, TRUE) ON CONFLICT (symbol) DO NOTHING"),
                {"symbol": symbol},
            )
            EPOCH_START = date(1970, 1, 1)
            today = date.today()
            res = await session.execute(
                text("SELECT has_full_history FROM symbols WHERE symbol = :symbol"),
                {"symbol": symbol},
            )
            has_full = bool(res.scalar() or False)
        except Exception:
            has_full = True  # be conservative on errors

        if not has_full:
            try:
                df_full = await fetch_prices_df(symbol, EPOCH_START, today)
                if df_full is not None and not df_full.empty:
                    rows_full = df_to_rows(df_full, symbol=symbol, source="yfinance")
                    if rows_full:
                        up_sql = text(upsert_prices_sql())
                        await session.execute(up_sql, rows_full)
                        await session.execute(
                            text("UPDATE symbols SET has_full_history = TRUE WHERE symbol = :symbol"),
                            {"symbol": symbol},
                        )
                        logger.info(
                            "full-history upsert completed",
                            extra=dict(symbol=symbol, start=str(EPOCH_START), end=str(today), n_rows=len(rows_full)),
                        )
            except Exception as e:  # pragma: no cover
                logger.warning(
                    f"full-history prefetch failed for {symbol}: {e}", exc_info=True
                )

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
                first_missing_weekday=str(first_missing_weekday) if first_missing_weekday else None,
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
                        extra=dict(
                            symbol=symbol,
                            start=str(refetch_start),
                            end=str(date_to),
                            days_since_last=days_since_last,
                        ),
                    )
            else:
                logger.debug(
                    "skipping recent data refetch - data is fresh",
                    extra=dict(
                        symbol=symbol, last_date=str(last_date), days_since_last=days_since_last
                    ),
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
                        extra=dict(
                            symbol=symbol, start=str(gap_start), end=str(min(gap_end, date_to))
                        ),
                    )

        # 3) 初期データ（データベースに何もない場合）
        if not first_date:
            fetch_ranges.append((date_from, date_to))
            logger.debug(
                "adding initial data range",
                extra=dict(symbol=symbol, start=str(date_from), end=str(date_to)),
            )

        # 範囲をマージして重複を避ける
        if not fetch_ranges:
            logger.debug(
                "no data fetch needed - database coverage is complete", extra=dict(symbol=symbol)
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
                "fetching data range", extra=dict(symbol=symbol, start=str(start), end=str(end))
            )

            df = await fetch_prices_df(symbol, start, end)
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
    """効率的に最古の利用可能日を探索（非同期対応）"""
    logger = logging.getLogger(__name__)

    def _sync_find_earliest() -> date:
        """同期処理を別スレッドで実行"""
        from datetime import timedelta

        import yfinance as yf

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
                        timeout=5,
                    )
                    if not df.empty:
                        return df.index[0].date()
                except Exception as e:
                    logger.debug(f"Test date {test_date} failed for {symbol}: {e}")
                    continue

        return max(target_date, date(2000, 1, 1))

    # 別スレッドで実行
    return await run_in_threadpool(_sync_find_earliest)


async def binary_search_yf_start_date(
    symbol: str,
    min_date: date,
    max_date: date,
    target_date: date,
) -> date:
    """Yahoo Financeの最古利用可能日を二分探索で特定"""
    logger = logging.getLogger(__name__)

    # 簡易実装: いくつかの代表的な日付をテスト
    test_dates = [
        date(1970, 1, 1),
        date(1980, 1, 1),
        date(1990, 1, 1),
        date(2000, 1, 1),
        date(2010, 1, 1),
        target_date,
    ]

    for test_date in test_dates:
        if test_date > max_date:
            break

        try:
            df = await fetch_prices_df(
                symbol=symbol,
                start=test_date,
                end=test_date + timedelta(days=30),
            )
            if df is not None and not df.empty:
                return test_date
        except Exception as e:
            logger.debug(f"Test date {test_date} failed for {symbol}: {e}")
            continue

    return target_date


async def ensure_coverage_unified(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
    refetch_days: int,
) -> Dict[str, Any]:
    """統一されたカバレッジ確保処理"""
    logger = logging.getLogger(__name__)
    result_meta: Dict[str, Any] = {"fetched_ranges": {}, "row_counts": {}, "adjustments": {}}

    for symbol in symbols:
        await with_symbol_lock(session, symbol)

        # 既存データのカバレッジ確認
        cov = await _get_coverage(session, symbol, date_from, date_to)

        # データがない場合、Yahoo Financeで利用可能な範囲を探索
        if not cov.get("first_date") or cov.get("has_weekday_gaps"):
            # 実際の利用可能日を探索
            actual_start = await binary_search_yf_start_date(
                symbol, date(1970, 1, 1), date_to, date_from
            )

            # 境界条件チェック
            if actual_start > date_to:
                logger.warning(
                    f"Symbol {symbol}: No data available in requested range "
                    f"({date_from} to {date_to}). Data starts from {actual_start}"
                )
                result_meta["adjustments"][symbol] = {
                    "status": "no_data_in_range",
                    "requested_start": str(date_from),
                    "requested_end": str(date_to),
                    "actual_start": str(actual_start),
                    "message": f"Data only available from {actual_start}",
                }
                continue

            # 部分データの場合
            if actual_start > date_from:
                logger.info(
                    f"Symbol {symbol}: Adjusting date range. "
                    f"Requested: {date_from}, Available: {actual_start}"
                )
                result_meta["adjustments"][symbol] = {
                    "status": "partial_data",
                    "requested_start": str(date_from),
                    "actual_start": str(actual_start),
                    "message": "Data adjusted to available range",
                }

            # データ取得
            df = await fetch_prices_df(
                symbol=symbol,
                start=actual_start,
                end=date_to,
            )

            if df is not None and not df.empty:
                rows = df_to_rows(df, symbol=symbol, source="yfinance")
                if rows:
                    up_sql = text(upsert_prices_sql())
                    await session.execute(up_sql, rows)

                    result_meta["fetched_ranges"][symbol] = {
                        "from": str(actual_start),
                        "to": str(date_to),
                    }
                    result_meta["row_counts"][symbol] = len(rows)

        # 既存のカバレッジ処理も実行
        else:
            await ensure_coverage(
                session=session,
                symbols=[symbol],
                date_from=date_from,
                date_to=date_to,
                refetch_days=refetch_days,
            )

    return result_meta


async def ensure_coverage_with_auto_fetch(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
    refetch_days: int,
) -> Dict[str, Any]:
    """統一実装にリダイレクト"""
    return await ensure_coverage_unified(
        session=session,
        symbols=symbols,
        date_from=date_from,
        date_to=date_to,
        refetch_days=refetch_days,
    )


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
        res = await session.execute(sql, {"symbol": s, "date_from": date_from, "date_to": date_to})
        out.extend([dict(m) for m in res.mappings().all()])
    out.sort(key=lambda r: (r["date"], r["symbol"]))
    return out


LIST_SYMBOLS_SQL = (
    "SELECT symbol, name, exchange, currency, is_active, first_date, last_date, created_at "
    "FROM symbols "
    "WHERE (:active IS NULL OR is_active = :active) "
    "ORDER BY symbol"
)


async def list_symbols(session: AsyncSession, active: bool | None = None) -> Sequence[Any]:
    """Return symbol metadata optionally filtered by activity."""

    if active is None:
        sql = "SELECT symbol, name, exchange, currency, is_active, first_date, last_date, created_at FROM symbols ORDER BY symbol"
        result = await session.execute(text(sql))
    else:
        sql = "SELECT symbol, name, exchange, currency, is_active, first_date, last_date, created_at FROM symbols WHERE is_active = :active ORDER BY symbol"
        result = await session.execute(text(sql), {"active": active})
    
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]


__all__ = [
    "ensure_coverage",
    "ensure_coverage_unified",  # 追加
    "ensure_coverage_with_auto_fetch",  # 追加
    "find_earliest_available_date",  # 追加
    "get_prices_resolved",
    "list_symbols",
    "LIST_SYMBOLS_SQL",
]
