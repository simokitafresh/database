
---

PR#1: Migrations 一元化（Postgres に統一）

ブランチ名: feature/pr1-migrations-postgres
目的: Alembic が確実に Postgres に向くように統一。Docker 起動時の堅牢化。

ToDo（コミット粒度）

1. feat(migrations): support ALEMBIC_DATABASE_URL and -x db_url ✅

2. chore(entrypoint): set -euo pipefail and export ALEMBIC_DATABASE_URL ✅

3. docs(readme): note about Postgres migration source（任意） ✅



パッチ

1) migrations/env.py（置き換え）

diff --git a/app/migrations/env.py b/app/migrations/env.py
new file mode 100644
--- /dev/null
+++ b/app/migrations/env.py
@@ -0,0 +1,126 @@
+import os
+from logging.config import fileConfig
+from alembic import context
+from sqlalchemy import engine_from_config, pool
+
+# NOTE: app.db.base から Declarative Base を import（モデルの Metadata 集約）
+try:
+    from app.db.base import Base  # type: ignore
+except Exception:
+    # プロジェクト構成が異なる場合はここを調整
+    from app.db.models import Base  # fallback
+
+# Alembic Config オブジェクトは .ini を表す
+config = context.config
+
+# ログ設定
+if config.config_file_name is not None:
+    fileConfig(config.config_file_name)
+
+target_metadata = Base.metadata
+
+
+def _get_db_url() -> str:
+    """
+    優先順位:
+      1) -x db_url=...（CLI からの上書き）
+      2) 環境変数 ALEMBIC_DATABASE_URL
+      3) 環境変数 DATABASE_URL
+      4) alembic.ini の sqlalchemy.url
+    """
+    x_args = context.get_x_argument(asdict=True)
+    if "db_url" in x_args and x_args["db_url"]:
+        return x_args["db_url"]
+    env_url = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
+    if env_url:
+        return env_url
+    return config.get_main_option("sqlalchemy.url")
+
+
+def run_migrations_offline() -> None:
+    url = _get_db_url()
+    context.configure(
+        url=url,
+        target_metadata=target_metadata,
+        literal_binds=True,
+        dialect_opts={"paramstyle": "named"},
+        compare_type=True,
+    )
+    with context.begin_transaction():
+        context.run_migrations()
+
+
+def run_migrations_online() -> None:
+    url = _get_db_url()
+    connectable = engine_from_config(
+        config.get_section(config.config_ini_section),
+        prefix="sqlalchemy.",
+        poolclass=pool.NullPool,
+        url=url,
+    )
+    with connectable.connect() as connection:
+        context.configure(
+            connection=connection,
+            target_metadata=target_metadata,
+            compare_type=True,
+        )
+        with context.begin_transaction():
+            context.run_migrations()
+
+
+if context.is_offline_mode():
+    run_migrations_offline()
+else:
+    run_migrations_online()

2) docker/entrypoint.sh（置き換え）

diff --git a/docker/entrypoint.sh b/docker/entrypoint.sh
new file mode 100755
--- /dev/null
+++ b/docker/entrypoint.sh
@@ -0,0 +1,36 @@
+#!/usr/bin/env bash
+set -euo pipefail
+
+# 必要なら: wait-for-it/wait-for-postgres などで DB 起動を待つ
+# 例) until pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER"; do sleep 1; done
+
+export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL:-${DATABASE_URL:-}}"
+if [ -z "${ALEMBIC_DATABASE_URL:-}" ]; then
+  echo "[entrypoint] ERROR: DATABASE_URL or ALEMBIC_DATABASE_URL is not set" >&2
+  exit 1
+fi
+
+echo "[entrypoint] Running migrations against ${ALEMBIC_DATABASE_URL}"
+alembic upgrade head
+
+echo "[entrypoint] Starting gunicorn (UvicornWorker)"
+exec gunicorn app.main:app \
+  --workers="${WEB_CONCURRENCY:-2}" \
+  --worker-class=uvicorn.workers.UvicornWorker \
+  --bind="0.0.0.0:${PORT:-8000}" \
+  --timeout="${GUNICORN_TIMEOUT:-120}"


