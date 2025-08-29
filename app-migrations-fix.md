

---

目的（ゴール）

Alembic の実行先を 常に PostgreSQL にする

Alembic が 環境変数の URL を読む（SQLite 既定を使わない）

CI と Docker で マイグレーションの up/down を検証できるようにする



---

修正タスクリスト（Codex へそのまま渡せます）

> 進捗用チェックボックス [ ] を付けています。各タスクは「開始条件 → 作業 → 検証（DoD）」の順で、テスト可能で単一関心です。



1) 依存の追加（Alembic を Postgres 同期ドライバで動かす）

[x] psycopg を requirements に追加
開始条件: 依存の追加作業に入れる
作業: requirements.txt に 1 行追加（ピン留めポリシーは既存に準拠）

# requirements.txt
+ psycopg[binary]==3.2.*

検証（DoD）: pip install -r requirements.txt が成功し、python -c "import psycopg" がゼロ終了。



---

2) Alembic が環境変数から URL を読むようにする（かつ asyncpg → psycopg を自動変換）

[x] app/migrations/env.py に環境変数注入を実装
開始条件: env.py を編集できる
作業: 下記パッチを適用（ALEMBIC_DATABASE_URL を優先、無ければ DATABASE_URL。postgresql+asyncpg:// は Alembic 用に postgresql+psycopg:// へ置換）

# app/migrations/env.py
+import os
 from logging.config import fileConfig
 from sqlalchemy import engine_from_config, pool
 from alembic import context
 from app.db.base import Base

 config = context.config
+# --- inject DB URL from env (prefer ALEMBIC_DATABASE_URL, fallback to DATABASE_URL) ---
+env_url = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
+if env_url:
+    if env_url.startswith("postgresql+asyncpg://"):
+        env_url = env_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
+    config.set_main_option("sqlalchemy.url", env_url)

 if config.config_file_name is not None:
     fileConfig(config.config_file_name)
 target_metadata = Base.metadata

検証（DoD）:

ALEMBIC_DATABASE_URL=postgresql+psycopg://... alembic current が成功

DATABASE_URL=postgresql+asyncpg://... alembic current でも成功（内部で psycopg に置換）。
根拠：現状 env.py は ini の URL をそのまま使用しているため要修正。




---

3) SQLite 既定を使わないよう安全化（操作ミス防止）

[x] alembic.ini の SQLite 既定 URL をコメントアウト or ダミー化
開始条件: alembic.ini を編集できる
作業: 下記いずれか

[alembic]
 script_location = app/migrations
-sqlalchemy.url = sqlite:///./app.db
+# sqlalchemy.url is injected from env by env.py
+# sqlalchemy.url =

検証（DoD）: 環境変数未設定で alembic current を実行すると Postgres ではなく 失敗 or 明示エラーになる（誤って SQLite で走らない）。



---

4) Docker/Compose で Alembic に psycopg URL を渡す

[x] docker-compose.yml に ALEMBIC_DATABASE_URL を追加
開始条件: Compose を編集できる
作業: API サービスの環境変数に追加（アプリは asyncpg、Alembic は psycopg を利用）

services:
   api:
     environment:

DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/postgres


DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/postgres

ALEMBIC_DATABASE_URL: postgresql+psycopg://postgres:postgres@postgres:5432/postgres

**検証（DoD）**: `docker compose up` で API 起動前に `alembic upgrade head` が Postgres に対して成功（entrypoint は既に `alembic upgrade head` 実行）。Compose は Postgres にヘルスチェックあり。4



---

5) Makefile にワンコマンド・マイグレーションを追加

[x] make migrate 追加（ローカル検証容易化）
開始条件: Makefile 変更可能
作業:

.PHONY: install test format
 install:
     pip install -r requirements.txt
     pip install --upgrade yfinance
 test:
     PYTHONPATH=. pytest -q
 format:
     black .
+migrate:
+    ALEMBIC_DATABASE_URL?=postgresql+psycopg://postgres:postgres@localhost:5432/postgres
+    alembic upgrade head

