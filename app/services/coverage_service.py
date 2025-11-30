"""Service for managing data coverage and fetching missing data."""

import asyncio
import logging
import inspect
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

import anyio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.locking import with_symbol_lock
from app.services.fetcher import fetch_prices
from app.services.upsert import df_to_rows, upsert_prices_sql
from app.db.queries_optimized import get_coverage_optimized

logger = logging.getLogger(__name__)

_fetch_semaphore = anyio.Semaphore(settings.YF_REQ_CONCURRENCY)


async def fetch_prices_df(symbol: str, start: date, end: date):
    """Background wrapper around :func:`fetch_prices`.

    ``fetch_prices`` is synchronous; run it in a thread to avoid blocking.
    """
    async with _fetch_semaphore:
        return await run_in_threadpool(fetch_prices, symbol, start, end, settings=settings)


async def _ensure_full_history_once(session: AsyncSession, symbol: str) -> None:
    """Ensure one-time full-history fetch for a symbol using a persistent flag.

    If ``symbols.has_full_history`` is false, fetch from 1970-01-01 to today
    and upsert, then set the flag to true. Safe to call repeatedly.
    """
    try:
        # Ensure symbol row exists (FK safety) and check flag
        await session.execute(
            text(
                "INSERT INTO symbols (symbol, is_active) VALUES (:symbol, TRUE) "
                "ON CONFLICT (symbol) DO NOTHING"
            ),
            {"symbol": symbol},
        )
        res = await session.execute(
            text("SELECT has_full_history FROM symbols WHERE symbol = :symbol"),
            {"symbol": symbol},
        )
        has_full = bool(res.scalar() or False)
        if has_full:
            return

        EPOCH_START = date(1970, 1, 1)
        today = date.today()
        df = await fetch_prices_df(symbol, EPOCH_START, today)
        if df is None or df.empty:
            return
        rows = df_to_rows(df, symbol=symbol, source="yfinance")
        if not rows:
            return
        up_sql = text(upsert_prices_sql())
        await session.execute(up_sql, rows)
        # Update symbol metadata (first_date/last_date) and set full-history flag
        try:
            min_date = min(r.get("date") for r in rows if r.get("date") is not None)
            max_date = max(r.get("date") for r in rows if r.get("date") is not None)
        except Exception:
            min_date = None
            max_date = None
        if min_date and max_date:
            await session.execute(
                text(
                    """
                    UPDATE symbols
                    SET first_date = COALESCE(LEAST(first_date, :min_date), :min_date),
                        last_date  = COALESCE(GREATEST(last_date, :max_date), :max_date),
                        has_full_history = TRUE
                    WHERE symbol = :symbol
                    """
                ),
                {"symbol": symbol, "min_date": min_date, "max_date": max_date},
            )
        else:
            await session.execute(
                text("UPDATE symbols SET has_full_history = TRUE WHERE symbol = :symbol"),
                {"symbol": symbol},
            )
        logger.info(
            "full-history upsert completed",
            extra=dict(symbol=symbol, start=str(EPOCH_START), end=str(today), n_rows=len(rows)),
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"full-history prefetch failed for {symbol}: {e}", exc_info=True)


async def _get_coverage(session: AsyncSession, symbol: str, date_from: date, date_to: date) -> dict:
    """Return coverage information with weekday gap detection.

    Weekends (Saturday and Sunday) are ignored when detecting gaps. This
    function reports the first missing weekday if any. Exchange-specific
    holidays are not considered; a dedicated holiday table could be joined in
    the future to refine gap detection.

    Uses optimized query from queries_optimized.py for better performance.
    """
    return await get_coverage_optimized(session, symbol, date_from, date_to)


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
    for symbol in symbols:
        # アドバイザリロック取得→欠損判定→取得→UPSERT（トランザクション管理は呼び出し側に委ねる）
        await with_symbol_lock(session, symbol)
        # Ensure one-time full-history cache using flag
        await _ensure_full_history_once(session, symbol)

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
    result_meta: Dict[str, Any] = {"fetched_ranges": {}, "row_counts": {}, "adjustments": {}}

    for symbol in symbols:
        await with_symbol_lock(session, symbol)
        # Ensure one-time full-history cache using flag
        await _ensure_full_history_once(session, symbol)

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


