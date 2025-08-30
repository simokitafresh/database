以下は、あなたのMVP（調整済OHLCV＋汎用データ提供API）を前提にした全体アーキテクチャと、実運用を意識したファイル／フォルダ構成のリファレンスです。
MVPの非機能要件（同期オンデマンド取得・将来拡張容易・Render+Supabase・Alembic導入・1ホップのシンボル変更透過解決・直近N日リフレッチ）を織り込んでいます。
エージェントベースの開発フロー（Planner/Coder/Tester/Reviewer）を [`AGENTS.md`](AGENTS.md) に準拠し、仕様の正本としてこの文書を優先してください。


---

1. システム全体アーキテクチャ

1.1 コンポーネント概要

FastAPI（APIサーバ）：同期オンデマンド取得・DB返却・メトリクス計算。

PostgreSQL（Supabase）：symbols / symbol_changes / prices の中核DB、関数（get_prices_resolved）。

yfinance：不足区間の調整済OHLCVを都度取得（auto_adjust=True）。

Alembic：スキーマ／関数のマイグレーション管理。

管理CLI（Typer）：シンボルの補完・検証・変更適用（ドライラン対応）。

Docker：ポータブルな実行環境。Renderにそのまま配置。

エージェントフロー：開発を [`AGENTS.md`](AGENTS.md) のPlanner/Coder/Tester/Reviewerで推進。外部I/Oはモック、DBはコードのみでテスト。


1.2 依存関係（論理図）

graph LR
  Client[Client (Quant App / BI / 他サービス)] -->|HTTP/JSON| API[FastAPI (Web)]
  API -->|SQL (asyncpg)| PG[(PostgreSQL - Supabase)]
  API -->|on-demand fetch| YF[yfinance/Yahoo Finance]
  API -->|Alembic upgrade| PG
  CLI[管理CLI] -->|Admin ops| API
  CLI -->|SQL| PG
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

直近N日リフレッチ：分割・配当反映の遅延に備え、毎回 last_date - N から再取得してUPSERT（N=30など環境変数化）。

アドバイザリロック：同一シンボルの初回取得競合をDB側で防止。

完全同期：キューやジョブワーカー無し（MVP方針）。

エージェント準拠：実装は最小差分でPR作成、テストは外部I/Oモック（例: [`tests/unit/test_prices_upsert_call.py`](tests/unit/test_prices_upsert_call.py)）。



---

2. リポジトリ構成（推奨）

