meta:
  project: "調整済OHLCV API (MVP)"
  language: "Python 3.11"
  package_manager: "pip-tools or pip"
  test_runner: "pytest"
  style: "black, isort, flake8 (任意)"
  note: "外部ネットワークを伴う処理は必ずモック。DB依存テストはコードのみ作成可。"

tasks:

# ========= 0. ルート構成・依存 =========
- id: T000
  title: リポジトリ初期ファイルの作成
  depends_on: []
  files:
    - path: README.md
      desc: プロジェクト概要とローカル実行/テスト方針（1ページ）
    - path: .gitignore
      desc: Python, venv, __pycache__, .pytest_cache, .mypy_cache, dist 等
    - path: requirements.in
      desc: 上位依存（fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, pandas, numpy, yfinance, typer, httpx, pytest, pytest-asyncio, pytest-mock）
    - path: requirements.txt
      desc: pip-compile想定のピン留め結果（仮置きでも可）
    - path: Makefile
      desc: install/test/format ターゲット
  description: ルートの最低限のテキスト/依存ファイルを用意
  acceptance_criteria:
    - "requirements.txt が requirements.in を網羅"
    - "README に 'テストはネットワークモック' と明記"
  status: "done"
  owner: "assistant"
  start: "2024-04-10"
  end: "2024-04-10"
  notes: "初期ファイルを追加"

# ========= 1. アプリ雛形 =========
- id: T010
  title: FastAPI エントリポイント雛形
  depends_on: [T000]
  files:
    - path: app/main.py
      desc: FastAPI起動、/healthz プレースホルダ、lifespanでDB初期化予約
    - path: app/__init__.py
      desc: 空で可
    - path: app/api/__init__.py
      desc: 空で可
    - path: app/api/v1/__init__.py
      desc: 空で可
  description: アプリの土台を作る
  acceptance_criteria:
    - "TestClient で GET /healthz が 200 を返す(固定JSONで可)"
  status: "done"
  owner: "assistant"
  start: "2025-08-28"
  end: "2025-08-28"
  notes: "/healthz endpoint scaffolding"

- id: T011
  title: core.config の実装（Pydantic Settings）
  depends_on: [T010]
  files:
    - path: app/core/config.py
      desc: Settings クラス（env_file=.env）。既定値と型を定義
    - path: app/core/__init__.py
      desc: 空で可
  description: 設定を環境変数から取得
  acceptance_criteria:
    - "Settingsに以下のキー: APP_ENV, DATABASE_URL, API_MAX_SYMBOLS, API_MAX_ROWS, YF_REFETCH_DAYS, YF_REQ_CONCURRENCY, FETCH_TIMEOUT_SECONDS, REQUEST_TIMEOUT_SECONDS, CORS_ALLOW_ORIGINS, LOG_LEVEL"
    - "pytestで env を一時変更して反映を検証"
  status: "done"
  owner: "assistant"
  start: "2025-08-29"
  end: "2025-08-29"
  notes: "Settings implemented"

- id: T012
  title: core.logging の実装（構造化ログ）
  depends_on: [T010]
  files:
    - path: app/core/logging.py
      desc: configure_logging() で標準ログをJSON化（logging.LogRecordをjson.dumps）
  description: ログ基盤を用意（最低限）
  acceptance_criteria:
    - "pytest caplog で JSON 文字列が出力され、level/name/message を含む"
  status: "done"
  owner: "assistant"
  start: "2025-08-30"
  end: "2025-08-30"
  notes: "JSON logging configured"

- id: T013
  title: core.cors の実装
  depends_on: [T010, T011]
  files:
    - path: app/core/cors.py
      desc: CORS ミドルウェア工場関数 create_cors_middleware(settings)
  description: CORS 設定（許可オリジンCSV→配列）
  acceptance_criteria:
    - "空文字ならCORS無効、値があれば許可オリジンが設定されるユニットテスト"
  status: "done"
  owner: "assistant"
  start: "2025-08-31"
  end: "2025-08-31"
  notes: "CORS middleware implemented"

# ========= 2. DB 接続・モデル =========
- id: T020
  title: db.engine (asyncpg) 実装
  depends_on: [T010, T011]
  files:
    - path: app/db/engine.py
      desc: async_engine, async_sessionmaker を返すファクトリ
    - path: app/db/__init__.py
      desc: 空で可
  description: 非同期SQLAlchemyエンジン/セッション生成
  acceptance_criteria:
    - "pytestで engine/urlスキーム(postgresql+asyncpg) を検証（接続は不要）"
  status: "done"
  owner: "assistant"
  start: "2025-09-01"
  end: "2025-09-01"
  notes: "Async engine factory implemented"