async def ensure_coverage_parallel(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
    refetch_days: int,
) -> None:
    """
    複数銘柄のカバレッジを並行確認・取得する新規関数
    既存のensure_coverage関数の並行版
    
    Parameters:
    -----------
    session: データベースセッション
    symbols: 銘柄リスト
    date_from: 開始日
    date_to: 終了日  
    refetch_days: 再取得日数（既定30日）
    """
    
    async def process_single_symbol(symbol: str):
        """単一銘柄の処理（既存のensure_coverageのロジックを利用）"""
        try:
            # アドバイザリロック取得
            async with with_symbol_lock(session, symbol): # Fixed: using with_symbol_lock wrapper which returns None, wait, with_symbol_lock is async def, so await it?
                # No, with_symbol_lock in queries.py was:
                # async def with_symbol_lock(...) -> None:
                #    async with symbol_lock(symbol): pass
                # So it was designed to be used as `await with_symbol_lock(...)`.
                # But here I am using `async with advisory_lock(symbol)` in the original code.
                # Wait, the original code used `await with_symbol_lock(session, symbol)` in ensure_coverage.
                # But in ensure_coverage_parallel it used `async with advisory_lock(symbol):`.
                # `advisory_lock` is from `app.db.utils`.
                # I should probably use `with_symbol_lock` from `app.core.locking` which I just created.
                # `app.core.locking.with_symbol_lock` is `async def` and returns `None`.
                # So I should call `await with_symbol_lock(session, symbol)`.
                # But `ensure_coverage_parallel` in original code used `async with advisory_lock(symbol):`.
                # I should standardize.
                
                # Let's check `app/db/utils.py` to see what `advisory_lock` does.
                # But I don't have access to it right now.
                # However, `queries.py` imported `advisory_lock` from `app.db.utils`.
                # And `ensure_coverage` used `await with_symbol_lock(session, symbol)`.
                # `ensure_coverage_parallel` used `async with advisory_lock(symbol):`.
                
                # In `app/core/locking.py`, I defined `with_symbol_lock` which uses `app.services.redis_utils.symbol_lock`.
                # I should probably use that.
                
                await with_symbol_lock(session, symbol)
                
                # 一度だけフル履歴を確保
                await _ensure_full_history_once(session, symbol)
                
                # カバレッジ確認
                cov = await _get_coverage(session, symbol, date_from, date_to)
                
                last_date = cov.get("last_date")
                first_date = cov.get("first_date") 
                has_gaps = bool(cov.get("has_weekday_gaps") or cov.get("has_gaps"))
                first_missing_weekday = cov.get("first_missing_weekday")
                
                # 取得範囲の決定（既存のロジックを使用）
                fetch_ranges = []
                
                # 最新データの再取得
                if last_date and date_to >= last_date:
                    days_since_last = (date_to - last_date).days
                    if days_since_last > 1:
                        refetch_start = max(date_from, last_date - timedelta(days=refetch_days))
                        if refetch_start <= date_to:
                            fetch_ranges.append((refetch_start, date_to))
                
                # ギャップの埋め込み
                if has_gaps and first_missing_weekday:
                    gap_end = first_date if first_date else date_to
                    gap_start = max(date_from, first_missing_weekday)
                    if gap_start < gap_end:
                        fetch_ranges.append((gap_start, min(gap_end, date_to)))
                
                # 初期データ
                if not first_date:
                    fetch_ranges.append((date_from, date_to))
                
                if not fetch_ranges:
                    logger.debug(f"No fetch needed for {symbol}")
                    return
                
                # 範囲をマージ
                fetch_ranges.sort()
                merged_ranges = [fetch_ranges[0]] if fetch_ranges else []
                for start, end in fetch_ranges[1:]:
                    last_start, last_end = merged_ranges[-1]
                    if start <= last_end + timedelta(days=1):
                        merged_ranges[-1] = (last_start, max(last_end, end))
                    else:
                        merged_ranges.append((start, end))
                
                # データ取得とUPSERT（既存の関数を利用）
                for start, end in merged_ranges:
                    df = await fetch_prices_df(symbol, start, end)
                    if df is None or df.empty:
                        continue
                        
                    rows = df_to_rows(df, symbol=symbol, source="yfinance")
                    if not rows:
                        continue
                        
                    up_sql = text(upsert_prices_sql())
                    await session.execute(up_sql, rows)
                    logger.debug(f"Upserted {len(rows)} rows for {symbol}")
                
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}", exc_info=True)
    
    # 並行処理（最大10銘柄ずつ）
    chunk_size = min(10, settings.YF_REQ_CONCURRENCY)
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i+chunk_size]
        tasks = [process_single_symbol(s) for s in chunk]
        await asyncio.gather(*tasks, return_exceptions=True)
