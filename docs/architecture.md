以下は、株価データ管理基盤（調整済OHLCV＋経済指標提供API）の全体アーキテクチャと、実運用を意識したファイル／フォルダ構成のリファレンスです。
非機能要件（同期オンデマンド取得・イベント駆動調整修正・将来拡張容易・Render+Supabase・Alembic導入・1ホップのシンボル変更透過解決・直近N日リフレッチ）を織り込んでいます。
エージェントベースの開発フロー（Planner/Coder/Tester/Reviewer）を [`AGENTS.md`](AGENTS.md) に準拠し、仕様の正本としてこの文書を優先してください。

**最終更新日**: 2025年12月4日

---

1. システム全体アーキテクチャ

1.1 コンポーネント概要

FastAPI（APIサーバ）：同期オンデマンド取得・DB返却・イベント管理・メンテナンスAPI。

PostgreSQL（Supabase）：symbols / symbol_changes / prices / fetch_jobs / corporate_events / economic_indicators の中核DB、関数（get_prices_resolved）。

yfinance：不足区間の調整済OHLCVを都度取得（auto_adjust=True, actions=True）。

FRED API：経済指標（DTB3等）の取得。

Alembic：スキーマ／関数のマイグレーション管理（11バージョン）。

Redis：分散ロック・キャッシュ（オプション、Standardプラン以上）。

プリフェッチサービス：主要銘柄のデータを定期的にキャッシュに事前読み込み。

Docker：ポータブルな実行環境。Renderにそのまま配置。

エージェントフロー：開発を [`AGENTS.md`](AGENTS.md) のPlanner/Coder/Tester/Reviewerで推進。外部I/Oはモック、DBはコードのみでテスト。


1.2 依存関係（論理図）

graph LR
  Client[Client (Quant App / BI / 他サービス)] -->|HTTP/JSON| API[FastAPI (Web)]
  API -->|SQL (asyncpg)| PG[(PostgreSQL - Supabase)]
  API -->|on-demand fetch| YF[yfinance/Yahoo Finance]
  API -->|経済指標取得| FRED[FRED API]
  API -->|キャッシュ/ロック| Redis[(Redis)]
  API -->|Alembic upgrade| PG
  Cron[Cron Jobs (Render)] -->|定期実行| API
  Prefetch[Prefetch Service] -->|データ事前取得| API
  Agents[Agents (Planner/Coder/Tester/Reviewer)] -->|Spec Update| Docs[architecture.md / AGENTS.md]

1.3 リクエストフロー（不足時のオンデマンド取得）

sequenceDiagram
  participant C as Client
  participant A as FastAPI
  participant P as Postgres
  participant Y as yfinance

  C->>A: GET /v1/prices?symbols=META&from=2021-01-01&to=2023-12-31
  A->>P: check coverage via get_prices_resolved segments
  alt gap exists
    A->>P: pg_advisory_xact_lock(hashtext('META'))
    A->>P: re-check gap (double-check under lock)
    A->>Y: fetch adj OHLCV for required segments (incl. last N days)
    Y-->>A: dataframe
    A->>P: UPSERT (INSERT...ON CONFLICT...)
  end
  A->>P: SELECT get_prices_resolved(...)
  P-->>A: rows (with source_symbol)
  A-->>C: 200 JSON (symbol=META, source_symbol in each row)

要点

1ホップのシンボル変更透過解決：symbol_changesに基づき、区間分割（<change_date は旧、>=change_date は新）。レスポンスは常に現行シンボルで返す（任意で source_symbol を各行に含め可）。

直近N日リフレッチ：分割・配当反映の遅延に備え、毎回 last_date - N から再取得してUPSERT（N=7が既定、環境変数YF_REFETCH_DAYSで変更可能）。

イベント駆動調整修正：yfinanceからのデータ取得時に `actions=True` で分割・配当イベントを検知し、即座に全履歴データを再取得。これにより乖離検知を待たずに翌日には正しいデータに修正される。

価格調整検出：定期チェックでDB価格とyfinance調整済み価格を比較し、分割・配当等による乖離を自動検出・修正。

アドバイザリロック：同一シンボルの初回取得競合をDB側で防止。Redis利用可能時は分散ロックも併用。

完全同期：基本はキューやジョブワーカー無し。バックグラウンドジョブはfetch_jobsテーブルで管理。

エージェント準拠：実装は最小差分でPR作成、テストは外部I/Oモック。



---

2. リポジトリ構成（現在の実装）

