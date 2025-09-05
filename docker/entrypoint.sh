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
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

# Alembic用のsync URLに変換
url = os.environ['ALEMBIC_DATABASE_URL']

# デバッグ: 環境変数の内容を確認
print(f'[DEBUG] Raw ALEMBIC_DATABASE_URL: {repr(url)}')

# 環境変数のプレフィックスが含まれている場合の修正
if '=' in url and url.startswith(('ALEMBIC_DATABASE_URL=', 'DATABASE_URL=')):
    url = url.split('=', 1)[1]
    print(f'[DEBUG] Cleaned URL after split: {repr(url)}')

# 空白や改行の除去
url = url.strip()
print(f'[DEBUG] Final URL: {repr(url)}')

if url.startswith('postgresql+asyncpg://'):
    url = url.replace('postgresql+asyncpg://', 'postgresql+psycopg://', 1)
    print(f'[DEBUG] URL after driver conversion: {repr(url)}')

try:
    # Render/Supabase環境に最適化された接続設定
    connect_args = {
        'connect_timeout': 30,
        'application_name': 'entrypoint_db_test'
    }
    
    # Supabaseの場合はSSL設定を追加
    if 'supabase.com' in url or 'pooler.supabase.com' in url:
        connect_args['sslmode'] = 'require'
    
    engine = create_engine(
        url,
        poolclass=NullPool,
        connect_args=connect_args,
        # Render環境での接続最適化
        pool_pre_ping=True,
        echo=False
    )
    
    with engine.connect() as conn:
        result = conn.execute(text('SELECT 1')).scalar()
        if result == 1:
            print('[entrypoint] Database connection successful')
            sys.exit(0)
        else:
            print('[entrypoint] Database connection failed: unexpected result')
            sys.exit(1)
            
except Exception as e:
    print(f'[entrypoint] Database connection failed: {str(e)}')
    import traceback
    print(f'[entrypoint] Error details: {traceback.format_exc()}')
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

# Debug: Check current migration state
echo "[entrypoint] Checking current migration state..."
alembic current || echo "[entrypoint] No current migration found"

echo "[entrypoint] Showing migration history..."
alembic history --verbose || echo "[entrypoint] Error showing history"

# Try to run migrations
echo "[entrypoint] Attempting migration upgrade..."
if ! alembic upgrade head; then
  echo "[entrypoint] Migration failed, attempting to resolve..."
  
  # Check if alembic_version table exists and has conflicting data
  echo "[entrypoint] Checking for migration conflicts..."
  
  # Try to stamp current state to head (reset to latest)
  echo "[entrypoint] Resetting migration state to head..."
  alembic stamp head
  
  # Now try upgrade again
  echo "[entrypoint] Retrying migration upgrade..."
  alembic upgrade head
fi

echo "[entrypoint] Starting gunicorn (UvicornWorker)"
exec gunicorn app.main:app \
  --workers="${WEB_CONCURRENCY:-2}" \
  --worker-class=uvicorn.workers.UvicornWorker \
  --bind="0.0.0.0:${PORT:-8000}" \
  --timeout="${GUNICORN_TIMEOUT:-120}"