- id: T021
  title: db.models 定義（symbols, symbol_changes, prices）
  depends_on: [T020]
  files:
    - path: app/db/base.py
      desc: Declarative Base 定義
    - path: app/db/models.py
      desc: 3テーブルのモデル（FK/PK/CHECK/UNIQUE/INDEX）
  description: スキーマをSQLAlchemyで記述
  acceptance_criteria:
    - "prices: PK(symbol,date), volume: BIGINT相当, last_updated: timezone=True"
    - "CHECK(高値/安値/前後関係) 定義済"
    - "symbol_changes: UNIQUE(new_symbol) と PK(old_symbol, change_date)"
    - "PostgreSQL方言へDDLコンパイル文字列にPK/FK/CHECKが含まれることをテスト"
  status: "done"
  owner: "assistant"
  start: "2025-09-02"
  end: "2025-09-02"
  notes: "SQLAlchemy models with constraints added"

# ========= 3. Alembic =========
- id: T030
  title: Alembic 初期化
  depends_on: [T021]
  files:
    - path: alembic.ini
      desc: 既定設定（script_location=app/migrations）
    - path: app/migrations/env.py
      desc: 非同期不要。metadata=Base.metadata を参照
    - path: app/migrations/script.py.mako
      desc: 標準テンプレート
  description: Alembic を使える状態に
  acceptance_criteria:
    - "env.py が app.db.base.Base を読み込む"
  status: "done"
  owner: "assistant"
  start: "2025-09-03"
  end: "2025-09-03"
  notes: "Alembic initialized"

- id: T031
  title: 001_init マイグレーション（3テーブル）
  depends_on: [T030]
  files:
    - path: app/migrations/versions/001_init.py
      desc: op.create_table で 3テーブル＋制約/インデックス
  description: 初期スキーマをDDL化
  acceptance_criteria:
    - "マイグレーションスクリプトに create_table('symbols'), create_table('symbol_changes'), create_table('prices') が存在"
    - "UNIQUE(new_symbol), CHECK群 がマイグレーションに明示"
  status: "done"
  owner: "assistant"
  start: "2025-09-04"
  end: "2025-09-04"
  notes: "Initial schema migration added"

- id: T032
  title: 002_fn_prices_resolved マイグレーション（SQL関数）
  depends_on: [T031]
  files:
    - path: app/migrations/versions/002_fn_prices_resolved.py
      desc: get_prices_resolved(_symbol,_from,_to) を CREATE FUNCTION / DROP FUNCTION
  description: 1ホップ透過解決SQL関数をDBに配布
  acceptance_criteria:
    - "スクリプト内に 'CREATE OR REPLACE FUNCTION get_prices_resolved' 文字列がある"
    - "ロールバックで DROP FUNCTION がある"
  status: "done"
  owner: "assistant"
  start: "2025-09-05"
  end: "2025-09-05"
  notes: "Function migration added"

# ========= 4. スキーマ & 依存注入 =========
- id: T040
  title: Pydantic スキーマ（共通/価格/メトリクス）
  depends_on: [T010]
  files:
    - path: app/schemas/common.py
      desc: DateRange(from: date, to: date), Validation
    - path: app/schemas/prices.py
      desc: PriceRowOut(symbol, date, open, high, low, close, volume, source, last_updated, source_symbol?)
    - path: app/schemas/metrics.py
      desc: MetricsOut(symbol, cagr, stdev, max_drawdown, n_days)
    - path: app/schemas/symbols.py
      desc: SymbolOut(symbol, name?, exchange?, currency?, is_active?, first_date?, last_date?)
  description: API I/O スキーマ
  acceptance_criteria:
    - "無効な日付レンジは ValidationError"
    - "PriceRowOut.date は date 型、last_updated は datetime(timezone) 型"
  status: "done"
  owner: "assistant"
  start: "2025-09-06"
  end: "2025-09-06"
  notes: "Pydantic schemas implemented"

- id: T041
  title: api.deps（依存注入）
  depends_on: [T020, T040]
  files:
    - path: app/api/deps.py
      desc: get_session()（async session dependency）
  description: ルータで使うDBセッション依存を定義
  acceptance_criteria:
    - "FastAPI Depends で awaitable session を供給できる擬似テスト"
  status: "done"
  owner: "assistant"
  start: "2025-09-07"
  end: "2025-09-07"
  notes: "DB session dependency implemented"