repo-root/
├─ README.md
├─ .env.example
├─ .gitignore
├─ Makefile
├─ pyproject.toml
├─ requirements.txt                # 依存関係（pip）
├─ runtime.txt                     # Pythonバージョン指定
├─ docker/
│  ├─ Dockerfile
│  └─ entrypoint.sh                # alembic upgrade && gunicorn/uvicorn 起動
├─ docker-compose.yml              # dev用（api + postgres）
├─ render.yaml                     # Render用（startCommand, env, healthcheck等）
├─ alembic.ini
├─ docs/
│  ├─ architecture.md              # この文書（仕様・DDL）
│  ├─ AGENTS.md                    # エージェント開発フロー
│  ├─ api-usage-guide.md           # API使用ガイド
│  └─ fred_api_architecture.md     # FRED API仕様
├─ app/
│  ├─ __init__.py
│  ├─ main.py                      # FastAPI起動, include_router, lifespan
│  ├─ core/
│  │  ├─ config.py                 # Pydantic Settings (env管理)
│  │  ├─ logging.py                # 構造化ログ (json)
│  │  ├─ cors.py                   # CORS allowlist
│  │  ├─ middleware.py             # リクエストIDミドルウェア
│  │  ├─ locking.py                # 分散ロック管理
│  │  └─ rate_limit.py             # レート制限
│  ├─ api/
│  │  ├─ deps.py                   # 依存注入（DBセッション、接続リトライ）
│  │  ├─ errors.py                 # 共通エラーハンドラ（422/404/429/503、接続エラー）
│  │  └─ v1/
│  │     ├─ router.py              # v1 APIRouter
│  │     ├─ symbols.py             # GET /v1/symbols
│  │     ├─ prices.py              # GET/DELETE /v1/prices
│  │     ├─ coverage.py            # GET /v1/coverage, /coverage/export
│  │     ├─ fetch.py               # POST/GET /v1/fetch (ジョブ管理)
│  │     ├─ events.py              # GET /v1/events (企業イベント管理)
│  │     ├─ economic.py            # GET /v1/economic (経済指標)
│  │     ├─ maintenance.py         # POST/GET /v1/maintenance/* (調整検出・修正)
│  │     ├─ cron.py                # POST /v1/daily-update, /adjustment-check
│  │     ├─ debug.py               # デバッグエンドポイント
│  │     └─ health.py              # GET /healthz
│  ├─ db/
│  │  ├─ base.py                   # SQLAlchemy Declarative Base
│  │  ├─ engine.py                 # async engine/session (asyncpg)
│  │  ├─ models.py                 # Symbol, SymbolChange, Price, FetchJob, CorporateEvent, EconomicIndicator
│  │  ├─ queries/                  # 生SQLクエリ
│  │  ├─ queries_optimized.py      # 最適化クエリ
│  │  └─ utils.py                  # advisory lock, helpers
│  ├─ services/
│  │  ├─ resolver.py               # シンボル変更の区間分割/解決
│  │  ├─ fetcher.py                # yfinance取得（N日リフレッチ、リトライ/バックオフ）
│  │  ├─ upsert.py                 # DataFrame→UPSERT
│  │  ├─ coverage.py               # カバレッジ計算
│  │  ├─ coverage_service.py       # カバレッジサービス
│  │  ├─ fetch_jobs.py             # ジョブ管理サービス
│  │  ├─ fetch_worker.py           # ジョブ実行ワーカー
│  │  ├─ query_optimizer.py        # SQL最適化（CTE利用）
│  │  ├─ normalize.py              # シンボル正規化（Yahoo準拠, BRK.B→BRK-B等）
│  │  ├─ event_service.py          # 企業イベント管理・記録
│  │  ├─ adjustment_detector.py    # 価格調整検出
│  │  ├─ adjustment_fixer.py       # 調整修正（再取得ジョブ作成）
│  │  ├─ daily_update_service.py   # 日次更新サービス
│  │  ├─ fred_service.py           # FRED API連携
│  │  ├─ price_service.py          # 価格取得サービス
│  │  ├─ prefetch_service.py       # データ事前取得
│  │  ├─ cache.py                  # キャッシュ管理（Redis/インメモリ）
│  │  ├─ redis_utils.py            # Redis接続ユーティリティ
│  │  ├─ auto_register.py          # シンボル自動登録（3フェーズアプローチ）
│  │  ├─ symbol_validator.py       # シンボル検証（Yahoo Finance）
│  │  ├─ data_cleaner.py           # データクリーニング
│  │  └─ profiling.py              # プロファイリング
│  ├─ schemas/
│  │  ├─ common.py                 # Pydantic共通（DateRange等）
│  │  ├─ symbols.py                # SymbolOut 等
│  │  ├─ prices.py                 # PriceRowOut 等
│  │  ├─ coverage.py               # CoverageOut, CoverageRequest等
│  │  ├─ fetch_jobs.py             # JobOut, JobRequest等
│  │  ├─ events.py                 # CorporateEventResponse等
│  │  ├─ economic.py               # EconomicDataOut等
│  │  ├─ cron.py                   # CronDailyUpdateRequest/Response
│  │  └─ maintenance.py            # AdjustmentCheckRequest/Response等
│  ├─ migrations/                  # Alembic
│  │  ├─ env.py
│  │  ├─ script.py.mako
│  │  └─ versions/
│  │     ├─ 001_init.py            # 3テーブル + 制約 + インデックス
│  │     ├─ 002_fn_prices_resolved.py # get_prices_resolved 関数
│  │     ├─ 003_add_price_checks.py # 追加CHECK制約
│  │     ├─ 004_create_fetch_jobs.py # fetch_jobsテーブル
│  │     ├─ 005_create_coverage_view.py # coverage_summaryビュー
│  │     ├─ 006_add_performance_indexes.py # パフォーマンスインデックス
│  │     ├─ 007_add_created_at_to_symbols.py # symbols.created_at追加
│  │     ├─ 008_add_full_history_flag.py # symbols.has_full_history追加
│  │     ├─ 009_update_get_prices_resolved_batch.py # バッチ対応関数
│  │     ├─ 010_add_economic_indicators.py # 経済指標テーブル
│  │     └─ 011_create_corporate_events.py # 企業イベントテーブル
│  ├─ monitoring/                  # 監視関連
│  ├─ profiling/                   # プロファイリング関連
│  └─ utils/                       # ユーティリティ
├─ scripts/
│  ├─ cron_*.sh                    # Cronジョブスクリプト
│  ├─ test_*.py / test_*.sh        # テスト・検証スクリプト
│  ├─ check_*.py / check_*.sql     # DB確認スクリプト
│  ├─ fix_*.py                     # 修正スクリプト
│  ├─ generate_token.py            # 認証トークン生成
│  └─ migrate_and_start.sh         # マイグレーション＆起動
├─ tests/
│  ├─ conftest.py                  # 共通フィクスチャ
│  ├─ test_*.py                    # 各種テスト
│  └─ unit/                        # 単体テスト
└─ .github/
   └─ workflows/
      └─ ci.yml                    # lint + test + build


---

3. 主要ファイルの役割と実装勘所

