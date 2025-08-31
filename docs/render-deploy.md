# 🚀 Render デプロイガイド（2025年8月版）

最終更新: 2025-08-31 / 対象プラン: Render Starter Plan（$7/月, 512MB RAM, 0.5 CPU）

調整済OHLCV API を 5 分でデプロイするための実践ガイドです。render.yaml は使わず GUI で設定します。環境変数は Render の「Add from .env」で一括インポートできます。

---

## ✅ 前提条件チェックリスト
- GitHub リポジトリ準備済み
- Render アカウント作成済み（Starter Plan）
- Supabase プロジェクト作成済み（接続情報を取得済み）
- ローカルで `/healthz` が 200（任意）

---

## 🎯 クイックスタート（5 分）

### Step 1: .env.render を用意（1 分）
Render の Environment へ一括インポートするため、ルートに `.env.render` を用意します（テンプレは本リポジトリに同梱）。Starter 最適化の例:

```
# 基本
APP_ENV=production

# Supabase（Supavisor）
# アプリ（非同期 / Transaction mode: 6543）
DATABASE_URL=postgresql+asyncpg://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@[YOUR-POOLER-HOST]:6543/postgres
# Alembic（同期 / Session mode: 5432）
ALEMBIC_DATABASE_URL=postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@[YOUR-POOLER-HOST]:5432/postgres?sslmode=require

# Starter Plan 最適化（512MB / 0.5 CPU）
WEB_CONCURRENCY=1
API_MAX_SYMBOLS=3
API_MAX_ROWS=5000
YF_REQ_CONCURRENCY=1
FETCH_TIMEOUT_SECONDS=10
FETCH_MAX_RETRIES=3
FETCH_BACKOFF_MAX_SECONDS=8.0
REQUEST_TIMEOUT_SECONDS=20
YF_REFETCH_DAYS=30
CORS_ALLOW_ORIGINS=*
LOG_LEVEL=INFO
GUNICORN_TIMEOUT=120
# Render は PORT を提供。手動設定は不要（ローカル用途のみ 8000 を使用可）
```

置換ポイント:
- `[YOUR-PROJECT-REF]`（Supabase Project Ref）
- `[YOUR-PASSWORD]`（DB パスワード）
- `[YOUR-POOLER-HOST]`（例: `aws-*-ap-northeast-1.pooler.supabase.com`。Connect 画面の接続文字列に記載）

### Step 2: Web Service を作成（2 分）
1. Render ダッシュボード → New → Web Service
2. リポジトリ/ブランチ（main/master）を選択
3. 設定
   - Name: `stock-ohlcv-api`
   - Region: DB に近い（例: Singapore）
   - Instance Type: Starter
   - Environment: Docker（自動認識）
   - Health Check Path: `/healthz`
   - Build/Start Command: 空欄（Dockerfile/ENTRYPOINT を利用）

### Step 3: 環境変数を一括インポート（1 分）
1. Environment タブ → “Add from .env”
2. `.env.render` の内容を貼り付け → Add variables

### Step 4: デプロイ開始（1 分）
Manual Deploy → Deploy latest commit。ログで以下を確認:
```
[entrypoint] Running migrations against ...
[entrypoint] Starting gunicorn (UvicornWorker)
Listening at: http://0.0.0.0:${PORT}
```

### Step 5: 動作確認（30 秒）
公開 URL（`https://<your-app>.onrender.com`）で確認:
- `/healthz` → 200
- `/v1/symbols` → 初回は空 or 既存シード
- `/v1/prices?symbols=AAPL&from=2024-01-01&to=2024-01-07` → 初回は 10–20 秒

---

## 📊 詳細設定ガイド

### Supabase（Supavisor）接続モード（2025/08 現在）
| モード | ポート | 用途 | 特徴 |
|--------|--------|------|------|
| Transaction | 6543 | アプリ（asyncpg） | サーバレス/短時間接続向け、prepared statement 非対応 |
| Session     | 5432 | Alembic（psycopg）| 永続接続向け、prepared statement 対応 |

Project Ref は Supabase → Settings → Database → Connection string で確認できます。

### Starter Plan 最適化のポイント
- メモリ（512MB）
  - `WEB_CONCURRENCY=1`, `API_MAX_SYMBOLS=1..3`, `API_MAX_ROWS=1000..5000`
- CPU（0.5 CPU）
  - `YF_REQ_CONCURRENCY=1`
  - タイムアウトを延長（`FETCH_TIMEOUT_SECONDS=10-20`, `REQUEST_TIMEOUT_SECONDS=20-30`）
- 外部 I/O（yfinance）
  - レート制限/ネットワーク品質の影響を受けるため、`FETCH_MAX_RETRIES` と `FETCH_BACKOFF_MAX_SECONDS` を適宜調整

---

## 実装に沿った接続の注意
- Alembic（同期）
  - 同期ドライバで接続（`postgresql://` or `postgresql+psycopg://`）
  - `app/migrations/env.py` が DSN を自動正規化（`postgresql(+asyncpg)`/`postgres` → `postgresql+psycopg`）し、`%` は `%%` へエスケープして ConfigParser 補間を回避
- アプリ（非同期）
  - `DATABASE_URL` は `postgresql+asyncpg://...` を推奨
  - PgBouncer(transaction/statement) 対策はコードで適用（prepared statement キャッシュ無効化・動的名称・`NullPool`・DSN 正規化）

---

## 🔧 トラブルシューティング
- マイグレーション失敗: 同期/非同期 DSN の取り違い → `ALEMBIC_DATABASE_URL` を `postgresql+psycopg://...` に
- 価格が空: 期間を短く/銘柄を変えて再試行。`LOG_LEVEL=DEBUG` で coverage/fetch window/UPSERT のログを確認
- CORS: 本番は `CORS_ALLOW_ORIGINS` にオリジンを明示（`*` は避ける）

---

## 参考
- エントリポイント: `docker/entrypoint.sh`
- Dockerfile: `docker/Dockerfile`
- Alembic: `alembic.ini`, `app/migrations/env.py`
- 実装補足: `docs/implementation-notes.md`