---

PR#2: /v1/prices バリデーション & 上限

ブランチ名: feature/pr2-prices-validation-limits
目的: 422/413 を厳密運用。シンボル正規化・去重・空要素除去を早期適用。

ToDo（コミット粒度）

1. feat(api): add strict validation for /v1/prices (symbols/date)


2. feat(api): enforce API_MAX_ROWS=413 after resolving


3. test(api): add e2e for 422/413/empty-symbols



パッチ

1) app/api/v1/prices.py（置き換え）

> 既存実装と関数名が異なる場合は、ルーター登録行だけ手元に合わせてください。



diff --git a/app/api/v1/prices.py b/app/api/v1/prices.py
new file mode 100644
--- /dev/null
+++ b/app/api/v1/prices.py
@@ -0,0 +1,236 @@
+from __future__ import annotations
+from datetime import date
+from typing import List
+
+from fastapi import APIRouter, Depends, HTTPException, Query
+
+from app.core.config import settings
+from app.schemas.prices import PriceRowOut
+from app.services.normalize import normalize_symbol
+from app.db.engine import get_session  # AsyncSession 依存性
+from app.db import queries
+
+router = APIRouter()
+
+
+def _parse_and_validate_symbols(symbols_raw: str) -> List[str]:
+    """
+    - カンマ分割 → trim → 空要素除去
+    - 正規化（大文字、クラス株、サフィックス維持）
+    - 去重
+    - 上限チェック
+    """
+    if not symbols_raw:
+        return []
+    items = [s.strip() for s in symbols_raw.split(",")]
+    items = [s for s in items if s]
+    normalized = [normalize_symbol(s) for s in items]
+    # unique & stable order
+    seen = set()
+    uniq = []
+    for s in normalized:
+        if s not in seen:
+            uniq.append(s)
+            seen.add(s)
+    if len(uniq) > settings.API_MAX_SYMBOLS:
+        raise HTTPException(status_code=422, detail="too many symbols requested")
+    return uniq
+
+
+@router.get("/prices", response_model=List[PriceRowOut])
+async def get_prices(
+    symbols: str = Query(..., description="Comma-separated symbols"),
+    date_from: date = Query(..., alias="from"),
+    date_to: date = Query(..., alias="to"),
+    session=Depends(get_session),
+):
+    # --- validation ---
+    if date_to < date_from:
+        raise HTTPException(status_code=422, detail="invalid date range")
+    symbols_list = _parse_and_validate_symbols(symbols)
+    if not symbols_list:
+        return []
+
+    # --- orchestration (欠損検出・再取得は内部サービスに委譲してもよい) ---
+    # 1) 欠損カバレッジを確認し、不足分＋直近N日を取得してUPSERT（冪等）
+    await queries.ensure_coverage(
+        session=session,
+        symbols=symbols_list,
+        date_from=date_from,
+        date_to=date_to,
+        refetch_days=settings.YF_REFETCH_DAYS,
+    )
+
+    # 2) 透過解決済み結果を取得
+    rows = await queries.get_prices_resolved(
+        session=session,
+        symbols=symbols_list,
+        date_from=date_from,
+        date_to=date_to,
+    )
+
+    if len(rows) > settings.API_MAX_ROWS:
+        raise HTTPException(status_code=413, detail="response too large")
+    return rows

> 補足: app/db/queries.py に ensure_coverage / get_prices_resolved が無い場合は、下記 PR#4 のパッチで追加します。ここでは先にエンドポイントだけ整えています。




---

PR#3: UTC/TZ 保証 & DB Check 制約

ブランチ名: feature/pr3-utc-and-db-checks
目的: last_updated の tz-aware/UTC を強制。OHLC/Volume の健全性を DB レベルでも担保。

ToDo（コミット粒度）

1. feat(schema): enforce tz-aware UTC for last_updated


2. feat(db): add CHECK constraints for prices (ohlc/volume)


3. migration(db): create checks for existing table



パッチ