3.1 app/core/config.py（環境変数）

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # アプリケーション基本設定
    APP_NAME: str = "Stock Price Data API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres?sslmode=disable"
    
    # データベース接続プール設定
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_PRE_PING: bool = True
    DB_POOL_RECYCLE: int = 900
    DB_ECHO: bool = False
    
    # API設定
    API_MAX_SYMBOLS: int = 10
    API_MAX_SYMBOLS_LOCAL: int = 100  # DB読み出し専用
    API_MAX_ROWS: int = 50000
    API_MAX_ROWS_LOCAL: int = 200000  # DB読み出し専用
    YF_REFETCH_DAYS: int = 7
    YF_REQ_CONCURRENCY: int = 8
    
    # レート制限設定（Yahoo Finance API）
    YF_RATE_LIMIT_REQUESTS_PER_SECOND: float = 2.0
    YF_RATE_LIMIT_BURST_SIZE: int = 10
    YF_RATE_LIMIT_BACKOFF_MULTIPLIER: float = 2.0
    YF_RATE_LIMIT_BACKOFF_BASE_DELAY: float = 1.0
    YF_RATE_LIMIT_MAX_BACKOFF_DELAY: float = 60.0
    
    FETCH_TIMEOUT_SECONDS: int = 30
    FETCH_MAX_RETRIES: int = 3
    FETCH_BACKOFF_MAX_SECONDS: float = 8.0
    CORS_ALLOW_ORIGINS: str = ""
    LOG_LEVEL: str = "INFO"
    
    # Cron Job設定
    CRON_SECRET_TOKEN: str = ""
    CRON_BATCH_SIZE: int = 50
    CRON_UPDATE_DAYS: int = 7

    # FRED API設定
    FRED_API_KEY: Optional[str] = None
    
    # 自動登録設定
    ENABLE_AUTO_REGISTRATION: bool = True
    AUTO_REGISTER_TIMEOUT: int = 15
    YF_VALIDATE_TIMEOUT: int = 10
    
    # フェッチジョブ設定
    FETCH_JOB_MAX_SYMBOLS: int = 100
    FETCH_JOB_MAX_DAYS: int = 3650
    FETCH_JOB_TIMEOUT: int = 3600
    FETCH_WORKER_CONCURRENCY: int = 2
    FETCH_PROGRESS_UPDATE_INTERVAL: int = 5
    FETCH_JOB_CLEANUP_DAYS: int = 30
    FETCH_MAX_CONCURRENT_JOBS: int = 10

    # キャッシュ設定
    CACHE_TTL_SECONDS: int = 3600
    ENABLE_CACHE: bool = True
    PREFETCH_SYMBOLS: str = "TQQQ,TECL,GLD,XLU,^VIX,QQQ,SPY,TMV,TMF,LQD"
    PREFETCH_INTERVAL_MINUTES: int = 5

    # Redis設定
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_LOCK_TIMEOUT: int = 30
    REDIS_LOCK_BLOCKING_TIMEOUT: float = 10.0

    # プロファイリング設定
    ENABLE_PROFILING: bool = False

    # 価格調整検出設定
    ADJUSTMENT_CHECK_ENABLED: bool = True
    ADJUSTMENT_MIN_THRESHOLD_PCT: float = 0.001
    ADJUSTMENT_SAMPLE_POINTS: int = 10
    ADJUSTMENT_MIN_DATA_AGE_DAYS: int = 7
    ADJUSTMENT_AUTO_FIX: bool = True
    ADJUSTMENT_CHECK_FULL_HISTORY: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    class Config:
        env_file = ".env"

settings = Settings()

**環境変数の詳細:**

**価格調整検出設定:**
- `ADJUSTMENT_CHECK_ENABLED`: 調整検出機能全体のオン/オフ
- `ADJUSTMENT_MIN_THRESHOLD_PCT`: DB価格とyfinance価格の乖離検出閾値（%）
- `ADJUSTMENT_SAMPLE_POINTS`: 各シンボルでチェックする日付サンプル数（最大）
- `ADJUSTMENT_MIN_DATA_AGE_DAYS`: この日数より新しいデータは調整対象外
- `ADJUSTMENT_AUTO_FIX`: TrueでPOST check-adjustments時に自動で修正ジョブ作成
- `ADJUSTMENT_CHECK_FULL_HISTORY`: 全履歴をチェックするかどうか

**キャッシュ・プリフェッチ設定:**
- `ENABLE_CACHE`: キャッシュ機能の有効化
- `CACHE_TTL_SECONDS`: キャッシュ有効期限（秒）
- `PREFETCH_SYMBOLS`: 起動時に事前取得する銘柄リスト
- `PREFETCH_INTERVAL_MINUTES`: プリフェッチ間隔（分）

**レート制限設定:**
- `YF_RATE_LIMIT_REQUESTS_PER_SECOND`: 秒間リクエスト数上限
- `YF_RATE_LIMIT_BURST_SIZE`: バーストサイズ
- `YF_RATE_LIMIT_BACKOFF_MULTIPLIER`: バックオフ乗数
- `YF_RATE_LIMIT_MAX_BACKOFF_DELAY`: 最大バックオフ遅延（秒）

3.2 app/db/models.py（スキーマ定義・要点）

**主要テーブル:**

- **Symbol**: シンボルメタデータ（symbol PK, name, exchange, currency, is_active, has_full_history, first_date, last_date, created_at）
- **SymbolChange**: シンボル変更履歴（old_symbol, new_symbol UNIQUE, change_date）- 1ホップ保証
- **Price**: 価格データ（symbol, date 複合PK）、FK、CHECK制約付き
- **FetchJob**: ジョブ管理（job_id, status, symbols[], date_from, date_to, interval, force_refresh, priority, progress, results, errors）
- **CorporateEvent**: 企業イベント（id, symbol, event_date, event_type, ratio, amount, status, severity等）
- **EconomicIndicator**: 経済指標（symbol, date 複合PK, value）

**CHECK制約:**
- `ck_prices_low_le_open_close`: `low <= LEAST(open, close)`
- `ck_prices_open_close_le_high`: `GREATEST(open, close) <= high`
- `ck_prices_positive_ohlc`: `open>0 AND high>0 AND low>0 AND close>0`
- `ck_prices_volume_nonneg`: `volume >= 0`

**インデックス:**
- `idx_symbol_changes_old`, `idx_symbol_changes_new`
- `idx_corp_events_symbol`, `idx_corp_events_date`, `idx_corp_events_type`, `idx_corp_events_status`


