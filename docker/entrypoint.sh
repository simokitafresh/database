#!/usr/bin/env bash
set -euo pipefail

# 環境変数設定（シンプル）
export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL:-${DATABASE_URL}}"

# URLドライバー変換（asyncpg → psycopg）
if [[ "$ALEMBIC_DATABASE_URL" == *"asyncpg"* ]]; then
    export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL//asyncpg/psycopg}"
fi

echo "[entrypoint] Running migrations..."
alembic upgrade head || {
    echo "[entrypoint] Migration failed, attempting stamp..."
    alembic stamp head
}

echo "[entrypoint] Starting server..."
exec gunicorn app.main:app \
    --workers="${WEB_CONCURRENCY:-2}" \
    --worker-class=uvicorn.workers.UvicornWorker \
    --bind="0.0.0.0:${PORT:-8000}" \
    --timeout="${GUNICORN_TIMEOUT:-60}"
