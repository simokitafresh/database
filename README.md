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

### マイグレーションの実行

Alembic は環境変数 `ALEMBIC_DATABASE_URL` もしくは `DATABASE_URL` を参照して
Postgres に接続します。Docker 環境ではエントリポイントがこれらの変数から
URL を解決し、`alembic upgrade head` を実行します。

## テスト方針

- **テストはネットワークモック** を用いて行い、外部への実通信は発生させません。

## ライセンス

MIT License
