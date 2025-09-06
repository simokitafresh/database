# 株価データ管理基盤 - エンジニアリングタスクリスト

## 📅 作成日: 2025年9月6日
## 🎯 目的: クリティカルエラー修正と自動データ取得機能実装
## 📦 リポジトリ: https://github.com/simokitafresh/database
## 🌐 本番環境: https://stockdata-api-6xok.onrender.com

---

## タスク進捗管理

| タスクID | カテゴリ | ステータス | 完了日時 |
|----------|----------|------------|----------|
| DEL-001 | 削除 | [ ] 未着手 | - |
| DEL-002 | 削除 | [ ] 未着手 | - |
| DEL-003 | 削除 | [ ] 未着手 | - |
| DEL-004 | 削除 | [ ] 未着手 | - |
| ENG-001 | 修正 | [ ] 未着手 | - |
| ENG-002 | 修正 | [ ] 未着手 | - |
| QRY-001 | 新機能 | [ ] 未着手 | - |
| QRY-002 | 新機能 | [ ] 未着手 | - |
| QRY-003 | 新機能 | [ ] 未着手 | - |
| QRY-004 | 新機能 | [ ] 未着手 | - |
| API-001 | 修正 | [ ] 未着手 | - |
| API-002 | 修正 | [ ] 未着手 | - |
| CFG-001 | 設定 | [ ] 未着手 | - |
| CFG-002 | 設定 | [ ] 未着手 | - |
| ENT-001 | 修正 | [ ] 未着手 | - |
| ENT-002 | 修正 | [ ] 未着手 | - |
| RND-001 | 設定 | [ ] 未着手 | - |
| RND-002 | 設定 | [ ] 未着手 | - |
| TST-001 | テスト | [ ] 未着手 | - |
| TST-002 | テスト | [ ] 未着手 | - |
| TST-003 | テスト | [ ] 未着手 | - |

---

## 削除タスク

### DEL-001: queries_new.pyファイル削除
**開始条件**: リポジトリのクローン完了
**作業内容**:
```bash
rm app/db/queries_new.py
```
**完了条件**: ファイルが存在しないこと
**検証コマンド**: `test ! -f app/db/queries_new.py && echo "OK"`

### DEL-002: queries_optimized.pyファイル削除
**開始条件**: リポジトリのクローン完了
**作業内容**:
```bash
rm app/db/queries_optimized.py
```
**完了条件**: ファイルが存在しないこと
**検証コマンド**: `test ! -f app/db/queries_optimized.py && echo "OK"`

### DEL-003: monitoringディレクトリ削除
**開始条件**: リポジトリのクローン完了
**作業内容**:
```bash
rm -rf app/monitoring/
```
**完了条件**: ディレクトリが存在しないこと
**検証コマンド**: `test ! -d app/monitoring && echo "OK"`

### DEL-004: profilingディレクトリ削除
**開始条件**: リポジトリのクローン完了
**作業内容**:
```bash
rm -rf app/profiling/
```
**完了条件**: ディレクトリが存在しないこと
**検証コマンド**: `test ! -d app/profiling && echo "OK"`

---

## app/db/engine.py修正タスク

### ENG-001: NullPool判定ロジック追加
**開始条件**: DEL-001完了
**対象ファイル**: `app/db/engine.py`
**修正場所**: `create_engine_and_sessionmaker`関数内、68行目付近
**作業内容**:
1. `if database_url.startswith("postgresql+asyncpg://"):`ブロック内に以下を追加:
```python
# 既存のconnect_args設定の後に追加
if "pooler.supabase.com" in database_url:
    poolclass = NullPool
    logger.info("Using NullPool for Supabase Pooler mode")
```
**完了条件**: pooler.supabase.comを含むURLでNullPoolが使用される
**検証コマンド**: `grep -n "poolclass = NullPool" app/db/engine.py`