3.3 app/services/resolver.py（1ホップ透過解決）

segments_for(symbol, from, to) を返す（[(actual_symbol, seg_from, seg_to), ...]）。

get_prices_resolved SQL関数と同一ロジックをPython側でも持ち、on‑demand取得の区間列挙に使う。


3.4 app/services/fetcher.py（オンデマンド取得・イベント検知）

直近N日リフレッチ：既存 last_date があれば max(from, last_date - N) を起点。

アドバイザリロック（pg_advisory_xact_lock(hashtext(symbol))）で重複取得防止。

指数バックオフと再試行（429/999対応）。

yfinance.download(ticker, start=..., end=..., auto_adjust=True, actions=True)

`actions=True` でイベント（分割・配当）を同時取得し、event_serviceに記録。

ジョブベースの非同期実行：fetch_jobsテーブルと連携したバックグラウンド処理


3.5 app/services/upsert.py

DataFrameを**一時テーブル＋INSERT...ON CONFLICT DO UPDATE**で投入。

速度が必要なら COPY（psycopg/asyncpg-copy等）だが、現在は executemany を使用。

監査目的で source に "yfinance/<version>" を格納。

**データ検証:** 無効なOHLC値（open/high/low/close ≤ 0）を含む行は自動的にスキップ。


3.6 app/services/coverage.py & coverage_service.py（データカバレッジ管理）

カバレッジ情報の取得・フィルタリング・ソート機能。

coverage_summaryビューを活用したパフォーマンス最適化。

CSV出力機能（StreamingResponse使用）。


3.7 app/services/fetch_jobs.py & fetch_worker.py（ジョブ管理）

fetch_jobsテーブルとの CRUD 操作。

ジョブステータス管理（pending → running → completed/failed/cancelled）。

バックグラウンドでのデータ取得実行。

複数シンボルの並行処理（セマフォ制御）。

プログレス追跡とエラーハンドリング。


3.8 app/services/adjustment_detector.py（価格調整検出）

**概要:** DB内の価格データとyfinance調整済み価格を比較し、分割・配当等による乖離を自動検出するサービス。

**主要クラス:**
- `PrecisionAdjustmentDetector`: メインサービスクラス
- `AdjustmentType`: 調整タイプ列挙（stock_split, reverse_split, dividend, special_dividend, spinoff, capital_gain, unknown）
- `AdjustmentSeverity`: 重要度（info, warning, critical, low, normal, high）

**メソッド:**
- `detect_adjustments(session, symbol)`: 単一シンボルの調整検出
- `scan_all_symbols(session, symbols?, auto_fix?)`: 全/指定シンボルスキャン
- `auto_fix_symbol(session, symbol)`: 自動修正（価格削除＋再取得ジョブ作成）

**検出フロー:**
1. DBから等間隔サンプルポイント取得（最大10点）
2. yfinanceから同日付の調整済み価格取得
3. 各ポイントで乖離率計算（閾値超で要修正判定）
4. 乖離パターンから調整タイプ推定（2倍→分割、0.5倍→逆分割、数%→配当等）
5. 要修正時、既存価格を削除しfetch_jobを作成して再取得


3.9 app/services/event_service.py（企業イベント管理）

**概要:** 企業イベント（分割・配当）の記録・管理サービス。

**主要機能:**
- `create_event()`: 新規イベント作成
- `get_events()`: フィルタ・ページネーション付きイベント一覧
- `get_pending_events()`: 未処理イベント取得
- `get_dividend_calendar()`: 配当カレンダー
- `get_split_history()`: 分割履歴
- `confirm_event()`, `ignore_event()`: イベントステータス更新


3.10 app/services/daily_update_service.py（日次更新）

**概要:** Cronジョブから呼び出される日次データ更新サービス。

**主要機能:**
- `execute_daily_update()`: 全アクティブシンボルの価格データ更新
- `execute_economic_update()`: 経済指標（FRED）データ更新
- バッチ処理による効率的な大量シンボル処理
- 調整チェック・自動修正との連携


3.11 app/services/fred_service.py（FRED API連携）

**概要:** FRED（Federal Reserve Economic Data）APIから経済指標を取得。

**対応指標:**
- DTB3: 3-Month Treasury Bill Secondary Market Rate

**機能:**
- `fetch_dtb3_data()`: DTB3データ取得
- `save_economic_data_async()`: 非同期データ保存（バッチ処理対応）


3.12 app/services/prefetch_service.py（プリフェッチ）

**概要:** 主要銘柄のデータを定期的に事前取得してキャッシュ。

**設定:**
- `PREFETCH_SYMBOLS`: 対象銘柄リスト
- `PREFETCH_INTERVAL_MINUTES`: 更新間隔

**注意:** Supabase環境（NullPool）では並行処理制限のため無効化。


3.13 app/services/cache.py（キャッシュ管理）

**概要:** Redis優先、インメモリフォールバックのキャッシュシステム。

**特徴:**
- Redis利用可能時はRedisを使用
- Redis接続失敗時は自動的にインメモリキャッシュにフォールバック
- TTL管理、最大サイズ制限


3.14 app/services/query_optimizer.py（クエリ最適化）

CTEベースのSQL最適化により50-70%のパフォーマンス向上。

大量データセットでの効率的な集計処理。



---

4. API仕様（現在実装）

4.1 エンドポイント一覧

**ヘルスチェック:**
- `GET /healthz`：DB接続・簡易クエリOKで200
- `GET /v1/health`：v1スコープのヘルスチェック
- `GET /`：ルートエンドポイント（status: ok）

**シンボル管理:**
- `GET /v1/symbols?active=true`：利用可能ティッカー一覧

**価格データ:**
- `GET /v1/prices?symbols=AAPL,MSFT&from=YYYY-MM-DD&to=YYYY-MM-DD`
  - 返却：[{symbol, date, open, high, low, close, volume, source, last_updated, source_symbol?}]
  - `auto_fetch=false` でDB読み出し専用モード（制限緩和: 100銘柄・200,000行）
