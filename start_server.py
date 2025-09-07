#!/usr/bin/env python
"""環境変数を読み込んでからAPIサーバーを起動するスクリプト"""

import os
import sys
from pathlib import Path

# .envファイルから環境変数を読み込む
def load_env_file():
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value
                    print(f"設定: {key} = {value[:20]}...")

if __name__ == "__main__":
    print("環境変数を読み込んでいます...")
    load_env_file()
    
    print("APIサーバーを起動しています...")
    # 仮想環境内のuvicornを使用
    import subprocess
    import sys
    
    subprocess.run([
        sys.executable, "-m", "uvicorn", 
        "app.main:app", 
        "--port", "8000", 
        "--reload"
    ])