### ENG-002: デフォルトプール設定値変更
**開始条件**: ENG-001完了
**対象ファイル**: `app/db/engine.py`
**修正場所**: 関数定義の引数デフォルト値（45-47行目）
**作業内容**:
```python
def create_engine_and_sessionmaker(
    database_url: str,
    pool_size: int = 2,  # 5から2に変更
    max_overflow: int = 3,  # 5から3に変更
    pool_pre_ping: bool = True,
    pool_recycle: int = 900,  # 1800から900に変更
    echo: bool = False
) -> Tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
```
**完了条件**: デフォルト値が変更されている
**検証コマンド**: `grep "pool_size: int = 2" app/db/engine.py`

---

## app/db/queries.py修正タスク

### QRY-001: find_earliest_available_date関数追加
**開始条件**: DEL-002完了
**対象ファイル**: `app/db/queries.py`
**修正場所**: ファイル末尾（ensure_coverage関数の後）
**作業内容**:
```python
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
```
**完了条件**: 関数が定義されている
**検証コマンド**: `grep -n "def find_earliest_available_date" app/db/queries.py`

### QRY-002: ensure_coverage_with_auto_fetch関数追加
**開始条件**: QRY-001完了
**対象ファイル**: `app/db/queries.py`
**修正場所**: find_earliest_available_date関数の後
**作業内容**:
```python
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
```
**完了条件**: 関数が定義されている
**検証コマンド**: `grep -n "def ensure_coverage_with_auto_fetch" app/db/queries.py`

### QRY-003: 必要なimport追加（Dict, Any）
**開始条件**: QRY-002完了
**対象ファイル**: `app/db/queries.py`
**修正場所**: ファイル先頭のimport部分（5行目付近）
**作業内容**:
```python
from typing import Any, List, Mapping, Optional, Sequence, cast, Dict
```
**完了条件**: Dict, Anyがimportされている
**検証コマンド**: `grep "from typing import" app/db/queries.py | grep Dict`

### QRY-004: __all__リストに関数追加
**開始条件**: QRY-003完了
**対象ファイル**: `app/db/queries.py`
**修正場所**: ファイル末尾の__all__定義（200行目付近）
**作業内容**:
```python
__all__ = [
    "ensure_coverage",
    "ensure_coverage_with_auto_fetch",  # 追加
    "find_earliest_available_date",  # 追加
    "get_prices_resolved",
    "list_symbols",
    "LIST_SYMBOLS_SQL",
]
```
**完了条件**: 新関数が__all__に含まれている
**検証コマンド**: `grep "ensure_coverage_with_auto_fetch" app/db/queries.py | grep __all__`

---

## app/api/v1/prices.py修正タスク

### API-001: auto_fetchパラメータ追加
**開始条件**: QRY-004完了
**対象ファイル**: `app/api/v1/prices.py`
**修正場所**: get_prices関数の引数定義（46-48行目）
**作業内容**:
```python
@router.get("/prices", response_model=List[PriceRowOut])
async def get_prices(
    symbols: str = Query(..., description="Comma-separated symbols"),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    auto_fetch: bool = Query(True, description="Auto-fetch all available data if missing"),  # 追加
    session=Depends(get_session),
):
```
**完了条件**: auto_fetchパラメータが追加されている
**検証コマンド**: `grep "auto_fetch: bool" app/api/v1/prices.py`

### API-002: auto_fetch条件分岐実装
**開始条件**: API-001完了
**対象ファイル**: `app/api/v1/prices.py`
**修正場所**: ensure_coverage呼び出し部分（69-75行目）
**作業内容**:
```python
        t0 = time.perf_counter()
        
        if auto_fetch:
            # 新機能：最古日から全データ自動取得
            fetch_meta = await queries.ensure_coverage_with_auto_fetch(
                session=session,
                symbols=symbols_list,
                date_from=date_from,
                date_to=date_to,
                refetch_days=settings.YF_REFETCH_DAYS,
            )
            
            if fetch_meta.get("adjustments"):
                logger.info(f"Date adjustments applied: {fetch_meta['adjustments']}")
        else:
            # 従来の動作（自動取得なし）
            await queries.ensure_coverage(
                session=session,
                symbols=symbols_list,
                date_from=date_from,
                date_to=date_to,
                refetch_days=settings.YF_REFETCH_DAYS,
            )
```
**完了条件**: 条件分岐が実装されている
**検証コマンド**: `grep -A5 "if auto_fetch:" app/api/v1/prices.py`

