.PHONY: install test format

install:
	pip install -r requirements.txt
	pip install --upgrade yfinance

test:
	PYTHONPATH=. pytest -q

format:
	black .
