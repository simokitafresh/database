#!/usr/bin/env python
"""FastAPI単体テスト - 環境分離"""

import os
import sys
from pathlib import Path

# 環境変数読み込み
def load_env():
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value

# テスト実行
def test_api_isolation():
    print("=== FastAPI単体テスト ===")
    
    # 1. 環境変数読み込み
    load_env()
    print(f"DATABASE_URL設定: {'DATABASE_URL' in os.environ}")
    
    # 2. FastAPI app import
    try:
        from app.main import app
        print("✅ FastAPI app import成功")
    except Exception as e:
        print(f"❌ FastAPI app import失敗: {e}")
        return False
    
    # 3. TestClient使用
    try:
        from fastapi.testclient import TestClient
        client = TestClient(app)
        print("✅ TestClient作成成功")
    except Exception as e:
        print(f"❌ TestClient作成失敗: {e}")
        return False
    
    # 4. API呼び出し
    try:
        response = client.get("/v1/symbols")
        print(f"✅ API呼び出し成功")
        print(f"   Status: {response.status_code}")
        if response.status_code != 200:
            print(f"   Error: {response.text}")
        else:
            data = response.json()
            print(f"   データ数: {len(data)}")
            if data:
                print(f"   最初のシンボル: {data[0]}")
        return True
    except Exception as e:
        print(f"❌ API呼び出し失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_api_isolation()
    sys.exit(0 if success else 1)
