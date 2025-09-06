#!/bin/bash

echo "=== Stock API 修正検証 ==="

echo "1. 構文チェック..."
python -m py_compile app/services/fetch_worker.py
python -m py_compile app/db/queries.py
python -m py_compile app/services/fetcher.py

echo "2. インポートチェック..."
python -c "from app.utils.date_utils import merge_date_ranges"
python -c "from app.db.queries import ensure_coverage_unified"

echo "3. テスト実行..."
pytest tests/unit/test_fetch_worker_transaction.py -v
pytest tests/unit/test_date_boundary.py -v

echo "=== 検証完了 ==="