- `DELETE /v1/prices/{symbol}`：特定シンボルの価格データを削除

**カバレッジ管理:**
- `GET /v1/coverage`：データカバレッジ一覧（フィルタ・ソート・ページネーション対応）
  - パラメータ：symbol, exchange, min_days/max_days, sort_by, order, limit/offset
- `GET /v1/coverage/export`：カバレッジデータのCSV出力（同じフィルタオプション）

**ジョブ管理:**
- `POST /v1/fetch`：データ取得ジョブ作成
  - ボディ：{symbols: [string], start_date: date, end_date?: date, force_refresh?: bool, priority?: string}
- `GET /v1/fetch/{job_id}`：ジョブ状態確認
- `GET /v1/fetch`：ジョブ一覧（status, limit/offsetでフィルタ）
- `POST /v1/fetch/{job_id}/cancel`：ジョブキャンセル

**企業イベント:**
- `GET /v1/events`：イベント一覧（symbol, event_type, status, from, to, page, page_sizeでフィルタ）
- `GET /v1/events/pending`：未処理イベント一覧
- `GET /v1/events/dividends`：配当カレンダー
- `GET /v1/events/splits`：分割履歴
- `GET /v1/events/{symbol}`：特定シンボルのイベント
- `POST /v1/events/{event_id}/confirm`：イベント確認
- `POST /v1/events/{event_id}/ignore`：イベント無視

**経済指標:**
- `GET /v1/economic`：利用可能な経済指標シリーズ一覧
- `GET /v1/economic/{symbol}`：経済指標データ取得（from, to, limit, orderでフィルタ）

**メンテナンス（価格調整検出・修正）:**
- `POST /v1/maintenance/check-adjustments`：価格調整チェック
  - ボディ：{symbols?: [string], threshold_pct?: float, auto_fix?: bool}
  - 返却：{scan_timestamp, total_symbols, scanned, needs_refresh, no_change, errors, summary}
- `GET /v1/maintenance/adjustment-report`：調整レポート取得
  - パラメータ：symbols, severity
- `POST /v1/maintenance/fix-adjustments`：調整修正実行
  - ボディ：{symbols?: [string], confirm: true}

**Cronジョブ（認証必要: X-Cron-Secret）:**
- `POST /v1/daily-update`：日次株価データ更新
  - ボディ：{dry_run?: bool, date_from?: string, date_to?: string, check_adjustments?: bool, auto_fix_adjustments?: bool}
- `POST /v1/daily-economic-update`：日次経済指標更新
- `POST /v1/adjustment-check`：定期調整チェック
- `GET /v1/status`：Cronステータス確認


4.2 エラーモデル（共通）

{ "error": { "code": "SYMBOL_NOT_FOUND", "message": "META not found" } }

**代表コード:**
- `SYMBOL_NOT_FOUND`: シンボルが見つからない
- `NO_DATA_IN_RANGE`: 指定期間にデータなし
- `TOO_MUCH_DATA`: 結果行数上限超過
- `UPSTREAM_RATE_LIMITED`: Yahoo Finance APIレート制限
- `VALIDATION_ERROR`: 入力バリデーションエラー
- `ADJUSTMENT_CHECK_DISABLED`: 調整チェック機能が無効
- `DATABASE_ERROR`: データベース接続エラー
- `SYMBOLS_ERROR`: シンボル取得エラー
- `MISSING_AUTH`: 認証ヘッダー欠落
- `INVALID_TOKEN`: 無効な認証トークン
- `SCAN_FAILED`: スキャン失敗



---

5. データベース（DDL 抜粋）

テーブル

**symbols（シンボルメタデータ）**
CREATE TABLE symbols (
  symbol        TEXT PRIMARY KEY,
  name          TEXT,
  exchange      TEXT,
  currency      CHAR(3),
  is_active     BOOLEAN,
  has_full_history BOOLEAN NOT NULL DEFAULT false,
  first_date    DATE,
  last_date     DATE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

**symbol_changes（シンボル変更履歴）**
CREATE TABLE symbol_changes (
  old_symbol    TEXT NOT NULL,
  new_symbol    TEXT NOT NULL UNIQUE, -- 1ホップを保証
  change_date   DATE NOT NULL,
  reason        TEXT,
  PRIMARY KEY (old_symbol, change_date)
);
CREATE INDEX idx_symbol_changes_old ON symbol_changes(old_symbol);
CREATE INDEX idx_symbol_changes_new ON symbol_changes(new_symbol);

**prices（価格データ）**
CREATE TABLE prices (
  symbol        TEXT NOT NULL REFERENCES symbols(symbol) ON UPDATE CASCADE ON DELETE RESTRICT,
  date          DATE NOT NULL,
  open          DOUBLE PRECISION NOT NULL,
  high          DOUBLE PRECISION NOT NULL,
  low           DOUBLE PRECISION NOT NULL,
  close         DOUBLE PRECISION NOT NULL,
  volume        BIGINT NOT NULL,
  source        TEXT NOT NULL,
  last_updated  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, date),
  CONSTRAINT ck_prices_low_le_open_close CHECK (low <= LEAST(open, close)),
  CONSTRAINT ck_prices_open_close_le_high CHECK (GREATEST(open, close) <= high),
  CONSTRAINT ck_prices_positive_ohlc CHECK (open>0 AND high>0 AND low>0 AND close>0),
  CONSTRAINT ck_prices_volume_nonneg CHECK (volume >= 0)
);

**fetch_jobs（ジョブ管理）**
CREATE TABLE fetch_jobs (
  job_id        TEXT PRIMARY KEY,
  status        TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
  symbols       TEXT[] NOT NULL,
  date_from     DATE NOT NULL,
  date_to       DATE NOT NULL,
  interval      TEXT NOT NULL DEFAULT '1d',
  force_refresh BOOLEAN NOT NULL DEFAULT false,
  priority      TEXT NOT NULL DEFAULT 'normal',
  progress      JSONB,
  results       JSONB,
  errors        JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at    TIMESTAMPTZ,
  completed_at  TIMESTAMPTZ,
  created_by    TEXT
);
CREATE INDEX idx_fetch_jobs_status ON fetch_jobs(status);
CREATE INDEX idx_fetch_jobs_created ON fetch_jobs(created_at);

