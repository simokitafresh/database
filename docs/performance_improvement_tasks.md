# API高速化実装タスクリスト

## 概要
- **目標**: 10銘柄同時リクエストの応答速度を10-15秒から2-3秒に短縮
- **プリフェッチ対象**: TQQQ, TECL, GLD, XLU, ^VIX, QQQ, SPY, TMV, TMF, LQD
- **実装方針**: 並行処理、キャッシュ、プリフェッチの3段階実装

## 現在のコードベース構造
- **FastAPI アプリ**: `app/main.py` (lifespan管理あり)
- **設定管理**: `app/core/config.py` (Settings クラスで環境変数管理)
- **価格取得API**: `app/api/v1/prices.py` (get_prices エンドポイント)
- **データ取得**: `app/services/fetcher.py` (fetch_prices 関数 - yfinance利用)
- **DB処理**: `app/db/queries.py` (ensure_coverage, get_prices_resolved)
- **正規化**: `app/services/normalize.py` (normalize_symbol 関数)
- **セッション管理**: `app/api/deps.py` (get_session, get_db)
- **DBエンジン**: `app/db/engine.py` (create_engine_and_sessionmaker)

## タスク一覧

### Phase 1: 環境変数と設定の更新（依存なし）

#### TASK-001: 環境変数の更新 ⬜
**責任**: 接続プールとAPI制限の拡張
**対象ファイル**: `app/core/config.py`
**現在の値**: 
- DB_POOL_SIZE = 2
- DB_MAX_OVERFLOW = 3  
- YF_REQ_CONCURRENCY = 2
- API_MAX_SYMBOLS = 5

**実装内容**:
```python
# app/core/config.py のSettingsクラスに以下を追加/更新
class Settings(BaseSettings):
    # 既存の設定（値を更新）
    DB_POOL_SIZE: int = 10  # 2から変更
    DB_MAX_OVERFLOW: int = 10  # 3から変更
    YF_REQ_CONCURRENCY: int = 8  # 2から変更
    API_MAX_SYMBOLS: int = 10  # 5から変更
    
    # 新規追加の設定
    CACHE_TTL_SECONDS: int = 60
    ENABLE_CACHE: bool = True
    PREFETCH_SYMBOLS: str = "TQQQ,TECL,GLD,XLU,^VIX,QQQ,SPY,TMV,TMF,LQD"
    PREFETCH_INTERVAL_MINUTES: int = 5
    
    # 既存のmodel_configはそのまま維持
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
```

**テスト方法**:
```python
from app.core.config import settings
assert settings.DB_POOL_SIZE == 10
assert settings.ENABLE_CACHE == True
assert "TQQQ" in settings.PREFETCH_SYMBOLS
```

**完了条件**: 
- アプリ起動時にエラーなし
- `settings.PREFETCH_SYMBOLS`から銘柄リストが取得可能

#### TASK-002: render.yaml の更新 ⬜
**責任**: 本番環境変数の設定
**対象ファイル**: `render.yaml`（プロジェクトルート）
**現在の設定**: DB_POOL_SIZE=2, YF_REQ_CONCURRENCY=2 など

**実装内容**:
```yaml
# render.yaml のenvVarsセクションに以下を追加/更新
services:
  - type: web
    name: stockdata-api
    envVars:
      # 既存の設定を更新
      - key: DB_POOL_SIZE
        value: "10"  # 2から変更
      - key: DB_MAX_OVERFLOW
        value: "10"  # 3から変更
      - key: YF_REQ_CONCURRENCY
        value: "8"   # 2から変更
      - key: API_MAX_SYMBOLS
        value: "10"  # 現在の値を確認して更新
      
      # 新規追加
      - key: CACHE_TTL_SECONDS
        value: "60"
      - key: ENABLE_CACHE
        value: "true"
      - key: PREFETCH_SYMBOLS
        value: "TQQQ,TECL,GLD,XLU,^VIX,QQQ,SPY,TMV,TMF,LQD"
      - key: PREFETCH_INTERVAL_MINUTES
        value: "5"
```

