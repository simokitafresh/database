# 調整済OHLCV API (MVP)

このリポジトリは、調整済み株価を提供する FastAPI ベースのサービスです。

## ローカル環境での実行

1. 依存関係をインストールします。
   ```bash
   make install
   ```
2. テストを実行します。
   ```bash
   make test
   ```

## アプリケーションの起動

1. 必要に応じて CORS を許可する Origin を設定します。
   例: 任意のオリジンを許可する場合
   ```bash
   export CORS_ALLOW_ORIGINS="*"
   ```
2. アプリを起動します。
   ```bash
   python -m uvicorn app.main:app
   ```

### マイグレーションの実行

Alembic は `ALEMBIC_DATABASE_URL` を優先し、無ければ `DATABASE_URL` を使用します。
`DATABASE_URL` が `postgresql+asyncpg://` の場合でも、Alembic 側で `postgresql+psycopg://` に
変換して Postgres に接続します。Docker 環境ではエントリポイントがこれらの変数から
URL を解決し、`alembic upgrade head` を実行します。

## テスト方針

- **テストはネットワークモック** を用いて行い、外部への実通信は発生させません。

## ライセンス

MIT License
