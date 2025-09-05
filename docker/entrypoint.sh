#!/usr/bin/env bash
set -euo pipefail

export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL:-${DATABASE_URL:-}}"
if [ -z "${ALEMBIC_DATABASE_URL:-}" ]; then
  echo "[entrypoint] ERROR: DATABASE_URL or ALEMBIC_DATABASE_URL is not set" >&2
  exit 1
fi

# データベース接続テスト関数
test_db_connection() {
  local max_attempts=30
  local attempt=1
  
  echo "[entrypoint] Testing database connection..."
  
  while [ $attempt -le $max_attempts ]; do
    echo "[entrypoint] Connection attempt $attempt/$max_attempts"
    
    if python -c "
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

# Alembic用のsync URLに変換
url = os.environ['ALEMBIC_DATABASE_URL']
if url.startswith('postgresql+asyncpg://'):
    url = url.replace('postgresql+asyncpg://', 'postgresql+psycopg://', 1)

try:
    engine = create_engine(
        url,
        poolclass=NullPool,
        connect_args={
            'connect_timeout': 30,
            'application_name': 'db-test'
        }
    )
    
    with engine.connect() as conn:
        result = conn.execute('SELECT 1').scalar()
        if result == 1:
            print('[entrypoint] Database connection successful')
            sys.exit(0)
        else:
            print('[entrypoint] Database connection failed: unexpected result')
            sys.exit(1)
            
except Exception as e:
    print(f'[entrypoint] Database connection failed: {e}')
    sys.exit(1)
" 2>/dev/null; then
      echo "[entrypoint] Database connection established"
      break
    fi
    
    if [ $attempt -eq $max_attempts ]; then
      echo "[entrypoint] ERROR: Failed to connect to database after $max_attempts attempts" >&2
      exit 1
    fi
    
    echo "[entrypoint] Connection failed, retrying in 5 seconds..."
    sleep 5
    attempt=$((attempt + 1))
  done
}

# データベース接続テストを実行
test_db_connection

echo "[entrypoint] Running migrations against ${ALEMBIC_DATABASE_URL}"
alembic upgrade head

echo "[entrypoint] Starting gunicorn (UvicornWorker)"
exec gunicorn app.main:app \
  --workers="${WEB_CONCURRENCY:-2}" \
  --worker-class=uvicorn.workers.UvicornWorker \
  --bind="0.0.0.0:${PORT:-8000}" \
  --timeout="${GUNICORN_TIMEOUT:-120}"