1) app/schemas/prices.py（置き換え）

diff --git a/app/schemas/prices.py b/app/schemas/prices.py
new file mode 100644
--- /dev/null
+++ b/app/schemas/prices.py
@@ -0,0 +1,73 @@
+from __future__ import annotations
+from datetime import datetime, timezone
+from typing import Optional
+
+try:
+    # Pydantic v2
+    from pydantic import BaseModel, Field, field_validator
+except Exception:  # v1 fallback
+    from pydantic import BaseModel, Field, validator as field_validator  # type: ignore
+
+
+class PriceRowOut(BaseModel):
+    symbol: str
+    date: datetime | str  # ISO 日付文字列も許容（FastAPI の JSON エンコーダ対応）
+    open: float
+    high: float
+    low: float
+    close: float
+    volume: int
+    source: str
+    last_updated: datetime
+    source_symbol: Optional[str] = None
+
+    @field_validator("last_updated")
+    @classmethod
+    def _tz_aware_utc(cls, v: datetime) -> datetime:
+        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
+            raise ValueError("last_updated must be timezone-aware")
+        return v.astimezone(timezone.utc)

2) 追加マイグレーション（migrations/versions/00X_add_price_checks.py）

diff --git a/app/migrations/versions/00X_add_price_checks.py b/app/migrations/versions/00X_add_price_checks.py
new file mode 100644
--- /dev/null
+++ b/app/migrations/versions/00X_add_price_checks.py
@@ -0,0 +1,48 @@
+"""add check constraints for prices
+
+Revision ID: 00X_add_price_checks
+Revises: 002_fn_prices_resolved
+Create Date: 2025-08-29
+"""
+from alembic import op
+import sqlalchemy as sa
+
+# revision identifiers, used by Alembic.
+revision = '00X_add_price_checks'
+down_revision = '002_fn_prices_resolved'
+branch_labels = None
+depends_on = None
+
+
+def upgrade() -> None:
+    op.create_check_constraint(
+        "ck_prices_low_le_open_close",
+        "prices",
+        "low <= LEAST(open, close)",
+    )
+    op.create_check_constraint(
+        "ck_prices_open_close_le_high",
+        "prices",
+        "GREATEST(open, close) <= high",
+    )
+    op.create_check_constraint(
+        "ck_prices_positive_ohlc",
+        "prices",
+        "open > 0 AND high > 0 AND low > 0 AND close > 0",
+    )
+    op.create_check_constraint(
+        "ck_prices_volume_nonneg",
+        "prices",
+        "volume >= 0",
+    )
+
+
+def downgrade() -> None:
+    op.drop_constraint("ck_prices_volume_nonneg", "prices", type_="check")
+    op.drop_constraint("ck_prices_positive_ohlc", "prices", type_="check")
+    op.drop_constraint("ck_prices_open_close_le_high", "prices", type_="check")
+    op.drop_constraint("ck_prices_low_le_open_close", "prices", type_="check")

> 既存の models.py に CheckConstraint を併記しても良いですが、運用はマイグレーション優先で OK です。




---

PR#4: 欠損検出（LEAD）& 直近 N 日リフレッシュ

ブランチ名: feature/pr4-gap-refresh-logic
目的: DB カバレッジからギャップ（飛び日）抽出、YF_REFETCH_DAYS を含めて再取得→UPSERT→解決関数で返却。

ToDo（コミット粒度）

1. feat(queries): add ensure_coverage() and get_prices_resolved()


2. feat(resolver): helper for date segments (1-hop symbol change)


3. test(queries): gap detection and refetch boundary



パッチ

1) app/db/queries.py（置き換え／不足分の追加）