---

## app/core/config.py修正タスク

### CFG-001: タイムアウト設定値変更
**開始条件**: API-002完了
**対象ファイル**: `app/core/config.py`
**修正場所**: Settingsクラス内の定数定義（20-30行目）
**作業内容**:
```python
    # Database connection pool settings
    DB_POOL_SIZE: int = 2  # 5から2に変更
    DB_MAX_OVERFLOW: int = 3  # 5から3に変更
    DB_POOL_PRE_PING: bool = True
    DB_POOL_RECYCLE: int = 900  # 1800から900に変更
    DB_ECHO: bool = False
```
**完了条件**: 値が変更されている
**検証コマンド**: `grep "DB_POOL_SIZE: int = 2" app/core/config.py`

### CFG-002: Fetchタイムアウト値変更
**開始条件**: CFG-001完了
**対象ファイル**: `app/core/config.py`
**修正場所**: Settingsクラス内のFETCH関連設定（34-40行目）
**作業内容**:
```python
    YF_REQ_CONCURRENCY: int = 2  # 4から2に変更
    FETCH_TIMEOUT_SECONDS: int = 30  # 8から30に変更
    FETCH_MAX_RETRIES: int = 3
    FETCH_BACKOFF_MAX_SECONDS: float = 8.0
    REQUEST_TIMEOUT_SECONDS: int = 45  # 15から45に変更
```
**完了条件**: 値が変更されている
**検証コマンド**: `grep "FETCH_TIMEOUT_SECONDS: int = 30" app/core/config.py`

---

## docker/entrypoint.sh修正タスク

### ENT-001: entrypoint.sh全体置き換え
**開始条件**: CFG-002完了
**対象ファイル**: `docker/entrypoint.sh`
**修正場所**: ファイル全体
**作業内容**: 以下の内容で全体を置き換え
```bash
#!/usr/bin/env bash
set -euo pipefail

# 環境変数設定（シンプル）
export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL:-${DATABASE_URL}}"

# URLドライバー変換（asyncpg → psycopg）
if [[ "$ALEMBIC_DATABASE_URL" == *"asyncpg"* ]]; then
    export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL//asyncpg/psycopg}"
fi

echo "[entrypoint] Running migrations..."
alembic upgrade head || {
    echo "[entrypoint] Migration failed, attempting stamp..."
    alembic stamp head
}

echo "[entrypoint] Starting server..."
exec gunicorn app.main:app \
    --workers="${WEB_CONCURRENCY:-2}" \
    --worker-class=uvicorn.workers.UvicornWorker \
    --bind="0.0.0.0:${PORT:-8000}" \
    --timeout="${GUNICORN_TIMEOUT:-60}"
```
**完了条件**: ファイルが50行以下になっている
**検証コマンド**: `wc -l docker/entrypoint.sh | awk '{print ($1 < 50) ? "OK" : "NG"}'`

### ENT-002: 実行権限付与
**開始条件**: ENT-001完了
**対象ファイル**: `docker/entrypoint.sh`
**作業内容**:
```bash
chmod +x docker/entrypoint.sh
```
**完了条件**: 実行権限がある
**検証コマンド**: `test -x docker/entrypoint.sh && echo "OK"`

---

## render.yaml修正タスク

