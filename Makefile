.PHONY: install test format

install:
pip install -r requirements.txt

test:
pytest -q

format:
black .