# ========= 5. サービス（ビジネスロジック） =========
- id: T050
  title: services.normalize（シンボル正規化）
  depends_on: [T040]
  files:
    - path: app/services/normalize.py
      desc: normalize_symbol(s:str)->str（大文字化/BRK.B→BRK-B/サフィックス維持）
    - path: tests/unit/test_normalize.py
      desc: 代表ケースのテスト
  description: 入出力の前処理
  acceptance_criteria:
    - "brk.b -> BRK-B, 7203.T -> 7203.T を満たす"
  status: "done"
  owner: "assistant"
  start: "2025-09-08"
  end: "2025-09-08"
  notes: "Symbol normalization implemented"

- id: T051
  title: services.resolver（1ホップ区間分割）
  depends_on: [T040]
  files:
    - path: app/services/resolver.py
      desc: segments_for(symbol, from, to, symbol_changes_rows) -> List[(actual_symbol, seg_from, seg_to)]
    - path: tests/unit/test_resolver.py
      desc: FB→META、変更日境界のテスト
  description: API/取得双方で使う区間分割ロジック（DB不要で純粋関数）
  acceptance_criteria:
    - "change_date当日以降を新、前日までを旧と判定"
  status: "done"
  owner: "assistant"
  start: "2025-09-09"
  end: "2025-09-09"
  notes: "1-hop resolver implemented"

- id: T052
  title: services.metrics（CAGR/STDEV/MaxDD）
  depends_on: [T040]
  files:
    - path: app/services/metrics.py
      desc: compute_metrics(price_frames:dict[symbol->pd.DataFrame]) -> list[dict]
    - path: tests/unit/test_metrics.py
      desc: 合成データで期待値を検証
  description: ログリターン、252日年率、最大DDの実装
  acceptance_criteria:
    - "CAGR = exp(sum(r)*252/N)-1"
    - "STDEV = std(r, ddof=1)*sqrt(252)"
    - "MaxDD 計算が既知事例で一致"
  status: "done"
  owner: "assistant"
  start: "2025-09-10"
  end: "2025-09-10"
  notes: "Metrics calculation implemented"

- id: T053
  title: services.upsert（DataFrame→UPSERT 準備）
  depends_on: [T040]
  files:
    - path: app/services/upsert.py
      desc: df_to_rows(df)->List[tuple], upsert_prices_sql()->str（ON CONFLICT ... DO UPDATE）
    - path: tests/unit/test_upsert.py
      desc: SQL文字列/行変換のテスト（DB接続不要）
  description: DBに入れるための整形とSQL生成
  acceptance_criteria:
    - "生成SQLに ON CONFLICT (symbol, date) DO UPDATE を含む"
    - "dfのNaNは除去/丸め方針を明確化（テストで確認）"
  status: "done"
  owner: "assistant"
  start: "2025-09-11"
  end: "2025-09-11"
  notes: "Prepared upsert SQL and row conversion helpers"

- id: T054
  title: services.fetcher（yfinance取得・N日リフレッチ・バックオフ）
  depends_on: [T053]
  files:
    - path: app/services/fetcher.py
      desc: fetch_prices(symbol,start,end, settings)->pd.DataFrame（auto_adjust=True想定）
    - path: tests/unit/test_fetcher.py
      desc: yfinance.download をモックし、再試行/タイムアウト/N日重ね起点を検証
  description: 取得層（ネットワークはモック）
  acceptance_criteria:
    - "429相当例外時に指数バックオフ（sleepはモック）"
    - "last_date - N 起点での再取得ロジックを関数単体で検証"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

- id: T055
  title: db.utils（アドバイザリロック）
  depends_on: [T020]
  files:
    - path: app/db/utils.py
      desc: async def advisory_lock(conn, symbol): pg_advisory_xact_lock(hashtext(symbol))
    - path: tests/unit/test_db_utils.py
      desc: SQL文字列/呼出しのみをモックで検証
  description: 競合制御（疑似テスト）
  acceptance_criteria:
    - "hashtext(symbol) を使う SQL が発行されることをモックで確認"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

# ========= 6. API ルータ =========
- id: T060
  title: 共通エラーモデル/ハンドラ
  depends_on: [T010, T040]
  files:
    - path: app/api/errors.py
      desc: raise_http_error(code, message), ハンドラ登録
    - path: tests/unit/test_errors.py
      desc: TestClientで 404/422/413 のJSON形状を確認
  description: エラーJSONの統一
  acceptance_criteria:
    - "レスポンス: {error:{code:string, message:string}} 形状"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

- id: T061
  title: /healthz 実装
  depends_on: [T060]
  files:
    - path: app/api/v1/health.py
      desc: DB未接続でも200を返す簡易版（後で拡張可）
    - path: app/api/v1/router.py
      desc: APIRouter集約（/v1）
    - path: tests/unit/test_health.py
      desc: 200/JSON検証
  description: 健康チェック
  acceptance_criteria:
    - "GET /healthz が {status:'ok'} を返す"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