**テスト方法**: 
```bash
# YAMLの構文チェック
python -c "import yaml; yaml.safe_load(open('render.yaml'))"
```

**完了条件**: YAMLファイルが有効でRenderにデプロイ可能

### Phase 2: キャッシュ基盤実装（依存: Phase 1）

#### TASK-003: インメモリキャッシュクラスの実装 ⬜
**責任**: TTL付きインメモリキャッシュ
**入力**: なし
**出力**: app/services/cache.py
**実装**:
```python
# app/services/cache.py
from typing import Any, Optional, Dict, Tuple
from datetime import datetime, timedelta
import asyncio
from threading import RLock

class InMemoryCache:
    def __init__(self, ttl_seconds: int = 60, max_size: int = 1000):
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._lock = RLock()
    
    async def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if datetime.utcnow() - timestamp < timedelta(seconds=self._ttl):
                    return value
                else:
                    del self._cache[key]
        return None
    
    async def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache.keys(), 
                               key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            self._cache[key] = (value, datetime.utcnow())
    
    async def clear(self) -> None:
        with self._lock:
            self._cache.clear()
    
    def get_sync(self, key: str) -> Optional[Any]:
        """同期版（デバッグ用）"""
        return asyncio.run(self.get(key))
```
**テスト**: set/get/TTL期限切れのユニットテスト
**完了条件**: キャッシュの基本操作が動作

#### TASK-004: キャッシュのシングルトンインスタンス作成 ⬜
**責任**: アプリ全体で共有されるキャッシュインスタンス
**入力**: TASK-003
**出力**: app/services/cache.py の更新
**実装**:
```python
# app/services/cache.py に追加
_cache_instance: Optional[InMemoryCache] = None

def get_cache() -> InMemoryCache:
    global _cache_instance
    if _cache_instance is None:
        from app.core.config import settings
        _cache_instance = InMemoryCache(
            ttl_seconds=settings.CACHE_TTL_SECONDS,
            max_size=1000
        )
    return _cache_instance
```
**テスト**: get_cache() が同一インスタンスを返すことを確認
**完了条件**: シングルトンパターンが機能

### Phase 3: 正規化処理の強化（依存: なし）

#### TASK-005: 特殊シンボル（^VIX）対応 ⬜
**責任**: ^で始まる指数シンボルの正規化対応
**対象ファイル**: `app/services/normalize.py`
**現在の実装**: BRK.B→BRK-B等の変換、取引所サフィックス対応

**実装内容**:
```python
# app/services/normalize.py の normalize_symbol関数を更新
def normalize_symbol(symbol: Optional[str]) -> str:
    """Normalize ticker symbols to Yahoo Finance style.
    
    現在の仕様:
    - BRK.B → BRK-B (クラス株変換)
    - 取引所サフィックス (.TO等) は維持
    
    追加仕様:
    - ^VIX等の指数シンボルはそのまま維持
    """
    if not symbol:
        return ""
    
    s = symbol.strip().upper()
    if not s:
        return ""
    
    # 新規追加: 特殊シンボル（^で始まる指数）はそのまま維持
    if s.startswith("^"):
        return s
    
    # 既存のロジック（ドット処理）
    if "." in s:
        head, tail = s.rsplit(".", 1)
        if tail in _KNOWN_EXCHANGE_SUFFIXES:
            return f"{head}.{tail}"
        if len(tail) == 1 and tail.isalpha():
            return f"{head}-{tail}"
        return s
    
    return s
```

**テスト方法**:
```python
from app.services.normalize import normalize_symbol

# 新規テストケース
assert normalize_symbol("^vix") == "^VIX"
assert normalize_symbol("^GSPC") == "^GSPC"
assert normalize_symbol("^DJI") == "^DJI"

# 既存機能が壊れていないことを確認
assert normalize_symbol("BRK.B") == "BRK-B"
assert normalize_symbol("TSM.TW") == "TSM.TW"
```

**完了条件**: ^VIXを含む10銘柄が正しく正規化される

### Phase 4: 並行取得の実装（依存: Phase 1）