**corporate_events（企業イベント）**
CREATE TABLE corporate_events (
  id            SERIAL PRIMARY KEY,
  symbol        TEXT NOT NULL REFERENCES symbols(symbol) ON UPDATE CASCADE ON DELETE CASCADE,
  event_date    DATE NOT NULL,
  event_type    TEXT NOT NULL CHECK (event_type IN ('stock_split', 'reverse_split', 'dividend', 'special_dividend', 'capital_gain', 'spinoff', 'unknown')),
  ratio         NUMERIC(10, 6),
  amount        NUMERIC(12, 4),
  currency      CHAR(3) DEFAULT 'USD',
  ex_date       DATE,
  detected_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  detection_method TEXT DEFAULT 'auto',
  db_price_at_detection NUMERIC(12, 4),
  yf_price_at_detection NUMERIC(12, 4),
  pct_difference NUMERIC(8, 6),
  severity      TEXT CHECK (severity IN ('critical', 'high', 'normal', 'low')),
  status        TEXT DEFAULT 'detected' CHECK (status IN ('detected', 'confirmed', 'fixing', 'fixed', 'ignored', 'failed')),
  fixed_at      TIMESTAMPTZ,
  fix_job_id    TEXT,
  rows_deleted  INTEGER,
  rows_refetched INTEGER,
  source_data   JSONB,
  notes         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(symbol, event_date, event_type)
);
CREATE INDEX idx_corp_events_symbol ON corporate_events(symbol);
CREATE INDEX idx_corp_events_date ON corporate_events(event_date DESC);
CREATE INDEX idx_corp_events_type ON corporate_events(event_type);
CREATE INDEX idx_corp_events_status ON corporate_events(status) WHERE status != 'fixed';
CREATE INDEX idx_corp_events_detected ON corporate_events(detected_at DESC);

**economic_indicators（経済指標）**
CREATE TABLE economic_indicators (
  symbol        TEXT NOT NULL,
  date          DATE NOT NULL,
  value         DOUBLE PRECISION,
  last_updated  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, date)
);

**カバレッジビュー（パフォーマンス最適化対応）**
CREATE VIEW coverage_summary AS
WITH price_stats AS (
  SELECT 
    symbol,
    COUNT(*) as data_points,
    MIN(date) as first_date,
    MAX(date) as last_date,
    MAX(last_updated) as last_updated
  FROM prices
  GROUP BY symbol
)
SELECT 
  s.symbol,
  s.name,
  s.exchange,
  s.currency,
  s.is_active,
  COALESCE(ps.data_points, 0) as data_points,
  ps.first_date,
  ps.last_date,
  ps.last_updated,
  CASE 
    WHEN ps.first_date IS NOT NULL AND ps.last_date IS NOT NULL 
    THEN ps.last_date - ps.first_date + 1
    ELSE 0
  END as total_days
FROM symbols s
LEFT JOIN price_stats ps ON s.symbol = ps.symbol;

**パフォーマンス最適化インデックス（主要）**
CREATE INDEX idx_prices_symbol_date_btree ON prices(symbol, date);
CREATE INDEX idx_prices_last_updated ON prices(last_updated);

**価格解決関数（1ホップ）**

CREATE OR REPLACE FUNCTION get_prices_resolved(_symbol TEXT, _from DATE, _to DATE)
RETURNS TABLE (
  symbol TEXT, date DATE,
  open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION,
  volume BIGINT, source TEXT, last_updated TIMESTAMPTZ, source_symbol TEXT
) LANGUAGE sql STABLE AS $$
WITH change AS (
  SELECT sc.old_symbol, sc.change_date
  FROM symbol_changes sc
  WHERE sc.new_symbol = _symbol
  LIMIT 1
),
segments AS (
  SELECT _symbol AS out_symbol, _symbol AS actual_symbol,
         COALESCE((SELECT change_date FROM change), _from) AS seg_from, _to AS seg_to
  UNION ALL
  SELECT _symbol, c.old_symbol, _from, c.change_date - INTERVAL '1 day'
  FROM change c
)
SELECT s.out_symbol AS symbol, p.date, p.open, p.high, p.low, p.close,
       p.volume, p.source, p.last_updated, p.symbol AS source_symbol
FROM segments s
JOIN prices p
  ON p.symbol = s.actual_symbol
 AND p.date BETWEEN s.seg_from::date AND s.seg_to::date
ORDER BY p.date;
$$;


---

6. デプロイ／ランタイム

6.1 Dockerfile（要点）

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
RUN chmod +x docker/entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]

6.2 docker/entrypoint.sh

#!/usr/bin/env bash
set -e
alembic upgrade head
exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 --workers 2 --timeout 30

6.3 Render（例：render.yaml）

services:
  - type: web
    name: stock-api
    env: docker
    plan: starter
    autoDeploy: true
    healthCheckPath: /healthz
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: API_MAX_SYMBOLS
        value: "50"
      - key: API_MAX_ROWS
        value: "1000000"
      - key: YF_REFETCH_DAYS
        value: "30"
      - key: YF_REQ_CONCURRENCY
        value: "4"
      - key: CORS_ALLOW_ORIGINS
        value: "https://your-frontend.example"


---

7. ロギング／監視

構造化JSONログ（request_id, route, symbols_count, rows_returned, fetch_count, fetch_wait_ms, db_time_ms, status）。

/healthz：DB ping + 簡易SELECT。

Renderのメトリクス＋将来はOpenTelemetry導入余地。


---

8. テスト戦略（実装済み）