repo-root/
├─ README.md
├─ .env.example
├─ .gitignore
├─ Makefile
├─ pyproject.toml                  # poetry or hatch; or use requirements*.txt + pip-tools
├─ requirements.in                 # pip-tools 派の場合
├─ requirements.txt                # compiled, pinned
├─ docker/
│  ├─ Dockerfile
│  └─ entrypoint.sh                # alembic upgrade && gunicorn/uvicorn 起動
├─ docker-compose.yml              # dev用（api + postgres + adminer等）
├─ render.yaml                     # Render用（startCommand, env, healthcheck等）
├─ alembic.ini
├─ docs/
│  ├─ api.md                       # エンドポイント仕様・エラーコード例
│  ├─ data_definition.md           # 調整済の定義・タイムゾーン・通貨など
│  ├─ operations.md                # 運用Runbook（落ちた時・429時の対処）
│  └─ adr/                         # Architectural Decision Records
├─ app/
│  ├─ main.py                      # FastAPI起動, include_router, lifespan
│  ├─ core/
│  │  ├─ config.py                 # Pydantic Settings (env管理)
│  │  ├─ logging.py                # 構造化ログ (json)
│  │  ├─ cors.py                   # CORS allowlist
│  │  └─ version.py
│  ├─ api/
│  │  ├─ deps.py                   # 依存注入（DBセッション等）
│  │  ├─ errors.py                 # 共通エラーハンドラ（422/404/429/503）
│  │  └─ v1/
│  │     ├─ router.py              # v1 APIRouter
│  │     ├─ symbols.py             # GET /v1/symbols
│  │     ├─ prices.py              # GET /v1/prices
│  │     ├─ metrics.py             # GET /v1/metrics
│  │     └─ health.py              # GET /healthz
│  ├─ db/
│  │  ├─ base.py                   # SQLAlchemy Declarative Base
│  │  ├─ engine.py                 # async engine/session (asyncpg)
│  │  ├─ models.py                 # symbols, symbol_changes, prices
│  │  ├─ queries.py                # 生SQL（get_prices_resolved など）
│  │  └─ utils.py                  # advisory lock, helpers
│  ├─ services/
│  │  ├─ resolver.py               # シンボル変更の区間分割/解決
│  │  ├─ fetcher.py                # yfinance取得（N日リフレッチ、リトライ/バックオフ）
│  │  ├─ upsert.py                 # DataFrame→UPSERT（COPY or executemany）
│  │  ├─ metrics.py                # CAGR, STDEV, MaxDD（Pandas/Numpy）
│  │  └─ normalize.py              # シンボル正規化（Yahoo準拠, BRK.B→BRK-B等）
│  ├─ schemas/
│  │  ├─ common.py                 # Pydantic共通（DateRange等）
│  │  ├─ symbols.py                # SymbolOut 等
│  │  ├─ prices.py                 # PriceRowOut 等
│  │  └─ metrics.py                # MetricsOut 等
│  ├─ migrations/                  # Alembic
│  │  ├─ env.py
│  │  ├─ script.py.mako
│  │  └─ versions/
│  │     ├─ 001_init.py            # 3テーブル + 制約 + インデックス
│  │     ├─ 002_fn_prices_resolved.py # get_prices_resolved 関数
│  │     └─ 003_add_price_checks.py # 追加CHECK制約（例: OHLC値域チェック）
│  ├─ management/                  # 管理CLI（Typer）
│  │  ├─ cli.py                    # entry: python -m app.management.cli
│  │  └─ commands/
│  │     ├─ add_symbol.py
│  │     ├─ bulk_add.py
│  │     ├─ verify_symbol.py
│  │     └─ apply_symbol_change.py
│  └─ tests/
│     ├─ unit/
│     │  ├─ test_normalize.py
│     │  ├─ test_metrics.py
│     │  ├─ test_resolver.py
│     │  └─ test_prices_upsert_call.py # UPSERTトリガーテスト例
│     ├─ integration/
│     │  ├─ test_on_demand_fetch.py # 初回取得→N日重ね→UPSERT冪等
│     │  └─ test_symbol_change.py
│     └─ e2e/
│        └─ test_prices_endpoint.py
└─ .github/
   └─ workflows/
      └─ ci.yml                     # lint + test + build


---

3. 主要ファイルの役割と実装勘所

3.1 app/core/config.py（環境変数）

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_ENV: str = "dev"
    DATABASE_URL: str
    API_MAX_SYMBOLS: int = 50
    API_MAX_ROWS: int = 1_000_000
    YF_REFETCH_DAYS: int = 30
    YF_REQ_CONCURRENCY: int = 4
    FETCH_TIMEOUT_SECONDS: int = 8
    REQUEST_TIMEOUT_SECONDS: int = 15
    CORS_ALLOW_ORIGINS: str = ""  # comma-separated
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()

3.2 app/db/models.py（スキーマ定義・要点）

prices(symbol,date) 複合PK（別途の同一組インデックスは不要）。

型と制約（volume BIGINT NOT NULL、last_updated TIMESTAMPTZ DEFAULT now()、CHECK）。[`003_add_price_checks.py`](app/migrations/versions/003_add_price_checks.py) で追加CHECK制約（OHLC値域、ボリューム非負）。

FK：prices.symbol → symbols(symbol)（ON UPDATE CASCADE ON DELETE RESTRICT）。