### RND-001: サービス名とplan設定
**開始条件**: ENT-002完了
**対象ファイル**: `render.yaml`
**修正場所**: servicesセクション（1-5行目）
**作業内容**:
```yaml
services:
  - type: web
    name: stockdata-api  # stock-apiから変更
    env: docker
    plan: starter
```
**完了条件**: name変更とplan明示
**検証コマンド**: `grep "name: stockdata-api" render.yaml`

### RND-002: 環境変数値更新
**開始条件**: RND-001完了
**対象ファイル**: `render.yaml`
**修正場所**: envVarsセクション（10-30行目）
**作業内容**:
```yaml
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: ALEMBIC_DATABASE_URL
        sync: false
      - key: DB_POOL_SIZE
        value: "2"  # 3から2に変更
      - key: DB_MAX_OVERFLOW
        value: "3"  # 2から3に変更
      - key: DB_POOL_RECYCLE
        value: "900"  # 1800から900に変更
      - key: GUNICORN_TIMEOUT
        value: "60"  # 180から60に変更
      - key: FETCH_TIMEOUT_SECONDS
        value: "30"  # 新規追加
      - key: REQUEST_TIMEOUT_SECONDS
        value: "45"  # 新規追加
      - key: YF_REQ_CONCURRENCY
        value: "2"  # 4から2に変更
      - key: WEB_CONCURRENCY
        value: "2"
      - key: API_MAX_SYMBOLS
        value: "50"
      - key: API_MAX_ROWS
        value: "1000000"
```
**完了条件**: 環境変数が更新されている
**検証コマンド**: `grep "FETCH_TIMEOUT_SECONDS" render.yaml`

---

## テストタスク

### TST-001: ローカルビルドテスト
**開始条件**: RND-002完了
**作業内容**:
```bash
docker-compose build
```
**完了条件**: ビルド成功
**検証コマンド**: `echo $?` (0なら成功)

### TST-002: ローカル起動テスト
**開始条件**: TST-001完了
**作業内容**:
```bash
docker-compose up -d
sleep 10
curl http://localhost:8000/healthz
```
**完了条件**: {"status": "ok"}が返る
**検証コマンド**: `curl -s http://localhost:8000/healthz | grep '"status": "ok"'`

### TST-003: 自動取得機能テスト
**開始条件**: TST-002完了
**作業内容**:
```bash
curl "http://localhost:8000/v1/prices?symbols=AAPL&from=1990-01-01&to=2024-01-31&auto_fetch=true"
```
**完了条件**: データが返る（空配列でない）
**検証コマンド**: `curl -s "http://localhost:8000/v1/prices?symbols=AAPL&from=2024-01-01&to=2024-01-31" | jq length`

---

## 実装順序

1. **削除フェーズ** (5分)
   - DEL-001〜DEL-004: 不要ファイル削除

2. **データベース層修正** (20分)
   - ENG-001〜ENG-002: engine.py修正
   - QRY-001〜QRY-004: queries.py修正

3. **API層修正** (10分)
   - API-001〜API-002: prices.py修正

4. **設定修正** (10分)
   - CFG-001〜CFG-002: config.py修正
   - ENT-001〜ENT-002: entrypoint.sh修正
   - RND-001〜RND-002: render.yaml修正

5. **テストフェーズ** (15分)
   - TST-001〜TST-003: ローカルテスト

**総所要時間**: 約60分

---

## 注意事項

1. **コードのみを実装**: コメントアウトやバックアップは作成しない
2. **完全置き換え**: 修正時は指定部分を完全に置き換える
3. **テスト必須**: 各タスク完了後に検証コマンドを実行
4. **順序厳守**: 開始条件を満たしてから実行
5. **エラー時**: 即座に停止し、エラー内容を記録

---

## コミットメッセージテンプレート

```
fix: [タスクID] タスク内容

- 変更内容の詳細
- 影響範囲
- テスト結果
```

例:
```
fix: [QRY-001] Add find_earliest_available_date function

- Added automatic detection of earliest available date
- Function tries common start dates to find data
- Tested with AAPL, MSFT symbols
```