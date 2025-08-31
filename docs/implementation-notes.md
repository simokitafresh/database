# 実装準拠メモ（接続/取得/ログ）

この文書は、現行コードの挙動を実運用観点で補足するものです。設計仕様は `architecture.md` を正本とし、本書は差分・実装準拠の注意点をまとめます。

## 接続と DSN

- 環境変数の役割
  - `DATABASE_URL`: アプリ実行用（非同期）DSN。`postgresql+asyncpg://` を推奨
  - `ALEMBIC_DATABASE_URL`: マイグレーション用（同期）DSN。`postgresql://` または `postgresql+psycopg://`
  - 未設定時は Alembic 実行時に `DATABASE_URL` を同期ドライバに変換して使用
- Alembic の `%` 補間回避
  - `app/migrations/env.py` は URL 内の `%` を `%%` にエスケープしてから `sqlalchemy.url` を設定（ConfigParser による補間の誤解釈を防止）
- asyncpg + PgBouncer(transaction/statement) 対策
  - 準備済みステートメントのキャッシュ無効化（statement cache を 0）
  - 動的名称（UUID）を付与して名称衝突を回避
  - アプリ側コネクションプールは `NullPool` を使用（PgBouncer のプールを前提）
  - `?sslmode=require` は asyncpg へは渡さず、DSN 正規化のうえ必要時に `connect_args['ssl']=True` を設定

## /v1/prices のオンデマンド取得（実装詳細）

- 1 シンボル = 1 トランザクション
  - `pg_advisory_xact_lock(hashtext(symbol))` で排他 → カバレッジ判定 → 取得 → UPSERT → コミット
- 取得ウィンドウの決定
  - `last_date` があれば `max(from, last_date - YF_REFETCH_DAYS)` を考慮
  - 平日ギャップが見つかれば `first_missing_weekday` を起点に統合して最小の開始日を決定
- yfinance の利用
  - 基本は `yf.download(..., auto_adjust=True)`
  - 空/列不足時は `yf.Ticker(symbol).history(...)` でフォールバック
  - `end` は排他的なため、内部で +1 日して包含

## ログ

- `.env` の `LOG_LEVEL` がルートロガーに適用（既定 `INFO`）
- `DEBUG` では以下を出力
  - coverage result（first/last/cnt/has_gaps/first_missing_weekday）
  - fetch window decided（start/end）
  - upserted rows（n_rows）
  - yfinance fallback 実行の有無

## 依存の最小化と Windows のヒント

- ランタイム依存（抜粋）: `fastapi`, `uvicorn`（extras なし）, `sqlalchemy`（extras なし）, `asyncpg`, `psycopg[binary]`, `alembic`, `pandas`, `numpy`
- Windows で `pandas`/`numpy` のビルドに失敗する場合
  - ホイールを優先: `PIP_ONLY_BINARY='pandas,numpy'`
  - もしくは先に `pip install --only-binary=:all: pandas numpy`

## リンク

- 仕様・DDL・運用: `architecture.md`
- マイグレーション補足: `docs/app-migrations-fix.md`
- DB 接続補足: `docs/app-db-fix.md`