diff --git a/app/db/queries.py b/app/db/queries.py
new file mode 100644
--- /dev/null
+++ b/app/db/queries.py
@@ -0,0 +1,218 @@
+from __future__ import annotations
+from datetime import date, timedelta
+from typing import Iterable, List, Sequence
+from sqlalchemy import text
+from sqlalchemy.ext.asyncio import AsyncSession
+
+from app.core.config import settings
+from app.db.utils import with_symbol_lock
+from app.services.fetcher import fetch_prices_df  # 外部取得（auto_adjust=True を想定）
+from app.services.upsert import df_to_rows, upsert_prices_sql
+
+
+async def _get_coverage(session: AsyncSession, symbol: str, date_from: date, date_to: date) -> dict:
+    sql = text(
+        """
+        WITH rng AS (
+            SELECT :date_from::date AS dfrom, :date_to::date AS dto
+        ),
+        cov AS (
+            SELECT
+              MIN(date) AS first_date,
+              MAX(date) AS last_date,
+              COUNT(*)  AS cnt
+            FROM prices
+            WHERE symbol = :symbol
+              AND date BETWEEN (SELECT dfrom FROM rng) AND (SELECT dto FROM rng)
+        ),
+        gaps AS (
+            SELECT p.date AS cur_date,
+                   LEAD(p.date) OVER (ORDER BY p.date) AS next_date
+            FROM prices p
+            WHERE p.symbol = :symbol
+              AND p.date BETWEEN (SELECT dfrom FROM rng) AND (SELECT dto FROM rng)
+        )
+        SELECT
+            (SELECT first_date FROM cov) AS first_date,
+            (SELECT last_date  FROM cov) AS last_date,
+            (SELECT cnt        FROM cov) AS cnt,
+            EXISTS (
+              SELECT 1 FROM gaps g WHERE g.next_date IS NOT NULL AND g.next_date > g.cur_date + INTERVAL '1 day'
+            ) AS has_gaps
+        """
+    )
+    res = await session.execute(
+        sql.bindparams(symbol=symbol, date_from=date_from, date_to=date_to)
+    )
+    row = res.mappings().first() or {}
+    return dict(row)
+
+
+async def ensure_coverage(
+    session: AsyncSession,
+    symbols: Sequence[str],
+    date_from: date,
+    date_to: date,
+    refetch_days: int,
+) -> None:
+    """
+    各シンボルごとに:
+      1) アドバイザリロック取得
+      2) カバレッジ確認 + ギャップ検出
+      3) 直近 refetch_days を含めて外部取得
+      4) UPSERT（ON CONFLICT）
+    """
+    for symbol in symbols:
+        async with session.begin():
+            await with_symbol_lock(session, symbol)
+            cov = await _get_coverage(session, symbol, date_from, date_to)
+
+            # refetch start（DB 最終日 - N日）: DB になければ date_from から
+            refetch_start = cov.get("last_date") or date_from
+            refetch_start = max(date_from, refetch_start - timedelta(days=refetch_days))
+
+            df = await fetch_prices_df(symbol=symbol, start=refetch_start, end=date_to)
+            if df is None or df.empty:
+                continue
+            rows = df_to_rows(df, symbol=symbol, source="yfinance")
+            if not rows:
+                continue
+            upsert_sql = upsert_prices_sql()
+            await session.execute(text(upsert_sql), {"rows": rows})
+        # トランザクションは with ブロックで commit/rollback
+
+
+async def get_prices_resolved(
+    session: AsyncSession,
+    symbols: Sequence[str],
+    date_from: date,
+    date_to: date,
+) -> List[dict]:
+    """
+    SQL 関数 get_prices_resolved(symbol, from, to) を経由して透過的に取得。
+    """
+    out: List[dict] = []
+    sql = text("SELECT * FROM get_prices_resolved(:symbol, :date_from, :date_to)")
+    for s in symbols:
+        res = await session.execute(sql.bindparams(symbol=s, date_from=date_from, date_to=date_to))
+        out.extend([dict(m) for m in res.mappings().all()])
+    # サーバ側で順序固定
+    out.sort(key=lambda r: (r["date"], r["symbol"]))
+    return out

> 注: ここでは services.fetcher.fetch_prices_df と services.upsert に依存しています。名称が異なる場合はお手元の実装名に合わせてください。




---

PR#5: Fetcher の同時実行制御 & リトライ統一

ブランチ名: feature/pr5-fetcher-concurrency-retry
目的: yfinance 等の一時エラー・レート制限への耐性を強化。