- id: T062
  title: /v1/symbols（DBスタブで実装）
  depends_on: [T041, T040]
  files:
    - path: app/api/v1/symbols.py
      desc: GET /v1/symbols?active=bool の雛形（リポジトリ層は後日）
    - path: tests/unit/test_symbols_api.py
      desc: セッション/クエリをモックし、スキーマ整形をテスト
  description: 一覧エンドポイントの枠
  acceptance_criteria:
    - "クエリパラメータ active がbool扱いされる"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

- id: T063
  title: /v1/prices（解決区間→不足検知→取得→UPSERT→SELECT の枠）
  depends_on: [T041, T050, T051, T053, T054, T060]
  files:
    - path: app/api/v1/prices.py
      desc: GET /v1/prices 実装（現行シンボルで返し、source_symbol 任意）
    - path: tests/unit/test_prices_api_validate.py
      desc: symbols件数上限/from<=to/行数上限の入力検証テスト
  description: 価格エンドポイントの全体フロー（DB/ネットはモック）
  acceptance_criteria:
    - "入力バリデーション／エラーコードが仕様通り"
    - "resolver/normalize/upsert/fetcher が所定順で呼ばれることをモックで確認"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

- id: T064
  title: /v1/metrics 実装（純粋計算）
  depends_on: [T052, T063]
  files:
    - path: app/api/v1/metrics.py
      desc: GET /v1/metrics（DB経由で終値取得→共通営業日の交差→計算）
    - path: tests/unit/test_metrics_api.py
      desc: 入力/出力検証、計算は services.metrics を利用
  description: メトリクスAPI
  acceptance_criteria:
    - "出力が MetricsOut の配列であること"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

# ========= 7. DB クエリ層 =========
- id: T070
  title: db.queries（生SQL呼出しラッパ）
  depends_on: [T020, T021]
  files:
    - path: app/db/queries.py
      desc: get_prices_resolved(symbol, from, to), list_symbols(active?) 等（async）
    - path: tests/unit/test_db_queries_signatures.py
      desc: 関数シグネチャとSQL文字列をモック/検証
  description: DB用関数のシグネチャ確立
  acceptance_criteria:
    - "SQL文字列に get_prices_resolved が含まれること"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

# ========= 8. 管理CLI =========
- id: T080
  title: Typer CLI 雛形（エントリポイント）
  depends_on: [T050]
  files:
    - path: app/management/cli.py
      desc: Typer アプリ（add-symbol, verify-symbol のダミー）
    - path: app/management/__init__.py
      desc: 空で可
    - path: tests/unit/test_cli_entry.py
      desc: CliRunner でコマンド一覧が表示される
  description: CLIの土台
  acceptance_criteria:
    - "'--help' 実行でサブコマンドが見える（テスト）"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

- id: T081
  title: CLI: add-symbol（DBスタブ）
  depends_on: [T080, T050]
  files:
    - path: app/management/commands/add_symbol.py
      desc: normalize後、INSERT or UPSERT のダミー呼び出し
    - path: tests/unit/test_cli_add_symbol.py
      desc: 正常/重複時のメッセージ確認（DBはモック）
  description: 単体登録の骨格
  acceptance_criteria:
    - "正規化が呼ばれる"
    - "重複時の表示が異なる"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

# ========= 9. ロギング/ミドルウェア =========
- id: T090
  title: リクエストID/構造化ログミドルウェア
  depends_on: [T012, T010]
  files:
    - path: app/core/middleware.py
      desc: request_id 生成し contextvar にセット、レスポンスヘッダにも付与
    - path: tests/unit/test_middleware.py
      desc: ヘッダ付与/ログ出力をcaplogで検証
  description: 運用ログの基礎
  acceptance_criteria:
    - "X-Request-ID がレスポンスに含まれる"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

# ========= 10. ルータ統合 & main配線 =========
- id: T100
  title: main.py に全ルータ/ミドルウェア/設定を配線
  depends_on: [T011, T013, T061, T062, T063, T064, T090]
  files:
    - path: app/main.py
      desc: include_router, ミドルウェア追加, 例外ハンドラ登録
  description: アプリ配線の完成
  acceptance_criteria:
    - "TestClientで /healthz, /v1/prices, /v1/metrics のルーティングが成功（モックで）"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

