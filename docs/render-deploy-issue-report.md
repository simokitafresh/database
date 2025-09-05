# Renderデプロイエラー調査報告書

## 1. エラー概要

### 1.1 症状
- **発生環境**: Render (Web Service, Docker環境)
- **エラー内容**: Gunicornが正常起動後、約1分後にSIGTERMシグナルを受信してシャットダウン
- **ブラウザアクセス結果**: "Not Found"エラー
- **エラーログ**:
```
[2025-08-31 04:36:46 +0000] [1] [INFO] Handling signal: term
[2025-08-31 04:36:46 +0000] [26] [INFO] Shutting down
[2025-08-31 04:36:46 +0000] [26] [INFO] Error while closing socket [Errno 9] Bad file descriptor
[2025-08-31 04:36:46 +0000] [26] [INFO] Waiting for application shutdown.
[2025-08-31 04:36:46 +0000] [26] [INFO] Application shutdown complete.
[2025-08-31 04:36:46 +0000] [26] [INFO] Finished server process [26]
[2025-08-31 04:36:46 +0000] [1] [ERROR] Worker (pid:26) was sent SIGTERM!
[2025-08-31 04:36:46 +0000] [1] [INFO] Shutting down: Master
==> Detected service running on port 10000
==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
```

### 1.2 プロジェクト構成
- **フレームワーク**: FastAPI + Uvicorn + Gunicorn
- **データベース**: PostgreSQL (Supabase)
- **マイグレーション**: Alembic
- **デプロイ方式**: Docker (docker/Dockerfile + docker/entrypoint.sh)

## 2. 調査で判明した事実

### 2.1 Render環境変数設定

#### 表示されている環境変数
| キー | 値 | 備考 |
|------|-----|------|
| DATABASE_URL | postgresql+asyncpg://... | Supabase接続文字列（アプリ用） |
| ALEMBIC_DATABASE_URL | postgresql+psycopg://... | マイグレーション用 |
| API_MAX_ROWS | 5000 | |
| API_MAX_SYMBOLS | 3 | |
| APP_ENV | production | |
| CORS_ALLOW_ORIGINS | * | |
| FETCH_BACKOFF_MAX_SECONDS | 8.0 | |
| FETCH_MAX_RETRIES | 3 | |
| FETCH_TIMEOUT_SECONDS | 10 | |
| GUNICORN_TIMEOUT | 120 | |
| LOG_LEVEL | INFO | |
| REQUEST_TIMEOUT_SECONDS | 20 | |
| WEB_CONCURRENCY | 1 | |
| YF_REFETCH_DAYS | 30 | |
| YF_REQ_CONCURRENCY | 1 | |

#### 重要な未設定項目
- **PORT環境変数**: UIには表示されていない（RenderのDocker環境では自動設定されるはずだが、内部的に10000が設定されている模様）

### 2.2 Render設定画面の内容

| 設定項目 | 設定値 | 備考 |
|---------|--------|------|
| Dockerfile Path | docker/Dockerfile | 正しい |
| Docker Build Context Directory | $ | UIでは$と表示されるがRenderの仕様で実際は`.`（正しい） |
| Docker Command | （空欄） | Dockerfileの設定を使用（正しい） |
| Pre-Deploy Command | $ | UIでは$と表示される |
| Registry Credential | No credential | |
| Auto-Deploy | On Commit | |
| Health Check Path | /healthz | 正しく設定済み |
| Service Notifications | Use workspace default (Only failure notifications) | |
| Preview Environment Notifications | Use account default (Disabled) | |
| Maintenance Mode | Disabled | |

### 2.3 コード内容

#### docker/entrypoint.sh（現状）
```bash
#!/usr/bin/env bash
set -euo pipefail

# 必要なら: wait-for-it/wait-for-postgres などで DB 起動を待つ
# 例) until pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER"; do sleep 1; done

export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL:-${DATABASE_URL:-}}"
if [ -z "${ALEMBIC_DATABASE_URL:-}" ]; then
  echo "[entrypoint] ERROR: DATABASE_URL or ALEMBIC_DATABASE_URL is not set" >&2
  exit 1
fi

echo "[entrypoint] Running migrations against ${ALEMBIC_DATABASE_URL}"
alembic upgrade head

echo "[entrypoint] Starting gunicorn (UvicornWorker)"
exec gunicorn app.main:app \
  --workers="${WEB_CONCURRENCY:-2}" \
  --worker-class=uvicorn.workers.UvicornWorker \
  --bind="0.0.0.0:${PORT:-8000}" \
  --timeout="${GUNICORN_TIMEOUT:-120}"
```

