# 調整済OHLCV API (MVP)

Yahoo Finance 由来の調整済み株価（OHLCV）をPostgreSQLへ保存し、FastAPIで提供するAPI。1ホップのシンボル変更（例: FB→META）を透過的に解決し、直近N日（既定30）の再取得で分割/配当の遅延反映にも対応します。

- エンドポイント: `/healthz`, `/v1/symbols`, `/v1/prices`, `/v1/metrics`
- 仕様・DDL: `architecture.md`
- マイグレーション: Alembic（起動時に `alembic upgrade head` 実行）
- デプロイ: Docker + Render

## クイックスタート（ローカル）

前提: Python 3.11+ / PostgreSQL

1) 取得・セットアップ

```bash
git clone <your-repo-url>
cd database
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
pip install -r requirements.txt
```

2) 環境変数ファイル

- `.env.example` を参考に `.env` を作成してください（機密はコミットしない）。
- 主要キー
  - `DATABASE_URL`: `postgresql+asyncpg://user:pass@host:5432/db`
  - `ALEMBIC_DATABASE_URL`: `postgresql+psycopg://user:pass@host:5432/db`（未設定時は `DATABASE_URL` を使用）
  - `API_MAX_SYMBOLS` / `API_MAX_ROWS` / `YF_REFETCH_DAYS` / `YF_REQ_CONCURRENCY`
  - `CORS_ALLOW_ORIGINS`（`,` 区切り or `*`。`*` の場合は資格情報が無効）
  - `LOG_LEVEL`, `WEB_CONCURRENCY`, `GUNICORN_TIMEOUT`, `PORT`

3) DBとマイグレーション

```bash
# 例: DockerのPostgresを使う場合（任意）
# docker-compose up -d postgres

alembic upgrade head
```

4) 起動

```bash
uvicorn app.main:app --reload
# http://localhost:8000/healthz
```

## API の使い方（例）

- ヘルス: `GET /healthz`
- シンボル: `GET /v1/symbols?active=true`
- 価格: `GET /v1/prices?symbols=AAPL,MSFT&from=2024-01-01&to=2024-01-31`
- メトリクス: `GET /v1/metrics?symbols=AAPL,MSFT&from=2024-01-01&to=2024-01-31`

## Render へのデプロイ

- `render.yaml` を利用。サービスは `docker/entrypoint.sh` から起動し、開始時に自動で `alembic upgrade head` を実行します。
- Render ダッシュボードで環境変数を設定（`DATABASE_URL` は `sync: false`）。
- `.env.render.example` に推奨値サンプルを用意（シークレットはリポジトリに置かない）。
- 注意点
  - `app/migrations/env.py` が `postgresql+asyncpg://` を `postgresql+psycopg://` に自動置換するため、`DATABASE_URL` のみでもマイグレーションは動作します。
  - 本番で `CORS_ALLOW_ORIGINS=*` は避け、必要なオリジンを列挙してください。

## 開発（テスト/品質）

- テスト実行: `pytest`
- Lint: `ruff check .` / 自動修正 `ruff check . --fix`
- フォーマット: `black .`
- 型チェック: `mypy app`

## 管理CLI（Typer）

```bash
# シンボル追加（正規化後に追加。重複時はメッセージ表示）
python -m app.management.cli add-symbol AAPL

# シンボル検証（正規化の動作確認）
python -m app.management.cli verify-symbol TSLA
```

## プロジェクト構成

```
app/
  api/v1/         # ルータ（/v1/*）
  core/           # 設定・CORS・ロギング・ミドルウェア
  db/             # モデル・クエリ・ユーティリティ
  migrations/     # Alembic スクリプト
  schemas/        # Pydantic モデル
  services/       # fetcher/metrics/normalize/resolver/upsert
  management/     # Typer CLI
```

## 環境変数（主なもの）

- DATABASE_URL: アプリ実行用（asyncpg）
- ALEMBIC_DATABASE_URL: マイグレーション用（psycopg）。未設定時は DATABASE_URL を自動流用
- API_MAX_SYMBOLS: 1リクエストの最大シンボル数
- API_MAX_ROWS: レスポンス最大行数
- YF_REFETCH_DAYS: 直近再取得日数（既定30）
- YF_REQ_CONCURRENCY: Fetch並列数
- CORS_ALLOW_ORIGINS: 許可オリジン（`,` 区切り／`*`）
- LOG_LEVEL, WEB_CONCURRENCY, GUNICORN_TIMEOUT, PORT

## ライセンス

MIT License

## 参考

- 仕様/DDL/運用: `architecture.md`
- Render 設定: `render.yaml` / `docker/entrypoint.sh`
- 主要テスト: `tests/unit/*`（API・services・migrations など）