3.3 app/services/resolver.py（1ホップ透過解決）

segments_for(symbol, from, to) を返す（[(actual_symbol, seg_from, seg_to), ...]）。

get_prices_resolved SQL関数と同一ロジックをPython側でも持ち、on‑demand取得の区間列挙に使う。


3.4 app/services/fetcher.py（オンデマンド取得）

直近N日リフレッチ：既存 last_date があれば max(from, last_date - N) を起点。

アドバイザリロック（pg_advisory_xact_lock(hashtext(symbol))）で重複取得防止。

指数バックオフと再試行（429/999対応）。

yfinance.download(ticker, start=..., end=..., auto_adjust=True)


3.5 app/services/upsert.py

DataFrameを**一時テーブル＋INSERT...ON CONFLICT DO UPDATE**で投入。

速度が必要なら COPY（psycopg/asyncpg-copy等）だが、MVPは executemany でも可。

監査目的で source に "yfinance/<version>" を格納。


3.6 app/api/v1/prices.py（入力制御）

バリデーション（symbols 件数、from<=to、結果行上限）。

先にDBを読むのではなく、**解決区間ベースで「不足検出→取得→UPSERT→確定SELECT」**の順。

レスポンスは現行シンボル名で統一。行単位に source_symbol を入れる設計も可。


3.7 app/services/metrics.py（定義固定）

価格：調整後終値。

日次ログリターン r_t = ln(P_t/P_{t-1})。

営業日：共通営業日の交差。

CAGR：exp(sum(r) * 252 / N) - 1

STDEV（年率）：std(r, ddof=1) * sqrt(252)

最大ドローダウン：累積対数リターンから算出。

欠損日はスキップ（前日補間なし）。



---

4. API仕様（MVP）

4.1 エンドポイント

GET /healthz：DB接続・簡易クエリOKで200

GET /v1/symbols?active=true：利用可能ティッカー

GET /v1/prices?symbols=AAPL,MSFT&from=YYYY-MM-DD&to=YYYY-MM-DD

返却：[{symbol, date, open, high, low, close, volume, source, last_updated, source_symbol?}]


GET /v1/metrics?symbols=AAPL,MSFT&from=...&to=...

返却：[{symbol, cagr, stdev, max_drawdown, n_days}]



4.2 エラーモデル（共通）

{ "error": { "code": "SYMBOL_NOT_FOUND", "message": "META not found" } }

代表コード：SYMBOL_NOT_FOUND, NO_DATA_IN_RANGE, TOO_MUCH_DATA, UPSTREAM_RATE_LIMITED, VALIDATION_ERROR



---

5. データベース（DDL 抜粋）

テーブル

CREATE TABLE symbols (
  symbol        TEXT PRIMARY KEY,
  name          TEXT,
  exchange      TEXT,
  currency      CHAR(3),
  is_active     BOOLEAN,
  first_date    DATE,
  last_date     DATE
);

CREATE TABLE symbol_changes (
  old_symbol    TEXT NOT NULL,
  new_symbol    TEXT NOT NULL UNIQUE, -- MVPは1ホップを保証
  change_date   DATE NOT NULL,
  reason        TEXT,
  PRIMARY KEY (old_symbol, change_date)
);

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
  CHECK (high >= low AND high >= open AND high >= close AND low <= open AND low <= close),
  CHECK (open>0 AND high>0 AND low>0 AND close>0),
  CHECK (volume >= 0)  -- 追加CHECK（003マイグレーション）
);

CREATE INDEX idx_symbol_changes_old ON symbol_changes(old_symbol);
CREATE INDEX idx_symbol_changes_new ON symbol_changes(new_symbol);

価格解決関数（1ホップ）

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

8. テスト戦略

単体：

シンボル正規化（BRK.B→BRK-B 等）

メトリクス計算（ゴールデン値・許容差）

区間解決（1ホップ分割）


