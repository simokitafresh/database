#!/usr/bin/env python
"""FastAPIローカル疎通スモークテスト。

DB接続不要なエンドポイント（/healthz, /v1/health）だけを叩きます。
"""

from pathlib import Path
import sys

# ルートを import path に追加（安全のため）
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import app


def main() -> int:
    with TestClient(app) as c:
        r1 = c.get("/healthz")
        print("/healthz", r1.status_code, r1.json())

        r2 = c.get("/v1/health")
        print("/v1/health", r2.status_code, r2.json())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
