import asyncio
import logging
import time
import io
from datetime import date, timedelta
from typing import Optional, Dict, List, Tuple, AsyncIterator
from urllib.error import HTTPError as URLlibHTTPError
from contextlib import redirect_stdout, redirect_stderr

import pandas as pd
import requests
import yfinance as yf
from requests.exceptions import HTTPError as RequestsHTTPError
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.logging import error_context, get_error_metrics
from app.core.rate_limit import get_rate_limiter, get_backoff, RateLimiter, ExponentialBackoff
from app.services.data_cleaner import DataCleaner

# yfinance の冗長な失敗ログ（"1 Failed download: ... possibly delisted" 等）を抑制
logging.getLogger("yfinance").setLevel(logging.ERROR)


def fetch_prices(
    symbol: str,
    start: date,
    end: date,
    *,
    settings: Settings,
    last_date: Optional[date] = None,
) -> pd.DataFrame:
    """Fetch adjusted OHLCV data for ``symbol`` between ``start`` and ``end``.

    Parameters
    ----------
    symbol:
        Ticker symbol understood by Yahoo Finance.
    start, end:
        Date range for the fetch. ``end`` is inclusive.
    settings:
        Application settings providing timeout and refetch parameters.
    last_date:
        Last date of existing data in the database.  If provided, the fetch will
        start from ``max(start, last_date - settings.YF_REFETCH_DAYS)`` to
        re-download the most recent ``N`` days for adjustments.

    Returns
    -------
    pandas.DataFrame
        Data frame with columns ``open``, ``high``, ``low``, ``close``,
        ``volume`` and a ``DatetimeIndex``.

    Note
    ----
    yfinance's end parameter is exclusive, so we add 1 day internally
    to ensure the end date is included in the results.
    """
    with error_context("fetch_prices", symbol=symbol, start=start, end=end):
        fetch_start = start
        if last_date is not None:
            refetch_start = last_date - timedelta(days=settings.YF_REFETCH_DAYS)
            if refetch_start > fetch_start:
                fetch_start = refetch_start

        # yfinanceのend引数は排他的なので、1日加算して包含的にする
        safe_end = min(end, date.today())
        fetch_end = safe_end + timedelta(days=1)

        rate_limiter = get_rate_limiter(settings)
        backoff = get_backoff(settings)
        backoff.reset()  # Reset backoff for new request
        
        attempts = 0
        max_attempts = settings.FETCH_MAX_RETRIES

        while attempts <= max_attempts:
            try:
                # Acquire rate limit token (use sync version for sync function)
                rate_limiter.acquire_sync()
                
                with io.StringIO() as _out, io.StringIO() as _err, redirect_stdout(_out), redirect_stderr(_err):
                    df = yf.download(
                    symbol,
                    start=fetch_start,
                    end=fetch_end,
                    auto_adjust=True,
                    progress=False,
                    timeout=settings.FETCH_TIMEOUT_SECONDS,
                )
                
                # Clean and validate data
                cleaned_df = DataCleaner.clean_price_data(df)
                
                if cleaned_df is None:
                    # Try fallback method
                    cleaned_df = _fetch_with_fallback(symbol, fetch_start, fetch_end, settings)
                
                if cleaned_df is not None:
                    backoff.reset()  # Reset on success
                    return cleaned_df
                
                # Special handling for common indices that might be missing the caret
                if symbol in {"IRX", "FVX", "TNX", "TYX", "VIX", "GSPC", "DJI", "IXIC", "SOX", "RUT"} and not symbol.startswith("^"):
                    logger = logging.getLogger(__name__)
                    logger.info(f"Retrying {symbol} as ^{symbol}")
                    return fetch_prices(
                        f"^{symbol}", 
                        start, 
                        end, 
                        settings=settings, 
                        last_date=last_date
                    )

                # If fallback also failed (returned None or empty), we might want to retry or give up?
                # The original logic retried on exceptions, but if download returns empty DF, it might not raise exception.
                # If yf.download returns empty DF, it usually means no data.
                # We should probably return empty DF here if no exception raised.
                return pd.DataFrame()
                
            except (
                URLlibHTTPError,
                RequestsHTTPError,
                TimeoutError,
                requests.exceptions.Timeout,
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectTimeout,
            ) as exc:
                error_type = type(exc).__name__
                status = getattr(exc, "code", None) or getattr(
                    getattr(exc, "response", None), "status_code", None
                )
                
                # Record error metrics
                get_error_metrics().record_error(error_type, {
                    "symbol": symbol,
                    "status_code": status,
                    "attempt": attempts + 1
                })
                
                # Check if retryable
                retryable = (
                    isinstance(exc, (
                        TimeoutError,
                        requests.exceptions.Timeout,
                        requests.exceptions.ReadTimeout,
                        requests.exceptions.ConnectTimeout,
                    )) or status in {429, 502, 503, 504}
                )
                
                if retryable and attempts < max_attempts:
                    delay = backoff.get_delay()
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Retry {attempts + 1}/{max_attempts} for {symbol} after {delay:.1f}s: {error_type}")
                    time.sleep(delay)
                    attempts += 1
                    continue
                
                # Max retries exceeded or non-retryable error
                raise
        
        # Should not reach here, but just in case
        raise RuntimeError(f"Failed to fetch {symbol} after {max_attempts} attempts")