ToDo（コミット粒度）

1. feat(fetcher): add asyncio.Semaphore for concurrency


2. feat(fetcher): add tenacity retry/backoff honoring settings


3. chore(requirements): add tenacity



パッチ

1) app/services/fetcher.py（置き換え）

diff --git a/app/services/fetcher.py b/app/services/fetcher.py
new file mode 100644
--- /dev/null
+++ b/app/services/fetcher.py
@@ -0,0 +1,113 @@
+from __future__ import annotations
+import asyncio
+from datetime import date, datetime
+from typing import Optional
+
+import pandas as pd
+
+from app.core.config import settings
+
+try:
+    import yfinance as yf
+except Exception:  # pragma: no cover
+    yf = None
+
+try:
+    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
+except Exception:
+    # tenacity 未導入でも読み込めるようにダミー実装
+    def retry(*args, **kwargs):
+        def deco(fn):
+            return fn
+        return deco
+    def stop_after_attempt(n):  # type: ignore
+        return None
+    def wait_exponential(max=8.0):  # type: ignore
+        return None
+    def retry_if_exception_type(*exc):  # type: ignore
+        return None
+
+
+_sem = asyncio.Semaphore(settings.YF_REQ_CONCURRENCY)
+
+
+class FetchError(Exception):
+    pass
+
+
+@retry(
+    stop=stop_after_attempt(settings.FETCH_MAX_RETRIES),
+    wait=wait_exponential(max=settings.FETCH_BACKOFF_MAX_SECONDS),
+    retry=retry_if_exception_type(Exception),
+)
+async def fetch_prices_df(symbol: str, start: date, end: date) -> Optional[pd.DataFrame]:
+    """
+    auto_adjust=True 相当のデータを DataFrame で返す。
+    返却: index=Datetime, columns=[Open, High, Low, Close, Volume]
+    """
+    if yf is None:
+        raise FetchError("yfinance is not available")
+    async with _sem:
+        loop = asyncio.get_running_loop()
+        df = await loop.run_in_executor(
+            None,
+            lambda: yf.download(
+                symbol,
+                start=start,
+                end=end,
+                progress=False,
+                auto_adjust=True,
+                threads=False,
+            ),
+        )
+        if isinstance(df, pd.DataFrame) and not df.empty:
+            df = df.rename(
+                columns={
+                    "Open": "open",
+                    "High": "high",
+                    "Low": "low",
+                    "Close": "close",
+                    "Volume": "volume",
+                }
+            )
+            df.index = pd.to_datetime(df.index)
+            return df[["open", "high", "low", "close", "volume"]]
+        return None

2) requirements.txt（追記）

diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,3 +1,6 @@
+# 既存行は維持してください。以下は追加分です。
+tenacity>=8.2
+pandas>=2.0

> pandas が既に入っていれば重複可。ピンはプロジェクト方針に合わせて調整ください。




---

PR#6: セキュリティ（入力クリーニング/SQL パラメータ化/CORS）

ブランチ名: feature/pr6-security-input-cors
目的: Injection/無効入力を抑止。CORS の * × credentials* 誤設定を防止。

ToDo（コミット粒度）

1. feat(normalize): add sanitize_symbols and allowed-char regex


2. refactor(api): parameterize raw SQL in /v1/symbols


3. feat(cors): disable credentials when origins="*"



パッチ

1) app/services/normalize.py（置き換え or 追記）

