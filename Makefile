.PHONY: install test format migrate

export ALEMBIC_DATABASE_URL ?= postgresql+psycopg://postgres:postgres@localhost:5432/postgres

install:
	pip install -r requirements.txt
	pip install --upgrade yfinance

test:
	PYTHONPATH=. pytest -q

format:
	black .

migrate:
	alembic upgrade head