def _fetch_with_fallback(
    symbol: str, 
    start: date, 
    end: date, 
    settings: Settings
) -> Optional[pd.DataFrame]:
    """Fallback fetch method using Ticker.history."""
    try:
        tk = yf.Ticker(symbol)
        with io.StringIO() as _out, io.StringIO() as _err, redirect_stdout(_out), redirect_stderr(_err):
            df = tk.history(
                start=start,
                end=end,
                auto_adjust=True,
                timeout=settings.FETCH_TIMEOUT_SECONDS,
            )
        
        return DataCleaner.clean_price_data(df)
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Fallback fetch failed for {symbol}: {e}")
    
    return None


async def fetch_prices_batch(
    symbols: List[str],
    start: date,
    end: date,
    settings: Settings,
    use_streaming: bool = True  # メモリ効率のためにストリーミングをデフォルトに
) -> Dict[str, pd.DataFrame]:
    """
    複数銘柄を並行取得する新規関数
    
    Parameters:
    -----------
    symbols: 銘柄リスト（例: ["AAPL", "MSFT", "^VIX"]）
    start: 開始日
    end: 終了日
    settings: アプリケーション設定（YF_REQ_CONCURRENCY等を含む）
    
    Returns:
    --------
    Dict[str, pd.DataFrame]: 銘柄名をキー、DataFrameを値とする辞書
    """
    with error_context("fetch_prices_batch", symbols=symbols, start=start, end=end):
        # メモリ効率のためにストリーミングを使用
        if use_streaming:
            successful_results = {}
            async for symbol, df in fetch_prices_streaming(symbols, start, end, settings):
                successful_results[symbol] = df
            return successful_results
        
        # 従来のメモリ集中型の実装（後方互換性のために残す）
        async def fetch_one(symbol: str) -> Tuple[str, Optional[pd.DataFrame]]:
            """単一銘柄を非同期で取得"""
            try:
                # レート制限を適用しながら取得
                rate_limiter = get_rate_limiter(settings)
                await rate_limiter.acquire()
                
                # 既存のfetch_prices関数を別スレッドで実行
                df = await run_in_threadpool(
                    fetch_prices, 
                    symbol, 
                    start, 
                    end, 
                    settings=settings
                )
                return symbol, df
            except Exception as e:
                # Record error but don't fail the whole batch
                get_error_metrics().record_error(type(e).__name__, {
                    "symbol": symbol,
                    "operation": "batch_fetch"
                })
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to fetch {symbol}: {e}")
                return symbol, None
        
        # セマフォで同時接続数を制御（YF_REQ_CONCURRENCYの値を使用）
        semaphore = asyncio.Semaphore(settings.YF_REQ_CONCURRENCY)
        
        async def fetch_with_semaphore(symbol: str):
            """セマフォで並行数を制限しながら取得"""
            async with semaphore:
                return await fetch_one(symbol)
        
        # 全銘柄を並行処理
        tasks = [fetch_with_semaphore(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 成功したものだけ辞書に格納
        successful_results = {}
        for result in results:
            if isinstance(result, Exception):
                # Record batch-level errors
                get_error_metrics().record_error(type(result).__name__, {
                    "operation": "batch_gather"
                })
                logger = logging.getLogger(__name__)
                logger.error(f"Batch operation failed: {result}")
            elif result and result[1] is not None and not result[1].empty:
                successful_results[result[0]] = result[1]
        
        return successful_results


async def fetch_prices_streaming(
    symbols: List[str],
    start: date,
    end: date,
    settings: Settings,
    chunk_size: int = 10
) -> AsyncIterator[Tuple[str, pd.DataFrame]]:
    """
    メモリ効率の良いストリーミング取得関数
    
    Parameters:
    -----------
    symbols: 銘柄リスト
    start: 開始日
    end: 終了日
    settings: アプリケーション設定
    chunk_size: 1回のチャンクで処理する銘柄数
    
    Yields:
    -------
    Tuple[str, pd.DataFrame]: (symbol, dataframe) のタプル
    """
    
    with error_context("fetch_prices_streaming", symbols=symbols, start=start, end=end):
        rate_limiter = get_rate_limiter(settings)
        semaphore = asyncio.Semaphore(settings.YF_REQ_CONCURRENCY)
        
        async def fetch_one(symbol: str) -> Tuple[str, Optional[pd.DataFrame]]:
            """単一銘柄を非同期で取得"""
            async with semaphore:
                try:
                    await rate_limiter.acquire()
                    df = await run_in_threadpool(
                        fetch_prices, 
                        symbol, 
                        start, 
                        end, 
                        settings=settings
                    )
                    return symbol, df
                except Exception as e:
                    # Record error but continue with other symbols
                    get_error_metrics().record_error(type(e).__name__, {
                        "symbol": symbol,
                        "operation": "streaming_fetch"
                    })
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to fetch {symbol}: {e}")
                    return symbol, None
        
        # 銘柄をチャンクに分割して処理
        for i in range(0, len(symbols), chunk_size):
            chunk_symbols = symbols[i:i + chunk_size]
            
            # チャンク内の銘柄を並行処理
            tasks = [fetch_one(symbol) for symbol in chunk_symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 成功した結果のみをyield
            for result in results:
                if isinstance(result, Exception):
                    # Record chunk-level errors
                    get_error_metrics().record_error(type(result).__name__, {
                        "operation": "streaming_chunk"
                    })
                    logger = logging.getLogger(__name__)
                    logger.error(f"Streaming chunk failed: {result}")
                elif result and result[1] is not None and not result[1].empty:
                    yield result[0], result[1]
                    
            # メモリ解放のためのGCヒント
            del tasks, results


__all__ = ["fetch_prices", "fetch_prices_batch", "fetch_prices_streaming", "RateLimiter", "ExponentialBackoff", "_fetch_with_fallback"]