#### TASK-006: バッチ取得関数の実装 ⬜
**責任**: 複数銘柄の並行取得
**対象ファイル**: `app/services/fetcher.py`
**現在の実装**: fetch_prices関数（同期的にyfinanceを呼び出し）
**必要なインポート**: `from starlette.concurrency import run_in_threadpool`

**実装内容**:
```python
# app/services/fetcher.py に以下の関数を追加
import asyncio
from typing import Dict, List, Tuple, Optional
from starlette.concurrency import run_in_threadpool

async def fetch_prices_batch(
    symbols: List[str],
    start: date,
    end: date,
    settings: Settings
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
    
    async def fetch_one(symbol: str) -> Tuple[str, Optional[pd.DataFrame]]:
        """単一銘柄を非同期で取得"""
        try:
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
    results = await asyncio.gather(*tasks)
    
    # 成功したものだけ辞書に格納
    return {symbol: df for symbol, df in results if df is not None and not df.empty}
```

**テスト方法**:
```python
# tests/test_batch_fetch.py
import asyncio
from datetime import date, timedelta
from app.services.fetcher import fetch_prices_batch
from app.core.config import settings

async def test_batch():
    symbols = ["AAPL", "MSFT", "GOOGL"]
    end = date.today()
    start = end - timedelta(days=7)
    
    results = await fetch_prices_batch(symbols, start, end, settings)
    assert len(results) > 0
    assert "AAPL" in results
    
# 実行
asyncio.run(test_batch())
```

**完了条件**: 3銘柄を並行取得し、逐次より高速

#### TASK-007: ensure_coverage の並行化 ⬜
**責任**: カバレッジ確認と取得の並行処理
**対象ファイル**: `app/db/queries.py`
**現在の実装**: ensure_coverage関数（forループで逐次処理）
**注意点**: 既存のwith_symbol_lock, _ensure_full_history_once, _get_coverage等を利用

**実装内容**:
```python
# app/db/queries.py に以下の関数を追加
import asyncio
from typing import Sequence
from datetime import date

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
    logger = logging.getLogger(__name__)
    
    async def process_single_symbol(symbol: str):
        """単一銘柄の処理（既存のensure_coverageのロジックを利用）"""
        try:
            # アドバイザリロック取得
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
```

**既存関数との関係**:
- `ensure_coverage`: そのまま残す（後方互換性）
- `ensure_coverage_parallel`: 新規追加（並行版）
- 内部で使用: `with_symbol_lock`, `_ensure_full_history_once`, `_get_coverage`, `fetch_prices_df`, `df_to_rows`, `upsert_prices_sql`

**テスト方法**:
```python
# 5銘柄でのテスト
symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"]
await ensure_coverage_parallel(session, symbols, date_from, date_to, 30)
```

**完了条件**: 5銘柄を並行処理してエラーなし

### Phase 5: プリフェッチサービスの実装（依存: Phase 2, 3, 4）