結合：

初回取得→直近N日重ね→UPSERTの冪等性（[`tests/unit/test_prices_upsert_call.py`](tests/unit/test_prices_upsert_call.py) 参照）

429時のバックオフ挙動


E2E：

/v1/prices 上限行ガード・404/422/413系（[`tests/e2e/test_prices_endpoint.py`](tests/e2e/test_prices_endpoint.py) 参照）


テストDB：docker-compose.yml で postgres:16 を起動。alembic upgrade head を自動適用。

外部I/Oモック必須：[`AGENTS.md`](AGENTS.md) のテスト原則に従い、yfinance/DB接続をモック。


---

9. セキュリティ／SLO

CORS：許可オリジンを明示列挙。

リクエスト上限：API_MAX_ROWS でブロック、API_MAX_SYMBOLS 制限。

タイムアウト：外部取得8s／全体15s（環境変数化）。

SLO（MVP）：コールド取得時 5–15秒／DBヒット時 < 200ms 目安。


---

10. 運用CLI（Typer）

add-symbol: 1銘柄登録（名称・通貨等を可能な範囲で取得）

bulk-add: CSV一括登録

verify-symbol: yfinanceで取得可否・メタ情報検証

apply-symbol-change: old→new と change_date を登録（ドライラン対応）


python -m app.management.cli add-symbol --symbol META
python -m app.management.cli apply-symbol-change --old FB --new META --date 2022-06-09 --dry-run


---

11. 実装サンプル（ごく一部）

11.1 価格取得とUPSERT（疑似コード）

async def ensure_data_for_segments(symbol: str, date_from: date, date_to: date):
    segments = await segments_for(symbol, date_from, date_to)  # [(actual_symbol, seg_from, seg_to)]
    for s, f, t in segments:
        async with db.transaction():
            await advisory_lock(s)                 # 同一シンボルの競合防止
            gap = await detect_gap(s, f, t)        # 既存coverageとの差分
            if not gap: 
                continue
            f2 = max(gap.start, last_date(s) - relativedelta(days=settings.YF_REFETCH_DAYS))
            df = await yf_download_async(s, f2, gap.end)  # auto_adjust=True
            await upsert_prices(s, df, source="yfinance/0.2.x")

11.2 /v1/metrics の計算（概略）

def compute_metrics(price_map: dict[str, pd.DataFrame]) -> list[dict]:
    # 1) adj_close系列抽出 2) 共通営業日の交差 3) 日次log return
    # 4) CAGR = exp(sum(r) * 252 / N) - 1
    # 5) STDEV = std(r, ddof=1) * sqrt(252)
    # 6) MaxDD = min(1 - exp(cum_log_ret - cum_log_ret.cummax()))
    ...


---

12. 進め方（短期ロードマップ）

1. 雛形生成：上記フォルダでFastAPI・SQLAlchemy・Alembic初期化


2. DDL実装（001/002/003）：テーブル、関数、追加CHECK制約


3. /healthz→/symbols→/prices の順で実装（行上限制御・CORS調整）


4. オンデマンド取得（N日リフレッチ＋ロック）


5. /metrics 実装（定義固定）


6. 管理CLI と テスト（冪等性・429）


7. Docker化→Render/Supabase投入（起動時 alembic upgrade head）

エージェントフロー：[`AGENTS.md`](AGENTS.md) のPlannerでタスク特定、Coderで最小実装、Testerでモックテスト、Reviewerで仕様適合確認。


---

ひとこと

この構成はMVPのミニマム運用に必要十分かつ、将来の非同期化・キャッシュ・多段シンボル変更へほぼ無痛で拡張できます（resolver を再帰CTE化、キュー導入、Redis追加など）。

実装中に迷いがちなポイント（N日リフレッチ、アドバイザリロック、行上限制御、エラーモデル、TZ/DATE）は専用モジュールに分離しておくと運用コストが下がります。

