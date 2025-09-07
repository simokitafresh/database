#!/usr/bin/env python
"""Stock API 修正検証スクリプト"""

import sys
import subprocess
import importlib
from pathlib import Path

def print_section(title: str):
    print(f"\n=== {title} ===")

def run_command(cmd: list, description: str) -> bool:
    """コマンドを実行し、結果を返す"""
    try:
        print(f"{description}...")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✅ {description} - OK")
        if result.stdout:
            print(f"   出力: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - FAILED")
        print(f"   エラー: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ {description} - ERROR: {e}")
        return False

def check_import(module_name: str, item: str = None) -> bool:
    """インポートをチェック"""
    try:
        if item:
            module = importlib.import_module(module_name)
            getattr(module, item)
            print(f"✅ インポート OK: from {module_name} import {item}")
        else:
            importlib.import_module(module_name)
            print(f"✅ インポート OK: import {module_name}")
        return True
    except Exception as e:
        print(f"❌ インポート FAILED: {module_name}.{item or ''} - {e}")
        return False

def main():
    print("=== Stock API 修正検証 ===")
    
    all_passed = True
    
    # 1. 構文チェック
    print_section("構文チェック")
    files_to_check = [
        "app/services/fetch_worker.py",
        "app/db/queries.py", 
        "app/services/fetcher.py",
        "app/utils/date_utils.py"
    ]
    
    for file_path in files_to_check:
        if not run_command([sys.executable, "-m", "py_compile", file_path], f"構文チェック: {file_path}"):
            all_passed = False
    
    # 2. インポートチェック
    print_section("インポートチェック")
    imports_to_check = [
        ("app.utils.date_utils", "merge_date_ranges"),
        ("app.utils.date_utils", "validate_date_range"),
        ("app.db.queries", "ensure_coverage_unified"),
        ("app.db.queries", "binary_search_yf_start_date"),
        ("app.db.queries", "ensure_coverage_with_auto_fetch"),
    ]
    
    for module, item in imports_to_check:
        if not check_import(module, item):
            all_passed = False
    
    # 3. テスト実行
    print_section("テスト実行")
    test_files = [
        "tests/unit/test_fetch_worker_transaction.py",
        "tests/unit/test_date_boundary.py"
    ]
    
    for test_file in test_files:
        if Path(test_file).exists():
            if not run_command([sys.executable, "-m", "pytest", test_file, "-v"], f"テスト実行: {test_file}"):
                all_passed = False
        else:
            print(f"⚠️ テストファイルが見つかりません: {test_file}")
    
    # 最終結果
    print_section("検証結果")
    if all_passed:
        print("🎉 すべての検証が正常に完了しました！")
        return 0
    else:
        print("❌ いくつかの検証が失敗しました。上記のエラーを確認してください。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