#### TASK-008: プリフェッチサービスクラス実装 ⬜
**責任**: 指定銘柄の事前取得とキャッシュ管理
**入力**: TASK-003, TASK-004, TASK-006
**出力**: app/services/prefetch_service.py
**実装**:
```python
# app/services/prefetch_service.py
import asyncio
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
import logging

from app.core.config import settings
from app.services.cache import get_cache
from app.services.fetcher import fetch_prices_batch
from app.db.engine import create_engine_and_sessionmaker
from app.db.queries import ensure_coverage_parallel

logger = logging.getLogger(__name__)

class PrefetchService:
    def __init__(self):
        self.symbols = self._parse_symbols()
        self.cache = get_cache()
        self.running = False
        self._task: Optional[asyncio.Task] = None
    
    def _parse_symbols(self) -> List[str]:
        """環境変数から銘柄リストを取得"""
        symbols_str = settings.PREFETCH_SYMBOLS
        if not symbols_str:
            return []
        return [s.strip() for s in symbols_str.split(",") if s.strip()]
    
    async def start(self):
        """プリフェッチサービス開始"""
        if self.running:
            return
        
        self.running = True
        logger.info(f"Starting prefetch for {len(self.symbols)} symbols")
        
        # 初回取得
        await self._prefetch_all()
        
        # 定期更新タスク開始
        self._task = asyncio.create_task(self._periodic_update())
    
    async def stop(self):
        """プリフェッチサービス停止"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _prefetch_all(self):
        """全銘柄をプリフェッチ"""
        if not self.symbols:
            return
        
        try:
            # 独立したDBセッションを作成
            _, SessionLocal = create_engine_and_sessionmaker(
                database_url=settings.DATABASE_URL,
                pool_size=2
            )
            
            async with SessionLocal() as session:
                # 最新30日分のデータを確保
                today = date.today()
                from_date = today - timedelta(days=30)
                
                # 並行取得
                await ensure_coverage_parallel(
                    session, self.symbols, from_date, today,
                    settings.YF_REFETCH_DAYS
                )
                
                # キャッシュに保存
                for symbol in self.symbols:
                    cache_key = f"prefetch:{symbol}:{from_date}:{today}"
                    await self.cache.set(cache_key, True)
                
            logger.info(f"Prefetched {len(self.symbols)} symbols")
            
        except Exception as e:
            logger.error(f"Prefetch failed: {e}")
    
    async def _periodic_update(self):
        """定期的な更新"""
        interval = settings.PREFETCH_INTERVAL_MINUTES * 60
        
        while self.running:
            try:
                await asyncio.sleep(interval)
                await self._prefetch_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic update failed: {e}")

# シングルトンインスタンス
_prefetch_service: Optional[PrefetchService] = None

def get_prefetch_service() -> PrefetchService:
    global _prefetch_service
    if _prefetch_service is None:
        _prefetch_service = PrefetchService()
    return _prefetch_service
```
**テスト**: start/stop/プリフェッチ実行の確認
**完了条件**: 指定銘柄がプリフェッチされる

#### TASK-009: アプリ起動時のプリフェッチ開始 ⬜
**責任**: FastAPI起動時にプリフェッチを自動開始
**対象ファイル**: `app/main.py`
**現在の実装**: lifespanコンテキストマネージャーあり（空実装）
**注意点**: 既存のimport文とlifespanの構造を維持

**実装内容**:
```python
# app/main.py のlifespanを更新
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    """アプリケーションライフサイクル管理"""
    prefetch_service = None
    try:
        # 起動時の処理
        logger.info("Starting application...")
        
        # プリフェッチサービス開始（ENABLE_CACHEがTrueの場合のみ）
        if settings.ENABLE_CACHE:
            try:
                from app.services.prefetch_service import get_prefetch_service
                prefetch_service = get_prefetch_service()
                await prefetch_service.start()
                logger.info(f"Prefetch service started for {len(prefetch_service.symbols)} symbols")
            except ImportError:
                logger.warning("Prefetch service not found, skipping...")
            except Exception as e:
                logger.error(f"Failed to start prefetch service: {e}")
                # エラーが起きてもアプリは起動させる
        
        yield
        
    finally:
        # シャットダウン時の処理
        logger.info("Shutting down application...")
        
        # プリフェッチサービス停止
        if prefetch_service and settings.ENABLE_CACHE:
            try:
                await prefetch_service.stop()
                logger.info("Prefetch service stopped")
            except Exception as e:
                logger.error(f"Error stopping prefetch service: {e}")

# 既存のFastAPIアプリ作成（lifespanを指定）
app = FastAPI(lifespan=lifespan)

# 以降の既存コード（init_error_handlers, configure_logging等）はそのまま
```

**確認事項**:
- settings.ENABLE_CACHEがFalseの場合はプリフェッチをスキップ
- ImportErrorをキャッチして、プリフェッチサービスがなくても起動可能
- エラーが発生してもアプリケーション全体は起動する

