#!/usr/bin/env bash
set -e

alembic upgrade head

gunicorn app.main:app --bind 0.0.0.0:8000 -k uvicorn.workers.UvicornWorker
