#!/usr/bin/env bash
set -e

alembic upgrade head

# Replace the shell with gunicorn so it becomes PID 1 and receives signals directly.
exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -b 0.0.0.0:${PORT:-8000}