**テスト方法**:
```bash
# ENABLE_CACHE=true で起動
ENABLE_CACHE=true uvicorn app.main:app --reload

# ログで確認
# "Prefetch service started for 10 symbols" が表示されること

# ENABLE_CACHE=false で起動してもエラーなし
ENABLE_CACHE=false uvicorn app.main:app --reload
```

**完了条件**: 
- アプリ起動時に"Prefetch service started"ログが出力
- ENABLE_CACHE=falseでも正常起動

### Phase 6: APIエンドポイントの最適化（依存: Phase 4, 5）

#### TASK-010: キャッシュチェック付き価格取得 ⬜
**責任**: キャッシュを確認してから取得する高速化
**対象ファイル**: `app/api/v1/prices.py`
**現在の実装**: get_prices関数（ensure_coverage → get_prices_resolved）
**依存**: TASK-003（キャッシュ）, TASK-007（並行化）

**実装内容**:
```python
# app/api/v1/prices.py のget_prices関数を更新
import time
from typing import List
from datetime import date
from fastapi import Query, Depends, HTTPException
from app.api.deps import get_session
from app.core.config import settings
from app.schemas.prices import PriceRowOut

@router.get("/prices", response_model=List[PriceRowOut])
async def get_prices(
    symbols: str = Query(..., description="Comma-separated symbols"),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    auto_fetch: bool = Query(True, description="Auto-fetch all available data if missing"),
    session=Depends(get_session),
):
    # 既存のバリデーション
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="invalid date range")
    
    symbols_list = _parse_and_validate_symbols(symbols)
    if not symbols_list:
        return []
    
    # 自動登録（既存のコード）
    if settings.ENABLE_AUTO_REGISTRATION:
        logger.info(f"Checking auto-registration for symbols: {symbols_list}")
        await ensure_symbols_registered(session, symbols_list)
    
    t0 = time.perf_counter()
    effective_to = min(date_to, date.today())
    
    # === ここから新規追加 ===
    cached_results = []
    uncached_symbols = []
    
    # キャッシュチェック（ENABLE_CACHEがTrueの場合のみ）
    if settings.ENABLE_CACHE:
        try:
            from app.services.cache import get_cache
            cache = get_cache()
            
            for symbol in symbols_list:
                # キャッシュキーの生成（シンボル、期間で一意）
                cache_key = f"prices:{symbol}:{date_from}:{effective_to}"
                cached_data = await cache.get(cache_key)
                
                if cached_data:
                    # キャッシュヒット
                    cached_results.extend(cached_data)
                    logger.debug(f"Cache hit for {symbol}")
                else:
                    # キャッシュミス
                    uncached_symbols.append(symbol)
                    logger.debug(f"Cache miss for {symbol}")
            
            # 全てキャッシュにあれば即座に返却
            if not uncached_symbols:
                logger.info(f"All {len(symbols_list)} symbols from cache")
                return cached_results
                
        except ImportError:
            # キャッシュモジュールがない場合は全て取得
            uncached_symbols = symbols_list
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
            uncached_symbols = symbols_list
    else:
        uncached_symbols = symbols_list
    
    # === 並行処理版の使用（TASK-007の成果を利用） ===
    if auto_fetch and uncached_symbols:
        # ensure_coverage_parallelが存在すれば使用、なければ通常版
        try:
            from app.db.queries import ensure_coverage_parallel
            await ensure_coverage_parallel(
                session=session,
                symbols=uncached_symbols,
                date_from=date_from,
                date_to=effective_to,
                refetch_days=settings.YF_REFETCH_DAYS,
            )
            logger.info(f"Used parallel coverage for {len(uncached_symbols)} symbols")
        except ImportError:
            # 並行版がなければ既存の逐次版を使用
            await queries.ensure_coverage(
                session=session,
                symbols=uncached_symbols,
                date_from=date_from,
                date_to=effective_to,
                refetch_days=settings.YF_REFETCH_DAYS,
            )
    
    # データベースから取得
    rows = []
    for symbol in uncached_symbols:
        symbol_rows = await queries.get_prices_resolved(
            session=session,
            symbols=[symbol],
            date_from=date_from,
            date_to=effective_to,
        )
        rows.extend(symbol_rows)
        
        # キャッシュに保存（ENABLE_CACHEがTrueの場合）
        if settings.ENABLE_CACHE and symbol_rows:
            try:
                cache_key = f"prices:{symbol}:{date_from}:{effective_to}"
                await cache.set(cache_key, symbol_rows)
                logger.debug(f"Cached {len(symbol_rows)} rows for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to cache {symbol}: {e}")
    
    # キャッシュ済みと新規取得を結合
    if cached_results:
        rows.extend(cached_results)
    
    # ソート（日付、シンボル順）
    rows.sort(key=lambda r: (r["date"], r["symbol"]))
    
    # 行数制限チェック
    if len(rows) > settings.API_MAX_ROWS:
        raise HTTPException(status_code=413, detail="response too large")
    
    # パフォーマンスログ
    dt_ms = int((time.perf_counter() - t0) * 1000)
    cache_hit_count = len(cached_results) if settings.ENABLE_CACHE else 0
    
    logger.info(
        "prices served",
        extra=dict(
            symbols=symbols_list,
            date_from=str(date_from),
            date_to=str(effective_to),
            rows=len(rows),
            duration_ms=dt_ms,
            cache_hits=cache_hit_count,
            cache_hit_ratio=cache_hit_count/len(symbols_list) if symbols_list else 0,
        ),
    )
    
    return rows
```