検証（DoD）: ALEMBIC_DATABASE_URL=postgresql+psycopg://... make migrate が成功。



---

6) CI で up/down を検証（回帰を防止）

[x] GitHub Actions に Postgres サービス＋ Alembic up/down を追加
開始条件: .github/workflows/ci.yml を編集できる
作業: 下記のように Postgres サービス、クライアント導入、alembic upgrade/downgrade を追加

jobs:
   build:
     runs-on: ubuntu-latest
+    services:
+      postgres:
+        image: postgres:16
+        env:
+          POSTGRES_USER: postgres
+          POSTGRES_PASSWORD: postgres
+          POSTGRES_DB: postgres
+        options: >-
+          --health-cmd="pg_isready -U postgres -d postgres -h 127.0.0.1"
+          --health-interval=5s --health-timeout=5s --health-retries=20
     steps:
       - uses: actions/checkout@v4
       - uses: actions/setup-python@v5
         with:
           python-version: "3.11"
       - name: Install deps
         run: |
           python -m pip install --upgrade pip
           pip install -r requirements.txt
           pip install ruff black mypy
+        - name: Install PostgreSQL client
+          run: sudo apt-get update && sudo apt-get install -y postgresql-client
+        - name: Alembic upgrade (Postgres)
+          env:
+            ALEMBIC_DATABASE_URL: postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres
+          run: alembic upgrade head
+        - name: Alembic downgrade (Postgres)
+          env:
+            ALEMBIC_DATABASE_URL: postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres
+          run: alembic downgrade base
       - name: Lint (ruff)
         run: ruff check .
       - name: Format (black --check)
         run: black --check .
       - name: Type check (mypy)
         run: mypy app || true
       - name: Tests
         env:
           PYTHONPATH: .
         run: pytest -q

検証（DoD）: CI がグリーン。Alembic の 昇順/降順が CI で実際に実行される。



---

7) ドキュメント整合（実装に合わせる）

[x] README のマイグレーション節を実装どおりに微修正
開始条件: README 編集可
作業: 「Alembic は ALEMBIC_DATABASE_URL 優先、無ければ DATABASE_URL を使用。DATABASE_URL が asyncpg の場合は Alembic 側で psycopg に変換。」の 1 文を追記。
検証（DoD）: 新しい手順どおりに ALEMBIC_DATABASE_URL=... alembic upgrade head が成功。



---

変更不要（確認のみ）

versions/002_fn_prices_resolved.py: PostgreSQL の SQL 関数（timestamptz を含む） → Postgres 前提でそのまま使用。

versions/003_add_price_checks.py: LEAST/GREATEST を用いた CHECK 制約 → Postgres 前提でそのまま使用。

初期スキーマ 001_init.py は Postgres で動作可能（TIMESTAMP WITH TIME ZONE 相当）。



---

スモークテスト（手元検証用・すべて可視化可能）

1. ローカル Postgres で up/down

export ALEMBIC_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/postgres'
alembic upgrade head
alembic downgrade base


2. Compose で自動適用の確認

docker compose up --build
# API 起動前に 'alembic upgrade head' が走り、/healthz が 200 を返す想定


3. CI で up/down が通ることを PR で確認




---

クリティカル不具合の根本（再掲・統一後は解消）

SQLite URL が既定（alembic.ini）＋env.py が URL を ini から直読み → Alembic が SQLite で動こうとする。

ただし マイグレーション内容は Postgres 前提（SQL 関数、LEAST/GREATEST）→ SQLite では実行不能。

psycopg（同期ドライバ）が未導入 → Alembic が Postgres に同期接続できない。

Docker/entrypoint は無条件で Alembic 実行だが、Compose では API 用に DATABASE_URL=postgresql+asyncpg のみ渡しており、Alembic 向け URL が不足。



---

補足（設計メモ）

アプリ本体は引き続き asyncpg（非同期）を利用、Alembic は psycopg（同期）を使う二刀流にします。SQLAlchemy 2.0 の標準的運用で、責務分離が明確です。app/db/engine.py は既に async engine を想定済み。



---