#### docker/Dockerfile（抜粋）
```dockerfile
EXPOSE 8000
ENTRYPOINT ["./docker/entrypoint.sh"]
```

## 3. 問題の分析（更新版）

### 3.1 直接的な原因
アプリケーションは正常に起動するが、Renderが約1分後（初回ヘルスチェックのタイムアウト）にSIGTERMを送信してシャットダウンしている。

### 3.2 根本原因の分析

#### 判明した事実
1. **データベース接続: ✅ 成功**
   - マイグレーションは正常に実行された
   - PostgreSQL接続は問題なし

2. **アプリケーション起動: ✅ 成功**
   - Gunicornがポート10000で正常に起動
   - FastAPIアプリケーションの起動完了

3. **ヘルスチェック: ❌ 失敗の可能性大**
   - `/healthz`エンドポイントは実装されている
   - しかし何らかの理由でアクセスできていない

#### 最も可能性が高い原因: ルーティングの問題

**コード分析**:
```python
# app/main.py
app.include_router(health_router)  # /healthz を直接登録
app.include_router(v1_router)      # /v1/* を登録
```

```python
# app/api/v1/health.py
@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

**問題の可能性**:
1. health_routerのインポートが間違っている
2. health_routerが`v1`ディレクトリにあるが、prefixなしで登録されている
3. 実際のパスが`/v1/healthz`になっている可能性

### 3.3 緊急の確認事項
- `app/api/v1/health.py`のrouterがどのように定義されているか
- `app/main.py`でhealth_routerをどこからインポートしているか
- 実際のヘルスチェックエンドポイントのパスが`/healthz`なのか`/v1/healthz`なのか

### 3.3 Renderのポート処理の特殊性
- RenderのDocker環境では、PORT環境変数は自動的に設定される（通常10000）
- この値はUI上の環境変数リストには表示されない
- アプリケーションはこのPORT環境変数を使用してバインドする必要がある

## 4. 提案された修正内容

### 4.1 entrypoint.shの改善
- デバッグ情報の追加
- エラーハンドリングの強化
- DB接続エラーの詳細表示

### 4.2 app/migrations/env.pyの改善
- SSL設定の自動追加（Supabase接続の場合）
- 接続タイムアウトの設定
- エラー情報の詳細表示

### 4.3 環境変数の追加
- PORT=10000を明示的に設定（テスト目的）

## 5. 追加調査が必要な項目

### 5.1 ログの詳細確認
- **ビルドログ**:
  - "Using Dockerfile at docker/Dockerfile"のメッセージ確認
  - Dockerビルドの成功/失敗
  - ビルド時間

- **ランタイムログ**:
  - alembic upgrade headの実行結果
  - データベース接続の成功/失敗
  - 具体的なエラーメッセージ

### 5.2 ヘルスチェック設定
- **確認済み**: Renderのヘルスチェックパスは`/healthz`に正しく設定されている
- ヘルスチェックのタイムアウト設定（デフォルト値使用中）
- **ヘルスチェックの実装内容**:
  ```python
  # app/api/v1/health.py
  @router.get("/healthz")
  async def healthz() -> dict[str, str]:
      """Health check endpoint returning a simple OK response."""
      return {"status": "ok"}
  ```
  - 現状はシンプルな実装でDB接続チェックは含まれていない
  - これはDB接続エラーがあってもヘルスチェック自体は成功することを意味する

### 5.3 ネットワーク設定
- SupabaseのIPアドレス制限
- SSL/TLS設定の要件

## 11. 解決策の提案

### 11.1 即座に実施すべき修正

#### オプション1: ルートパスにヘルスチェックを追加
**app/main.py**に以下を追加：
```python
@app.get("/")
async def root():
    return {"status": "ok", "service": "Stock OHLCV API"}
```

#### オプション2: ヘルスチェックパスの再確認と修正
1. Renderの設定で`Health Check Path`を`/`に変更（一時的に）
2. または、health_routerの登録を確認：

**app/api/v1/router.py**を修正：
```python
from fastapi import APIRouter
from .health import router as health_router  # 追加
from .metrics import router as metrics_router
from .prices import router as prices_router
from .symbols import router as symbols_router