**テストファイル構成:**
```
tests/
├─ conftest.py                 # 共通フィクスチャ（AsyncClient, DBセットアップ）
├─ test_healthz_endpoint.py    # ヘルスチェックテスト
├─ test_root_endpoint.py       # ルートエンドポイントテスト
├─ test_v1_health.py           # v1ヘルステスト
├─ test_symbols_endpoint.py    # シンボルAPIテスト
├─ test_symbols_list.py        # シンボル一覧テスト
├─ test_prices_basic.py        # 価格取得基本テスト
├─ test_prices_bulk.py         # 大量データテスト
├─ test_coverage_invalid_sort.py # カバレッジソートテスト
├─ test_fetch_job_creation.py  # ジョブ作成テスト
├─ test_fetcher_refactored.py  # フェッチャーテスト
├─ test_fred_service_mock.py   # FRED APIモックテスト
├─ test_event_flow.py          # イベントフローテスト
├─ test_adjustment_detector.py # 調整検出テスト
├─ test_adjustment_config.py   # 調整設定テスト
├─ test_cron_endpoint.py       # Cronエンドポイントテスト
├─ test_cron_adjustment.py     # Cron調整テスト
├─ test_maintenance_api.py     # メンテナンスAPIテスト
├─ test_maintenance_schemas.py # メンテナンススキーマテスト
├─ test_concurrency_fixes.py   # 並行処理テスト
└─ unit/                       # 単体テスト
```

**単体テスト:**
- シンボル正規化（BRK.B→BRK-B 等）
- 区間解決（1ホップ分割）
- データベースクエリの動作確認
- 調整検出ロジック

**統合テスト:**
- 基本API動作確認（/healthz, /v1/symbols, /v1/prices）
- ジョブ作成・取得・キャンセル機能
- CSV出力形式検証
- エラーハンドリング確認

**結合テスト:**
- 初回取得→直近N日重ね→UPSERTの冪等性
- 429時のバックオフ挙動
- イベント検知から修正までのフロー

**テスト環境:**
- docker-compose.yml で postgres:16 を起動
- alembic upgrade head を自動適用
- 外部I/Oモック必須（yfinance/DB接続をモック）
- AsyncClient を使用した非同期APIテスト


---

9. セキュリティ／SLO

**CORS:** 許可オリジンを明示列挙（CORS_ALLOW_ORIGINSで設定）。

**認証:**
- Cronエンドポイント: X-Cron-Secretヘッダーで認証
- CRON_SECRET_TOKENが未設定の場合は認証スキップ（開発用）

**リクエスト上限:**
- API_MAX_ROWS: 最大結果行数（デフォルト50,000）
- API_MAX_SYMBOLS: 最大シンボル数（デフォルト10）
- DB読み出し専用モード（auto_fetch=false）では制限緩和

**レート制限:**
- Yahoo Finance API: トークンバケット方式（2 req/s, バースト10）
- 指数バックオフ（最大60秒）

**タイムアウト:**
- FETCH_TIMEOUT_SECONDS: 30秒（外部取得）

**SLO:**
- コールド取得時: 5–15秒
- DBヒット時: < 200ms


---

10. 実装サンプル（疑似コード）

**10.1 価格取得とUPSERT**

async def ensure_data_for_segments(symbol: str, date_from: date, date_to: date):
    segments = await segments_for(symbol, date_from, date_to)
    for s, f, t in segments:
        async with db.transaction():
            await advisory_lock(s)                 # 同一シンボルの競合防止
            gap = await detect_gap(s, f, t)        # 既存coverageとの差分
            if not gap: 
                continue
            f2 = max(gap.start, last_date(s) - relativedelta(days=settings.YF_REFETCH_DAYS))
            df = await yf_download_async(s, f2, gap.end, auto_adjust=True, actions=True)
            
            # イベント検知
            if has_split_or_dividend(df):
                await record_corporate_event(session, s, df)
                
            await upsert_prices(s, df, source="yfinance/0.2.x")

**10.2 イベント駆動調整修正フロー**

async def handle_corporate_event(session, symbol: str, event: dict):
    # 1. イベントをDBに記録
    event_record = await event_service.create_event(session, event)
    
    # 2. 株式分割の場合は全履歴を再取得
    if event["event_type"] in ["stock_split", "reverse_split"]:
        # 既存データを削除
        deleted = await delete_prices(session, symbol)
        
        # 高優先度の再取得ジョブを作成
        job = await create_fetch_job(
            session, 
            symbols=[symbol],
            priority="high",
            force_refresh=True
        )
        
        # イベントステータスを更新
        await event_service.update_status(session, event_record.id, "fixing", job.job_id)


---

11. 進め方（実装完了ロードマップ）

✅ **1. 雛形生成**：FastAPI・SQLAlchemy・Alembic初期化完了

✅ **2. DDL実装（001-011）**：
- 001: 基本テーブル（symbols, symbol_changes, prices）
- 002: get_prices_resolved関数
- 003: 追加CHECK制約
- 004: fetch_jobsテーブル
- 005: coverage_summaryビュー
- 006: パフォーマンスインデックス
- 007: symbols.created_at追加
- 008: symbols.has_full_history追加
- 009: バッチ対応関数
- 010: economic_indicatorsテーブル
- 011: corporate_eventsテーブル

✅ **3. 基本API実装**：/healthz→/symbols→/prices の順で実装

✅ **4. オンデマンド取得**：N日リフレッチ＋ロック機能実装

✅ **5. 拡張API実装**：
- /v1/coverage（カバレッジ管理・CSV出力）
- /v1/fetch（ジョブ管理・バックグラウンド実行）
- /v1/events（企業イベント管理）
- /v1/economic（経済指標）
- /v1/maintenance（調整検出・修正）
- Cronエンドポイント

✅ **6. パフォーマンス最適化**：
- QueryOptimizer実装（50-70%高速化）
- キャッシュシステム（Redis/インメモリ）
- プリフェッチサービス

✅ **7. イベント駆動調整修正**：
- yfinanceからのイベント検知
- corporate_eventsテーブル管理
- 自動再取得ジョブ作成

✅ **8. 統合テストスイート**：包括的テストカバレッジ

✅ **9. ドキュメント整備**：README更新、API仕様明確化

✅ **10. Docker化→Render/Supabase対応**：起動時 alembic upgrade head 対応

