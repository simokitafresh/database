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