**重要なポイント**:
1. ENABLE_CACHE=falseでも動作（既存の処理にフォールバック）
2. ImportErrorをキャッチ（キャッシュモジュールがなくても動作）
3. 並行版ensure_coverage_parallelを優先使用
4. キャッシュヒット率をログに記録

**テスト方法**:
```bash
# 初回リクエスト（キャッシュミス）
curl "http://localhost:8000/v1/prices?symbols=AAPL,MSFT&from=2024-01-01&to=2024-01-31"

# 2回目（キャッシュヒット、高速）
curl "http://localhost:8000/v1/prices?symbols=AAPL,MSFT&from=2024-01-01&to=2024-01-31"
```

**完了条件**: 2回目のリクエストが初回より大幅に高速

### Phase 7: テストの実装（依存: Phase 1-6）

#### TASK-011: キャッシュのユニットテスト ⬜
**責任**: InMemoryCacheクラスのテスト
**入力**: TASK-003
**出力**: tests/unit/test_cache.py
**実装**:
```python
# tests/unit/test_cache.py
import pytest
import asyncio
from datetime import datetime, timedelta
from app.services.cache import InMemoryCache

@pytest.mark.asyncio
async def test_cache_basic():
    cache = InMemoryCache(ttl_seconds=1)
    
    # Set and get
    await cache.set("key1", "value1")
    assert await cache.get("key1") == "value1"
    
    # TTL expiration
    await asyncio.sleep(1.1)
    assert await cache.get("key1") is None

@pytest.mark.asyncio
async def test_cache_max_size():
    cache = InMemoryCache(ttl_seconds=60, max_size=2)
    
    await cache.set("key1", "value1")
    await cache.set("key2", "value2")
    await cache.set("key3", "value3")  # key1 should be evicted
    
    assert await cache.get("key1") is None
    assert await cache.get("key2") == "value2"
    assert await cache.get("key3") == "value3"
```
**テスト**: pytest tests/unit/test_cache.py
**完了条件**: 全テスト合格

#### TASK-012: 並行取得のパフォーマンステスト ⬜
**責任**: 並行取得の速度測定
**入力**: TASK-006
**出力**: tests/performance/test_parallel_fetch.py
**実装**:
```python
# tests/performance/test_parallel_fetch.py
import pytest
import asyncio
import time
from app.services.fetcher import fetch_prices_batch, fetch_prices
from app.core.config import settings
from datetime import date, timedelta

@pytest.mark.asyncio
async def test_parallel_vs_sequential():
    symbols = ["AAPL", "MSFT", "GOOGL"]
    end = date.today()
    start = end - timedelta(days=30)
    
    # Sequential
    t0 = time.time()
    for symbol in symbols:
        await asyncio.to_thread(fetch_prices, symbol, start, end, settings=settings)
    seq_time = time.time() - t0
    
    # Parallel
    t0 = time.time()
    await fetch_prices_batch(symbols, start, end, settings)
    par_time = time.time() - t0
    
    print(f"Sequential: {seq_time:.2f}s, Parallel: {par_time:.2f}s")
    assert par_time < seq_time * 0.7  # 並行が30%以上高速
```
**テスト**: pytest tests/performance/test_parallel_fetch.py -s
**完了条件**: 並行処理が高速