router = APIRouter(prefix="/v1")
router.include_router(symbols_router)
router.include_router(prices_router)
router.include_router(metrics_router)
# health_routerは含めない（main.pyで直接登録）
```

### 11.2 デバッグのための一時的な修正

**app/main.py**を以下のように修正してログを追加：
```python
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 起動時にルート一覧を出力
@app.on_event("startup")
async def startup_event():
    routes = []
    for route in app.routes:
        if hasattr(route, "path"):
            routes.append(f"{route.methods} {route.path}")
    logger.info(f"Available routes: {routes}")
```

### 11.3 最も簡単な解決策

**Renderの設定変更**:
1. Settings → Health Check Path を `/healthz` から `/v1/health` に変更してみる
2. それでも失敗する場合は、Health Check Pathを空欄にして無効化（一時的に）

### 11.4 根本的な解決

**docker/entrypoint.sh**にヘルスチェックのテストを追加：
```bash
echo "[entrypoint] Testing health endpoint..."
sleep 5  # アプリケーション起動待ち
curl -f http://localhost:${PORT:-8000}/healthz || echo "[entrypoint] WARNING: Health check failed"
```

## 7. 関連ファイル一覧

- `docker/entrypoint.sh` - 起動スクリプト
- `docker/Dockerfile` - Dockerイメージ定義
- `app/migrations/env.py` - Alembic設定
- `app/main.py` - FastAPIアプリケーション
- `app/core/config.py` - 環境変数設定
- `app/db/engine.py` - データベースエンジン設定
- `app/api/deps.py` - 依存性注入（DB接続）
- `.env.render.example` - Render用環境変数サンプル

## 8. 参考情報

- プロジェクトはPython 3.12、FastAPI、PostgreSQL (Supabase)を使用
- Alembicによるマイグレーション管理
- yfinanceを使用した株価データ取得システム
- 1ホップのシンボル変更透過解決機能を実装
- 直近N日（デフォルト30日）のデータ再取得機能

## 10. 最新のログ分析（重要な発見）

### 10.1 デプロイログの詳細
```
[entrypoint] Running migrations against postgresql+psycopg://...
INFO: Context impl PostgresqlImpl.
INFO: Will assume transactional DDL.
[entrypoint] Starting gunicorn (UvicornWorker)
[2025-08-31 04:35:38 +0000] [1] [INFO] Starting gunicorn 21.2.0
[2025-08-31 04:35:38 +0000] [1] [INFO] Listening at: http://0.0.0.0:10000 (1)
[2025-08-31 04:35:38 +0000] [1] [INFO] Using worker: uvicorn.workers.UvicornWorker
[2025-08-31 04:35:38 +0000] [26] [INFO] Booting worker with pid: 26
[2025-08-31 04:35:41 +0000] [26] [INFO] Started server process [26]
[2025-08-31 04:35:41 +0000] [26] [INFO] Waiting for application startup.
[2025-08-31 04:35:41 +0000] [26] [INFO] Application startup complete.
==> Your service is live 🎉
==> Available at your primary URL https://stockdata-api-6xok.onrender.com
[2025-08-31 04:36:46 +0000] [1] [INFO] Handling signal: term （← 起動から約1分後）
```

### 10.2 判明した事実

1. **マイグレーション: ✅ 成功**
   - PostgreSQL接続成功
   - トランザクショナルDDL実行
   - エラーメッセージなし

2. **アプリケーション起動: ✅ 成功**
   - Gunicornがポート10000で正常にリッスン
   - UvicornWorkerが起動
   - Application startup complete
   - サービスがライブ状態になった

3. **問題発生: ❌ 起動から約65秒後**
   - 04:35:41: 起動完了
   - 04:36:46: SIGTERM受信（65秒後）
   - Renderがサービスを不健全と判断してシャットダウン

4. **ブラウザアクセス: ❌ "Not Found"**
   - URLにアクセスすると404エラー

### 10.3 問題の真の原因

**ルートパス（/）が実装されていないことが原因**

- Renderのヘルスチェックは`/healthz`に設定されているが、初回のヘルスチェックが失敗している
- アプリケーションのルーティング設定を確認：
  - `/healthz` - health_router
  - `/v1/*` - v1_router
  - `/` - **実装なし（404）**

Renderが初回ヘルスチェックを実行しているが、何らかの理由で失敗し、約1分のタイムアウト後にサービスをシャットダウンしている可能性が高い。