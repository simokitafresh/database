import asyncio
import logging
import time
import math
from datetime import date, timedelta
from typing import Optional, Dict, List, Tuple, AsyncIterator
from urllib.error import HTTPError as URLlibHTTPError
from contextlib import redirect_stdout, redirect_stderr
import io

import pandas as pd
import requests
import yfinance as yf
from requests.exceptions import HTTPError as RequestsHTTPError
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.logging import error_context, get_error_metrics

# yfinance の冗長な失敗ログ（"1 Failed download: ... possibly delisted" 等）を抑制
logging.getLogger("yfinance").setLevel(logging.ERROR)


class RateLimiter:
    """Token bucket rate limiter for Yahoo Finance API requests."""
    
    def __init__(self, rate_per_second: float, burst_size: int):
        self.rate_per_second = rate_per_second
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Acquire a token from the bucket, waiting if necessary."""
        async with self._lock:
            now = time.time()
            # Add tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate_per_second)
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                return
            
            # Calculate wait time for next token
            wait_time = (1 - self.tokens) / self.rate_per_second
            await asyncio.sleep(wait_time)
            self.tokens = 0
            self.last_update = time.time()
    
    def acquire_sync(self) -> None:
        """Synchronous version of acquire for use in sync functions."""
        # Simple token bucket implementation for sync context
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate_per_second)
        self.last_update = now
        
        if self.tokens < 1:
            # Simple delay calculation
            wait_time = (1 - self.tokens) / self.rate_per_second
            time.sleep(min(wait_time, 1.0))  # Cap at 1 second to avoid long delays
            self.tokens = 0
            self.last_update = time.time()
        else:
            self.tokens -= 1


class ExponentialBackoff:
    """Exponential backoff with jitter for retry logic."""
    
    def __init__(self, base_delay: float, multiplier: float, max_delay: float):
        self.base_delay = base_delay
        self.multiplier = multiplier
        self.max_delay = max_delay
        self.attempt = 0
    
    def reset(self):
        """Reset the backoff counter."""
        self.attempt = 0
    
    def get_delay(self) -> float:
        """Get the next delay duration."""
        if self.attempt == 0:
            delay = 0
        else:
            delay = min(self.base_delay * (self.multiplier ** (self.attempt - 1)), self.max_delay)
        self.attempt += 1
        return delay


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None
_backoff: Optional[ExponentialBackoff] = None


def get_rate_limiter(settings: Settings) -> RateLimiter:
    """Get or create the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(
            rate_per_second=settings.YF_RATE_LIMIT_REQUESTS_PER_SECOND,
            burst_size=settings.YF_RATE_LIMIT_BURST_SIZE
        )
    return _rate_limiter


def get_backoff(settings: Settings) -> ExponentialBackoff:
    """Get or create the global backoff instance."""
    global _backoff
    if _backoff is None:
        _backoff = ExponentialBackoff(
            base_delay=settings.YF_RATE_LIMIT_BACKOFF_BASE_DELAY,
            multiplier=settings.YF_RATE_LIMIT_BACKOFF_MULTIPLIER,
            max_delay=settings.YF_RATE_LIMIT_MAX_BACKOFF_DELAY
        )
    return _backoff


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
                df = df.rename(
                    columns={
                        "Open": "open",
                        "High": "high",
                        "Low": "low",
                        "Close": "close",
                        "Adj Close": "adj_close",
                        "Volume": "volume",
                    }
                )
                if "adj_close" in df.columns:
                    df = df.drop(columns=["adj_close"])

                # Guard against empty frames or missing required columns
                required_columns = {"open", "high", "low", "close", "volume"}
                if df is None or df.empty or not required_columns.issubset(df.columns):
                    # Try fallback method
                    df = _fetch_with_fallback(symbol, fetch_start, fetch_end, settings)
                
                backoff.reset()  # Reset on success
                return df
                
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
) -> pd.DataFrame:
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
        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume",
            }
        )
        if "adj_close" in df.columns:
            df = df.drop(columns=["adj_close"])
        
        required_columns = {"open", "high", "low", "close", "volume"}
        if df is not None and not df.empty and required_columns.issubset(df.columns):
            return df
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Fallback fetch failed for {symbol}: {e}")
    
    return pd.DataFrame()


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