diff --git a/app/services/normalize.py b/app/services/normalize.py
new file mode 100644
--- /dev/null
+++ b/app/services/normalize.py
@@ -0,0 +1,77 @@
+import re
+from typing import Iterable, List
+
+ALLOWED = re.compile(r"^[A-Z0-9.\-]+$")
+
+def normalize_symbol(s: str) -> str:
+    """
+    大文字化、クラス株置換（BRK.B → BRK-B）、取引所サフィックスは維持。
+    """
+    s = s.strip().upper()
+    s = s.replace("BRK.B", "BRK-B")
+    return s
+
+
+def sanitize_symbols(symbols: Iterable[str], limit: int) -> List[str]:
+    """
+    - trim → 空要素除去
+    - 正規化
+    - 許可文字のみ（A-Z0-9.-）
+    - 去重
+    - 上限チェックは呼び出し側で
+    """
+    seen = set()
+    out: List[str] = []
+    for s in symbols:
+        s = s.strip()
+        if not s:
+            continue
+        s = normalize_symbol(s)
+        if not ALLOWED.match(s):
+            continue
+        if s in seen:
+            continue
+        out.append(s)
+        seen.add(s)
+        if len(out) >= limit:
+            break
+    return out

2) app/api/v1/symbols.py（置き換え）

diff --git a/app/api/v1/symbols.py b/app/api/v1/symbols.py
new file mode 100644
--- /dev/null
+++ b/app/api/v1/symbols.py
@@ -0,0 +1,60 @@
+from __future__ import annotations
+from typing import List, Optional
+from fastapi import APIRouter, Depends, Query
+from sqlalchemy import text
+from app.db.engine import get_session
+
+router = APIRouter()
+
+@router.get("/symbols")
+async def list_symbols(
+    active: Optional[bool] = Query(default=None),
+    session=Depends(get_session),
+) -> List[dict]:
+    if active is None:
+        sql = text("SELECT symbol, name, exchange, currency, is_active FROM symbols")
+        res = await session.execute(sql)
+    else:
+        sql = text(
+            "SELECT symbol, name, exchange, currency, is_active "
+            "FROM symbols WHERE is_active = :active"
+        )
+        res = await session.execute(sql.bindparams(active=active))
+    return [dict(m) for m in res.mappings().all()]

3) app/core/cors.py（置き換え）

diff --git a/app/core/cors.py b/app/core/cors.py
new file mode 100644
--- /dev/null
+++ b/app/core/cors.py
@@ -0,0 +1,49 @@
+from __future__ import annotations
+from fastapi.middleware.cors import CORSMiddleware
+from starlette.middleware import Middleware
+from app.core.config import settings
+
+
+def build_cors_middleware() -> Middleware:
+    """
+    CORS_ALLOW_ORIGINS が "*" の場合はブラウザ仕様上 credentials を無効化。
+    CSV 指定時のみ credentials を有効化できる。
+    """
+    origins_str = (settings.CORS_ALLOW_ORIGINS or "").strip()
+    if not origins_str:
+        allow_origins = []
+    elif origins_str == "*":
+        allow_origins = ["*"]
+    else:
+        allow_origins = [o.strip() for o in origins_str.split(",") if o.strip()]
+
+    allow_credentials = False
+    if allow_origins and allow_origins != ["*"]:
+        allow_credentials = True
+
+    return Middleware(
+        CORSMiddleware,
+        allow_origins=allow_origins,
+        allow_credentials=allow_credentials,
+        allow_methods=["*"],
+        allow_headers=["*"],
+        expose_headers=["X-Request-ID"],
+    )

> app/main.py で add_middleware(*build_cors_middleware()) ではなく、app.add_middleware(CORSMiddleware, ...) に合わせて適用してください。既存実装がある場合はロジックだけ反映でも OK。




---

PR#7: 観測性 & CI（ruff/black/mypy）

ブランチ名: feature/pr7-observability-ci
目的: 1リクエストの処理統計をログ出力。CI に Lint/Format/Type-Check を追加。

ToDo（コミット粒度）

1. feat(api): log processing stats (rows, duration, symbols)


2. chore(ci): add ruff/black/mypy steps


3. chore(cfg): add pyproject.toml for tooling



パッチ

1) /v1/prices のログ追記（既存に差し込む）

> PR#2 の prices.py をベースに、処理時間と件数をログへ。置き換え版を再掲します。



diff --git a/app/api/v1/prices.py b/app/api/v1/prices.py
--- a/app/api/v1/prices.py
+++ b/app/api/v1/prices.py
@@ -1,13 +1,22 @@
 from __future__ import annotations
 from datetime import date
 from typing import List