#### TASK-013: プリフェッチサービスの統合テスト ⬜
**責任**: プリフェッチ機能の動作確認
**入力**: TASK-008
**出力**: tests/integration/test_prefetch.py
**実装**:
```python
# tests/integration/test_prefetch.py
import pytest
import asyncio
from app.services.prefetch_service import PrefetchService
from app.services.cache import InMemoryCache

@pytest.mark.asyncio
async def test_prefetch_service():
    # テスト用設定
    service = PrefetchService()
    service.symbols = ["AAPL", "MSFT"]  # テスト用に2銘柄のみ
    
    # プリフェッチ実行
    await service._prefetch_all()
    
    # キャッシュ確認
    cache = service.cache
    from datetime import date, timedelta
    today = date.today()
    from_date = today - timedelta(days=30)
    
    for symbol in service.symbols:
        cache_key = f"prefetch:{symbol}:{from_date}:{today}"
        assert await cache.get(cache_key) is not None
```
**テスト**: pytest tests/integration/test_prefetch.py
**完了条件**: プリフェッチ動作確認

### Phase 8: モニタリングとデバッグ（依存: Phase 1-7）

#### TASK-014: キャッシュ統計エンドポイント ⬜
**責任**: キャッシュ利用状況の可視化
**入力**: TASK-003
**出力**: app/api/v1/debug.py
**実装**:
```python
# app/api/v1/debug.py
from fastapi import APIRouter, Depends, HTTPException
from app.core.config import settings
from app.api.deps import get_settings

router = APIRouter()

@router.get("/debug/cache-stats")
async def get_cache_stats(settings=Depends(get_settings)):
    """キャッシュ統計情報（開発環境のみ）"""
    if settings.APP_ENV not in ["development", "staging"]:
        raise HTTPException(status_code=404)
    
    from app.services.cache import get_cache
    cache = get_cache()
    
    with cache._lock:
        total_items = len(cache._cache)
        items_info = []
        for key, (value, timestamp) in list(cache._cache.items())[:10]:
            items_info.append({
                "key": key,
                "age_seconds": (datetime.utcnow() - timestamp).total_seconds(),
                "size_bytes": len(str(value))
            })
    
    return {
        "total_items": total_items,
        "max_size": cache._max_size,
        "ttl_seconds": cache._ttl,
        "sample_items": items_info
    }
```
**テスト**: エンドポイント呼び出し
**完了条件**: 統計情報が取得可能

#### TASK-015: パフォーマンスログの追加 ⬜
**責任**: 高速化効果の測定
**入力**: TASK-010
**出力**: app/api/v1/prices.py の更新
**実装**: ログに cache_hits, parallel_fetch_time 等を追加
**テスト**: ログ出力確認
**完了条件**: パフォーマンス指標がログに記録

## 実装順序と優先度

### 🚀 即座に効果が出るタスク（設定変更のみ）
1. **TASK-001**: 環境変数の更新（5分）
2. **TASK-002**: render.yamlの更新（5分）

### 🎯 最大効果が期待できるタスク（並行処理）
3. **TASK-006**: バッチ取得関数（30分）
4. **TASK-007**: ensure_coverageの並行化（45分）

### 📦 基盤実装（キャッシュとプリフェッチ）
5. **TASK-003**: インメモリキャッシュ（30分）
6. **TASK-004**: キャッシュシングルトン（10分）
7. **TASK-005**: 正規化の強化（15分）
8. **TASK-008**: プリフェッチサービス（45分）
9. **TASK-009**: 起動時プリフェッチ（20分）