エージェントフロー：[`AGENTS.md`](AGENTS.md) のPlannerでタスク特定、Coderで最小実装、Testerでモックテスト、Reviewerで仕様適合確認。


---

12. まとめ

この構成は本格運用に必要十分であり、将来の拡張にも対応可能な設計となっています。

**実装された主要機能：**
- **データカバレッジ管理**: シンボル別データ完全性監視とCSV出力
- **ジョブベースデータ取得**: 非同期バックグラウンド実行とステータス管理  
- **イベント駆動調整修正**: yfinanceからのイベント検知と自動修正
- **企業イベント管理**: 分割・配当の記録と追跡
- **経済指標対応**: FRED APIによるDTB3等の取得
- **パフォーマンス最適化**: QueryOptimizer、キャッシュ、プリフェッチ
- **包括的API**: RESTful エンドポイント群と統合テストスイート

**運用上のポイント:**
- N日リフレッチ（デフォルト7日）で分割・配当の遅延反映に対応
- イベント検知により翌日には自動修正
- アドバイザリロックで同一シンボルの競合防止
- Redis利用可能時は分散ロック・キャッシュを活用
- 行上限制御でリソース保護
- 構造化JSONログで運用監視


---

付記（2025年12月4日更新）

本ドキュメントは2025年12月4日に最新のコードベースに基づいて更新されました。

**主な変更点（2025年12月4日版）:**

1. **接続エラー対策の強化**
   - `deps.py`: セッション作成時のリトライロジック（最大3回）
   - `errors.py`: 接続エラー用グローバル例外ハンドラ（503 + Retry-After）
   - `auto_register.py`: 3フェーズアプローチでDB操作と外部API呼び出しを分離

2. **データ検証の強化**
   - `upsert.py`: 無効なOHLC値（open/high/low/close ≤ 0）の自動スキップ

3. **3フェーズシンボル登録**
   - Phase 1 (DB): 既存シンボルのバッチチェック
   - Phase 2 (External API): Yahoo Financeでのシンボル検証（DB接続を保持しない）
   - Phase 3 (DB): 検証済みシンボルのバッチ挿入

**主な変更点（2025年9月版からの差分）:****

1. **イベント駆動調整修正システム**
   - `corporate_events`テーブルの追加
   - `event_service.py`による企業イベント管理
   - `actions=True`でのイベント自動検知

2. **経済指標対応**
   - `economic_indicators`テーブルの追加
   - `fred_service.py`によるFRED API連携
   - `/v1/economic`エンドポイント

3. **キャッシュ・プリフェッチシステム**
   - `cache.py`: Redis/インメモリハイブリッドキャッシュ
   - `prefetch_service.py`: 主要銘柄の事前取得
   - Supabase環境での自動無効化

4. **レート制限強化**
   - トークンバケット方式の導入
   - 指数バックオフの改善

5. **マイグレーション拡張**
   - 007-011の追加マイグレーション
   - symbols.has_full_history, created_atの追加

6. **環境変数の整理**
   - キャッシュ設定の追加
   - Redis設定の追加
   - 調整検出設定の最適化


---

13. 接続/取得/ログ（実装詳細）

**接続とDSN:**
- アプリ実行時は `DATABASE_URL` に `postgresql+asyncpg://` を推奨
- Alembic実行時は同期ドライバ（`postgresql://` または `postgresql+psycopg://`）を使用
- Supabase対応: NullPoolを利用しPgBouncerのプールを前提とする
- Alembic の URL 補間回避: `app/migrations/env.py` で URL 内の `%` を `%%` にエスケープ

**接続エラー対策（NullPoolモード）:**

| コンポーネント | 戦略 | 説明 |
|--------------|--------|------|
| `deps.py` | リトライ付きセッション作成 | `connection was closed`エラー時に最大3回リトライ |
| `errors.py` | グローバル例外ハンドラ | SQLAlchemyエラーを503レスポンスに変換、`Retry-After`ヘッダ付き |
| `auto_register.py` | 3フェーズアプローチ | DB操作と外部API呼び出しを分離し、接続タイムアウトを防止 |
| `upsert.py` | データ検証 | 無効なOHLC値をスキップしてDB制約違反を防止 |

**/v1/prices のオンデマンド取得:****
- 1シンボル = 1トランザクションで処理
- アドバイザリロック → カバレッジ判定 → 必要区間の取得 → UPSERT → コミット
- yfinance は `download()` を基本とし、空/列不足時は `Ticker().history()` をフォールバック
- yfinance の `end` は排他的なため、内部で +1 日補正

**ログ:**
- `.env` の `LOG_LEVEL` をルートロガーへ適用（既定は `INFO`）
- `DEBUG` 時は詳細ログを出力
- 構造化JSONログ形式

**既知の落とし穴:**
- `change_date` 当日は新シンボルとして扱う（`<` 旧 / `>=` 新）
- `(symbol, date)` PK が BTree を持つため重複索引は不要
- CORS の `*` と資格情報は併用不可


---

14. DBスキーマ詳細（確定事項）

**symbols:**
- PK: `symbol`
- メタデータ: name, exchange, currency, is_active, has_full_history, first_date, last_date, created_at

**symbol_changes:**
- PK: `(old_symbol, change_date)`
- `UNIQUE(new_symbol)` で1ホップを担保

**prices:**
- PK: `(symbol, date)`
- FK: `symbol -> symbols.symbol (ON UPDATE CASCADE, ON DELETE RESTRICT)`
- CHECK制約で価格の整合性を保証

**fetch_jobs:**
- PK: `job_id`
- ステータス: pending, running, completed, failed, cancelled
- プログレス・結果・エラーをJSONBで格納

**corporate_events:**
- PK: `id` (SERIAL)
- UNIQUE: `(symbol, event_date, event_type)`
- ステータス: detected, confirmed, fixing, fixed, ignored, failed

**economic_indicators:**
- PK: `(symbol, date)`
- FRED APIからのデータを格納


---

以上が株価データ管理基盤の完全なアーキテクチャドキュメントです。