+import time
+import logging
 
 from fastapi import APIRouter, Depends, HTTPException, Query
 
 from app.core.config import settings
 from app.schemas.prices import PriceRowOut
 from app.services.normalize import normalize_symbol
 from app.db.engine import get_session  # AsyncSession 依存性
 from app.db import queries
 
 router = APIRouter()
+logger = logging.getLogger(__name__)
@@
 async def get_prices(
@@
-    await queries.ensure_coverage(
+    t0 = time.perf_counter()
+    await queries.ensure_coverage(
         session=session,
         symbols=symbols_list,
         date_from=date_from,
         date_to=date_to,
         refetch_days=settings.YF_REFETCH_DAYS,
     )
@@
-    if len(rows) > settings.API_MAX_ROWS:
+    n = len(rows)
+    if n > settings.API_MAX_ROWS:
         raise HTTPException(status_code=413, detail="response too large")
-    return rows
+    dt_ms = int((time.perf_counter() - t0) * 1000)
+    logger.info(
+        "prices served",
+        extra=dict(symbols=symbols_list, date_from=str(date_from), date_to=str(date_to), rows=n, duration_ms=dt_ms),
+    )
+    return rows

2) .github/workflows/ci.yml（置き換え）

diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
new file mode 100644
--- /dev/null
+++ b/.github/workflows/ci.yml
@@ -0,0 +1,53 @@
+name: CI
+on:
+  push:
+    branches: [ main, develop, feature/** ]
+  pull_request:
+    branches: [ main, develop ]
+
+jobs:
+  build:
+    runs-on: ubuntu-latest
+    steps:
+      - uses: actions/checkout@v4
+      - uses: actions/setup-python@v5
+        with:
+          python-version: "3.11"
+      - name: Install deps
+        run: |
+          python -m pip install --upgrade pip
+          pip install -r requirements.txt
+          pip install ruff black mypy
+      - name: Lint (ruff)
+        run: ruff check .
+      - name: Format (black --check)
+        run: black --check .
+      - name: Type check (mypy)
+        run: mypy app || true
+      - name: Tests
+        env:
+          PYTHONPATH: .
+        run: pytest -q

3) pyproject.toml（追加）

diff --git a/pyproject.toml b/pyproject.toml
new file mode 100644
--- /dev/null
+++ b/pyproject.toml
@@ -0,0 +1,34 @@
+[tool.black]
+line-length = 100
+target-version = ["py311"]
+exclude = '''
+/(
+  \.git
+ | \.venv
+ | build
+ | dist
+)/
+'''
+
+[tool.ruff]
+line-length = 100
+target-version = "py311"
+select = ["E", "F", "I"]
+ignore = []
+exclude = ["build", "dist", ".venv"]
+
+[tool.mypy]
+python_version = "3.11"
+ignore_missing_imports = true
+warn_unused_ignores = true
+warn_redundant_casts = true
+warn_unused_configs = true
+exclude = "tests"


---

参考：動かない場合の最小調整ガイド

import パスが異なるとき

from app.db.engine import get_session → あなたのプロジェクトで AsyncSession 依存を返す関数/Provider に置換

from app.db import queries → データアクセス層の実ファイルに合わせる

from app.services.upsert import df_to_rows, upsert_prices_sql → 実在するユーティリティ名に合わせる


Pydantic v1 利用時

field_validator を validator に置換（パッチ内フォールバックで原則不要）


ログ出力の JSON 化

既に core/logging.py が JSON ハンドラを設定している場合はそのまま logger.info(...) で構造化されます。


get_prices_resolved 関数名／SQL の差異

関数名や引数が異なる場合、app/db/queries.py の該当箇所で SQL 文を合わせてください。




---

実施順の推奨

1. PR#1（Migrations 統一）


2. PR#2（/prices バリデーション）


3. PR#3（UTC/Check 制約）


4. PR#4（ギャップ検出 & リフレッシュ）


5. PR#5（Fetcher 耐性）


6. PR#6（セキュリティ & CORS）


7. PR#7（観測性 & CI）




---