### 🔧 APIとテスト
10. **TASK-010**: API最適化（30分）
11. **TASK-011〜015**: テストとモニタリング（各15-20分）

## 成功指標と測定方法

### パフォーマンス目標
- [ ] **10銘柄同時リクエスト**: 10-15秒 → 2-3秒以内
- [ ] **プリフェッチ10銘柄**: 0.1秒以内（キャッシュから即座に返却）
- [ ] **キャッシュヒット率**: 60%以上（ログで確認）

### 測定方法
```bash
# パフォーマンス測定スクリプト
time curl "http://localhost:8000/v1/prices?symbols=TQQQ,TECL,GLD,XLU,^VIX,QQQ,SPY,TMV,TMF,LQD&from=2024-01-01&to=2024-01-31"

# ログでキャッシュヒット率を確認
tail -f logs/app.log | grep "cache_hit_ratio"
```

### システム制約
- [ ] **メモリ使用量**: 500MB以内
- [ ] **エラー率**: 1%未満
- [ ] **後方互換性**: 既存APIの動作を変更しない

## 実装上の重要な注意事項

### 1. エラーハンドリング
- **ImportError**: モジュールがなくても既存処理にフォールバック
- **キャッシュエラー**: キャッシュ失敗してもデータ取得は継続
- **並行処理エラー**: 個別銘柄のエラーが全体を止めない

### 2. 設定による制御
```python
# ENABLE_CACHE=false で従来動作
if settings.ENABLE_CACHE:
    # 新機能を使用
else:
    # 既存の処理を使用
```

### 3. データベーストランザクション
- 並行処理時は各銘柄で独立したトランザクション
- アドバイザリロックは維持（with_symbol_lock）

### 4. ログ出力
```python
logger.info("Performance metrics", extra={
    "duration_ms": dt_ms,
    "cache_hits": cache_hit_count,
    "parallel_fetch": True
})
```

### 5. テスト実行
```bash
# 単体テスト
pytest tests/unit/test_cache.py -v

# パフォーマンステスト
pytest tests/performance/test_parallel_fetch.py -s

# 統合テスト
pytest tests/integration/test_prefetch.py -v
```

## 実装チェックリスト

### Phase 1: 基本設定（10分）
- [ ] TASK-001: config.py更新
- [ ] TASK-002: render.yaml更新
- [ ] デプロイ環境で動作確認

### Phase 2: 並行処理（1.5時間）
- [ ] TASK-006: fetch_prices_batch実装
- [ ] TASK-007: ensure_coverage_parallel実装  
- [ ] パフォーマンス測定

### Phase 3: キャッシュ（1時間）
- [ ] TASK-003: InMemoryCache実装
- [ ] TASK-004: get_cache実装
- [ ] TASK-005: 正規化更新

### Phase 4: プリフェッチ（1時間）
- [ ] TASK-008: PrefetchService実装
- [ ] TASK-009: lifespan更新

### Phase 5: 統合（30分）
- [ ] TASK-010: get_prices最適化
- [ ] 全体動作確認

### Phase 6: 品質保証（1時間）
- [ ] TASK-011〜013: テスト作成
- [ ] TASK-014〜015: モニタリング

## トラブルシューティング

### Q: ImportError: No module named 'app.services.cache'
A: TASK-003が未実装。ENABLE_CACHE=falseで一時的に回避可能

### Q: 並行処理でデッドロック
A: chunk_sizeを小さくする（10→5）

### Q: キャッシュメモリ不足
A: InMemoryCacheのmax_sizeを調整（1000→500）

### Q: ^VIXが取得できない
A: TASK-005の正規化更新が必要

## 最終確認事項

1. **既存機能への影響なし**: 従来のAPIが正常動作
2. **段階的移行可能**: ENABLE_CACHEで切り替え
3. **エラー時の安全性**: 新機能エラーでも基本機能は動作
4. **パフォーマンス向上**: 目標値を達成
5. **運用性**: ログとモニタリングが充実
