#!/usr/bin/env bash
set -euo pipefail

# 環境変数設定（シンプル）
export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL:-${DATABASE_URL}}"

# URLドライバー変換（asyncpg → psycopg）
if [[ "$ALEMBIC_DATABASE_URL" == *"asyncpg"* ]]; then
    export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL//asyncpg/psycopg}"
fi

# Supabase Pooler用: sslmode=requireを追加（なければ）
if [[ "$ALEMBIC_DATABASE_URL" == *"supabase"* ]] && [[ "$ALEMBIC_DATABASE_URL" != *"sslmode="* ]]; then
    if [[ "$ALEMBIC_DATABASE_URL" == *"?"* ]]; then
        export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL}&sslmode=require"
    else
        export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL}?sslmode=require"
    fi
fi

echo "[entrypoint] Running migrations..."
# リトライ付きマイグレーション実行
MAX_RETRIES=3
RETRY_DELAY=5

for i in $(seq 1 $MAX_RETRIES); do
    if alembic upgrade head; then
        echo "[entrypoint] Migration completed successfully"
        break
    else
        if [ $i -eq $MAX_RETRIES ]; then
            echo "[entrypoint] Migration failed after $MAX_RETRIES attempts, attempting stamp..."
            alembic stamp head || echo "[entrypoint] Stamp also failed, continuing anyway..."
        else
            echo "[entrypoint] Migration attempt $i failed, retrying in ${RETRY_DELAY}s..."
            sleep $RETRY_DELAY
            RETRY_DELAY=$((RETRY_DELAY * 2))
        fi
    fi
done

echo "[entrypoint] Starting server..."
exec gunicorn app.main:app \
    --workers="${WEB_CONCURRENCY:-2}" \
    --worker-class=uvicorn.workers.UvicornWorker \
    --bind="0.0.0.0:${PORT:-8000}" \
    --timeout="${GUNICORN_TIMEOUT:-60}"