# ========= 11. コンテナ & 実行ファイル =========
- id: T110
  title: Dockerfile / entrypoint.sh 作成
  depends_on: [T030, T100]
  files:
    - path: docker/Dockerfile
      desc: python:3.11-slim, pip install, alembic upgrade, gunicorn起動準備
    - path: docker/entrypoint.sh
      desc: set -e; alembic upgrade head; gunicorn起動
  description: デプロイ用のコードファイル
  acceptance_criteria:
    - "ファイルが存在し、CMD/ENTRYPOINTの文字列が期待どおり（文字列検証）"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

- id: T111
  title: docker-compose.yml（開発用）
  depends_on: [T110]
  files:
    - path: docker-compose.yml
      desc: api, postgres, adminer (任意) のサービス定義（起動は不要）
  description: ローカル実行のための構成ファイル（コードのみ）
  acceptance_criteria:
    - "services.api.build.context が ./ に設定されていること（YAML検証）"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

- id: T112
  title: render.yaml（Render用設定ファイル）
  depends_on: [T110]
  files:
    - path: render.yaml
      desc: type:web env:docker startCommandはdocker/entrypoint.sh 経由
  description: Render設定（コードのみ）
  acceptance_criteria:
    - "healthCheckPath: /healthz が含まれる"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

# ========= 12. API バリデーション強化 =========
- id: T120
  title: /v1/prices 入力制限（件数/期間/行上限）
  depends_on: [T063]
  files:
    - path: app/api/v1/prices.py
      desc: symbols上限(API_MAX_SYMBOLS)、期間正常化、上限行(API_MAX_ROWS)チェックを追加
    - path: tests/unit/test_prices_api_limits.py
      desc: 422/413 の境界テスト
  description: 防御的プログラミング
  acceptance_criteria:
    - "超過時のエラーコード/メッセージが仕様準拠"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

- id: T121
  title: /v1/metrics 共通営業日の交差
  depends_on: [T064]
  files:
    - path: app/services/metrics.py
      desc: インデックス交差ロジックを追加
    - path: tests/unit/test_metrics_common_days.py
      desc: 銘柄ごとに欠損日を作り、交差後のNで期待結果を検証
  description: 計算の厳密化
  acceptance_criteria:
    - "交差前後で N が期待どおりに変化"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

# ========= 13. 取得フローの統合（モックで） =========
- id: T130
  title: on-demand 取得のフロー制御（再チェック/ロック）
  depends_on: [T055, T054, T053, T063]
  files:
    - path: app/api/v1/prices.py
      desc: アドバイザリロック下で不足再確認→取得→UPSERT の疑似実装
    - path: tests/unit/test_prices_fetch_flow.py
      desc: 2並走の疑似→片方が取得をスキップする挙動（モック）をテスト
  description: 競合/冪等のフロー
  acceptance_criteria:
    - "2リクエストで fetcher が一度だけ呼ばれる"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

# ========= 14. 例外/タイムアウト =========
- id: T140
  title: 外部取得のタイムアウト/再試行
  depends_on: [T054, T130]
  files:
    - path: app/services/fetcher.py
      desc: タイムアウト/最大試行回数/バックオフ最大を設定値から適用
    - path: tests/unit/test_fetcher_retry_timeout.py
      desc: 例外系列で最終的にエラー化、成功系列で回数内成功をテスト
  description: 信頼性の確保
  acceptance_criteria:
    - "最大試行超過で例外が上がる"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

# ========= 15. エンドツーエンド（疑似） =========
- id: T150
  title: /v1/prices E2E 疑似（DB/ネット全面モック）
  depends_on: [T100]
  files:
    - path: tests/e2e/test_prices_endpoint.py
      desc: FastAPI TestClient で入力→出力形状/件数/フィールド検証
  description: 最終的なI/Oの契約テスト
  acceptance_criteria:
    - "symbol が現行名で統一され、source_symbol が任意で含まれる"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

- id: T151
  title: /v1/metrics E2E 疑似
  depends_on: [T100]
  files:
    - path: tests/e2e/test_metrics_endpoint.py
      desc: 計算値・キーの有無を検証（services.metrics をモック/実体）
  description: メトリクスの契約テスト
  acceptance_criteria:
    - "cagr/stdev/max_drawdown/n_days が存在し型が数値"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""

# ========= 16. CI（コードのみ） =========
- id: T160
  title: GitHub Actions CI（lint+test）
  depends_on: [T150, T151]
  files:
    - path: .github/workflows/ci.yml
      desc: ubuntu-latest, Python 3.11, pip install -r requirements.txt, pytest -q
  description: PR時にユニットテストを回す定義（実行は不要）
  acceptance_criteria:
    - "yml内に 'pytest -q' が含まれる"
  status: ""
  owner: ""
  start: ""
  end: ""
  notes: ""
