# Cron Job 日次更新機能 - 実装整合版アーキテクチャー設計書

## 1. 既存システムとの統合方針

### 1.1 活用する既存機能
```
既存のFetchJob機能を最大限活用:
- FetchJobモデル（fetch_jobs テーブル）
- /v1/fetch エンドポイント
- fetch_worker.process_fetch_job
- FetchJobRequest/Response スキーマ
```

### 1.2 システムフロー
```
Render Cron Service (10:00 JST)
    ↓ HTTP GET
/v1/cron/daily-update （新規）
    ↓
全シンボル取得（既存: list_symbols）
    ↓
バッチ分割（50シンボルずつ）
    ↓
create_fetch_job_endpoint（既存）を内部呼び出し
    ↓
process_fetch_job（既存）でバックグラウンド処理
    ↓
Yahoo Finance → upsert_prices（既存）
```

## 2. 実装詳細（既存コードとの整合性確保）

### 2.1 新規ファイル: `app/api/v1/cron.py`

```python
"""Cron job endpoints for scheduled data updates."""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.api.deps import get_session
from app.core.config import settings
from app.db.queries import list_symbols
from app.schemas.fetch_jobs import FetchJobRequest
from app.services.fetch_jobs import create_fetch_job
from app.services.fetch_worker import process_fetch_job

router = APIRouter()
logger = logging.getLogger(__name__)


def verify_cron_token(x_cron_secret: Optional[str] = Header(None)) -> bool:
    """Cronトークン認証.
    
    環境変数CRON_SECRET_TOKENが設定されている場合のみ認証を行う。
    開発環境では認証をスキップ可能。
    """
    # 環境変数が設定されていない場合は認証スキップ（開発用）
    if not settings.CRON_SECRET_TOKEN:
        logger.warning("CRON_SECRET_TOKEN not set, skipping authentication")
        return True
    
    if not x_cron_secret:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "MISSING_AUTH", "message": "Missing X-Cron-Secret header"}}
        )
    
    if x_cron_secret != settings.CRON_SECRET_TOKEN:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid cron token"}}
        )
    
    return True


@router.get("/cron/daily-update")
async def daily_update(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    authenticated: bool = Depends(verify_cron_token),
    dry_run: bool = False,
    limit: Optional[int] = None  # テスト用: シンボル数制限
) -> Dict[str, Any]:
    """
    全シンボルの日次データ更新を実行.
    
    既存のFetchJob機能を活用してバッチ処理を行う。
    
    Parameters
    ----------
    dry_run : bool
        True の場合、実際の処理は行わずシミュレーションのみ
    limit : int, optional
        処理するシンボル数の上限（テスト用）
        
    Returns
    -------
    Dict[str, Any]
        実行結果（ジョブID、バッチ数など）
    """
    start_time = datetime.utcnow()
    logger.info(f"Starting daily update cron job at {start_time}")
    
    try:
        # 1. 全アクティブシンボル取得（既存のlist_symbols関数を使用）
        all_symbols_data = await list_symbols(session, active=True)
        all_symbols = [row["symbol"] for row in all_symbols_data]
        
        if limit:
            all_symbols = all_symbols[:limit]
            logger.info(f"Limited to {limit} symbols for testing")
        
        total_symbols = len(all_symbols)
        logger.info(f"Found {total_symbols} active symbols to update")
        
        if total_symbols == 0:
            return {
                "status": "no_symbols",
                "message": "No active symbols found",
                "timestamp": start_time.isoformat()
            }
        
        # 2. 日付範囲の計算（最新7日間）
        date_to = date.today()
        date_from = date_to - timedelta(days=settings.CRON_UPDATE_DAYS)
        
        # 3. バッチ分割（既存のFETCH_JOB_MAX_SYMBOLSに合わせる）
        batch_size = min(settings.CRON_BATCH_SIZE, settings.FETCH_JOB_MAX_SYMBOLS)
        batches = [
            all_symbols[i:i + batch_size]
            for i in range(0, total_symbols, batch_size)
        ]
        
        logger.info(f"Split into {len(batches)} batches of max {batch_size} symbols")
        
        if dry_run:
            return {
                "status": "dry_run",
                "message": "Dry run completed",
                "total_symbols": total_symbols,
                "batch_count": len(batches),
                "batch_size": batch_size,
                "date_range": {
                    "from": date_from.isoformat(),
                    "to": date_to.isoformat()
                },
                "timestamp": start_time.isoformat()
            }
        
        # 4. 各バッチに対してFetchJobを作成
        job_ids = []
        for i, batch in enumerate(batches):
            try:
                # FetchJobRequestスキーマを使用（既存のバリデーション活用）
                request = FetchJobRequest(
                    symbols=batch,
                    date_from=date_from,
                    date_to=date_to,
                    interval="1d",
                    force=False,  # 既存データは上書きしない
                    priority="normal"
                )
                
                # 既存のcreate_fetch_job関数を使用
                job_id = await create_fetch_job(
                    session=session,
                    request=request,
                    created_by="cron_daily_update"
                )
                
                job_ids.append(job_id)
                
                # バックグラウンドで処理開始（既存のprocess_fetch_job使用）
                background_tasks.add_task(
                    process_fetch_job,
                    job_id=job_id,
                    symbols=batch,
                    date_from=date_from,
                    date_to=date_to,
                    interval="1d",
                    force=False,
                    max_concurrency=settings.YF_REQ_CONCURRENCY
                )
                
                logger.info(f"Created job {job_id} for batch {i+1}/{len(batches)}")
                
            except Exception as e:
                logger.error(f"Failed to create job for batch {i+1}: {e}")
                continue
        
        # 5. 実行ログを記録
        await log_cron_execution(
            session=session,
            status="started",
            total_symbols=total_symbols,
            job_ids=job_ids,
            execution_time=datetime.utcnow() - start_time
        )
        
        return {
            "status": "success",
            "message": f"Daily update started for {total_symbols} symbols",
            "total_symbols": total_symbols,
            "batch_count": len(batches),
            "job_ids": job_ids,
            "date_range": {
                "from": date_from.isoformat(),
                "to": date_to.isoformat()
            },
            "timestamp": start_time.isoformat(),
            "estimated_completion_minutes": (total_symbols * 0.5) / 60  # 概算
        }
        
    except Exception as e:
        logger.error(f"Daily update cron failed: {e}", exc_info=True)
        
        # エラーログ記録
        await log_cron_execution(
            session=session,
            status="failed",
            error=str(e),
            execution_time=datetime.utcnow() - start_time
        )
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "CRON_FAILED",
                    "message": f"Daily update failed: {str(e)}",
                    "timestamp": start_time.isoformat()
                }
            }
        )


async def log_cron_execution(
    session: AsyncSession,
    status: str,
    total_symbols: int = 0,
    job_ids: List[str] = None,
    error: Optional[str] = None,
    execution_time: timedelta = None
) -> None:
    """Cron実行ログを記録（簡易版）."""
    try:
        # 既存のfetch_jobsテーブルにcron実行記録を残す
        # （専用テーブルは後で追加可能）
        log_data = {
            "job_id": f"cron_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            "status": status,
            "symbols": job_ids or [],  # job_idsを記録
            "date_from": date.today() - timedelta(days=settings.CRON_UPDATE_DAYS),
            "date_to": date.today(),
            "interval": "1d",
            "force_refresh": False,
            "priority": "cron",
            "created_by": "cron_daily_update",
            "created_at": datetime.utcnow(),
            "progress": {
                "total_symbols": total_symbols,
                "execution_seconds": execution_time.total_seconds() if execution_time else 0
            },
            "errors": [{"error": error}] if error else []
        }
        
        await session.execute(
            text("""
                INSERT INTO fetch_jobs 
                (job_id, status, symbols, date_from, date_to, interval, 
                 force_refresh, priority, created_by, created_at, progress, errors)
                VALUES 
                (:job_id, :status, :symbols, :date_from, :date_to, :interval,
                 :force_refresh, :priority, :created_by, :created_at, 
                 :progress::jsonb, :errors::jsonb)
            """),
            log_data
        )
        await session.commit()
        
    except Exception as e:
        logger.error(f"Failed to log cron execution: {e}")


@router.get("/cron/status")
async def get_cron_status(
    session: AsyncSession = Depends(get_session),
    authenticated: bool = Depends(verify_cron_token)
) -> Dict[str, Any]:
    """
    最近のCron実行状況を取得.
    
    Returns
    -------
    Dict[str, Any]
        最近の実行履歴とステータス
    """
    try:
        # 最近のcron実行ジョブを取得
        result = await session.execute(
            text("""
                SELECT 
                    job_id,
                    status,
                    created_at,
                    started_at,
                    completed_at,
                    progress,
                    errors
                FROM fetch_jobs
                WHERE created_by = 'cron_daily_update'
                ORDER BY created_at DESC
                LIMIT 10
            """)
        )
        
        recent_jobs = []
        for row in result.fetchall():
            job_info = {
                "job_id": row.job_id,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "progress": row.progress,
                "has_errors": len(row.errors) > 0 if row.errors else False
            }
            recent_jobs.append(job_info)
        
        # 今日の実行統計
        today_result = await session.execute(
            text("""
                SELECT 
                    COUNT(*) as total_jobs,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE status IN ('pending', 'processing')) as in_progress
                FROM fetch_jobs
                WHERE created_by = 'cron_daily_update'
                AND created_at >= CURRENT_DATE
            """)
        )
        
        today_stats = today_result.fetchone()
        
        return {
            "status": "ok",
            "today": {
                "total_jobs": today_stats.total_jobs,
                "completed": today_stats.completed,
                "failed": today_stats.failed,
                "in_progress": today_stats.in_progress
            },
            "recent_jobs": recent_jobs,
            "next_run": "10:00 JST",
            "configuration": {
                "batch_size": settings.CRON_BATCH_SIZE,
                "update_days": settings.CRON_UPDATE_DAYS,
                "max_concurrency": settings.YF_REQ_CONCURRENCY
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get cron status: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "STATUS_ERROR", "message": str(e)}}
        )
```

### 2.2 更新: `app/core/config.py`

```python
# 既存の設定に追加
class Settings(BaseSettings):
    # ... 既存の設定 ...
    
    # Cron Job Settings（既存の設定を活用）
    CRON_SECRET_TOKEN: str = ""  # 空の場合は認証スキップ（開発用）
    CRON_BATCH_SIZE: int = 50    # FETCH_JOB_MAX_SYMBOLSと整合
    CRON_UPDATE_DAYS: int = 7     # YF_REFETCH_DAYSと同じ
```

### 2.3 更新: `app/api/v1/router.py`

```python
from fastapi import APIRouter

from .coverage import router as coverage_router
from .cron import router as cron_router  # 追加
from .fetch import router as fetch_router
from .prices import router as prices_router
from .symbols import router as symbols_router

router = APIRouter(prefix="/v1")
router.include_router(symbols_router)
router.include_router(prices_router)
router.include_router(coverage_router)
router.include_router(fetch_router)
router.include_router(cron_router)  # 追加
```

## 3. Render設定（実用版）

### 3.1 環境変数（Render Dashboard）

```bash
# 最小限の追加環境変数
CRON_SECRET_TOKEN=<32文字以上のランダム文字列>

# 既存の環境変数の確認・調整
YF_REQ_CONCURRENCY=2        # そのまま
FETCH_TIMEOUT_SECONDS=30    # そのまま
FETCH_JOB_MAX_SYMBOLS=100   # そのまま
YF_REFETCH_DAYS=7           # そのまま
DB_POOL_SIZE=2              # そのまま（Renderの制限内）
DB_MAX_OVERFLOW=3           # そのまま
```

### 3.2 Render Cron Job設定（Dashboard）

1. **Render Dashboardログイン**
2. **該当サービスを選択**
3. **Jobs タブをクリック**
4. **Create Job** をクリック
5. **設定内容：**

```yaml
Name: Daily Stock Update
Schedule: 0 1 * * *  # UTC 01:00 = JST 10:00
Command: curl -X GET "${RENDER_EXTERNAL_URL}/v1/cron/daily-update" \
         -H "X-Cron-Secret: ${CRON_SECRET_TOKEN}" \
         --max-time 3600 \
         --retry 2 \
         --retry-delay 30
```

### 3.3 代替: GitHub Actions（無料オプション）

```yaml
# .github/workflows/daily-update.yml
name: Daily Stock Update

on:
  schedule:
    - cron: '0 1 * * *'  # UTC 01:00
  workflow_dispatch:  # 手動実行可能

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Update
        run: |
          curl -X GET "${{ secrets.API_URL }}/v1/cron/daily-update" \
            -H "X-Cron-Secret: ${{ secrets.CRON_SECRET }}" \
            --max-time 3600 \
            --retry 2
```

## 4. テストと段階的導入

### 4.1 ローカルテスト

```bash
# 1. 環境変数設定（.env）
CRON_SECRET_TOKEN=test-token-local

# 2. ドライランテスト（実際には実行しない）
curl -X GET "http://localhost:8000/v1/cron/daily-update?dry_run=true" \
  -H "X-Cron-Secret: test-token-local"

# 3. 限定テスト（10シンボルのみ）
curl -X GET "http://localhost:8000/v1/cron/daily-update?limit=10" \
  -H "X-Cron-Secret: test-token-local"

# 4. ステータス確認
curl -X GET "http://localhost:8000/v1/cron/status" \
  -H "X-Cron-Secret: test-token-local"
```

### 4.2 本番段階的導入

```python
# Phase 1: 少数シンボルでテスト（1週間）
limit=50

# Phase 2: 中規模テスト（1週間）
limit=200

# Phase 3: 全シンボル（制限なし）
limit=None
```

## 5. 監視とトラブルシューティング

### 5.1 ログ確認

```sql
-- 今日のCron実行状況
SELECT 
    job_id,
    status,
    created_at,
    completed_at,
    EXTRACT(EPOCH FROM (completed_at - started_at)) as duration_seconds
FROM fetch_jobs
WHERE created_by = 'cron_daily_update'
AND created_at >= CURRENT_DATE
ORDER BY created_at DESC;

-- エラーの確認
SELECT 
    job_id,
    errors
FROM fetch_jobs
WHERE created_by = 'cron_daily_update'
AND errors IS NOT NULL
AND errors != '[]'::jsonb
ORDER BY created_at DESC
LIMIT 10;

-- シンボル別の更新状況
SELECT 
    p.symbol,
    MAX(p.last_updated) as last_update,
    COUNT(*) as recent_records
FROM prices p
WHERE p.last_updated >= CURRENT_DATE - INTERVAL '1 day'
GROUP BY p.symbol
ORDER BY last_update DESC;
```

### 5.2 よくある問題と対処

| 問題 | 確認コマンド | 対処法 |
|------|------------|--------|
| Cronが実行されない | `render logs --tail` | Cron設定確認、トークン確認 |
| 途中で止まる | `/v1/cron/status` | タイムアウト延長、バッチサイズ縮小 |
| Yahoo Finance 429エラー | fetch_jobsのerrors確認 | YF_REQ_CONCURRENCY=1に減らす |
| DB接続エラー | PostgreSQLログ確認 | DB_POOL_SIZE=1に減らす |

## 6. パフォーマンス最適化

### 6.1 現在の設定での推定処理時間

```
条件:
- 1000シンボル
- バッチサイズ: 50
- 同時実行: 2
- 1シンボルあたり: 約0.5秒

計算:
- バッチ数: 20
- 並列度を考慮: 20 / 2 = 10セット
- 総時間: 10 × 50 × 0.5秒 = 250秒 ≈ 4-5分
```

### 6.2 最適化案

```python
# 人気シンボルの優先処理
popular_symbols = ["AAPL", "MSFT", "GOOGL", ...]  # 上位100
other_symbols = [s for s in all_symbols if s not in popular_symbols]

# 人気シンボルを先に処理
process_batch(popular_symbols, priority="high")
process_batch(other_symbols, priority="normal")
```

## 7. セキュリティ考慮事項

### 7.1 トークン生成

```python
# 安全なトークン生成
import secrets
token = secrets.token_urlsafe(32)
print(f"CRON_SECRET_TOKEN={token}")
```

### 7.2 アクセス制限（オプション）

```python
# IPアドレス制限を追加
from fastapi import Request

def verify_render_ip(request: Request):
    # RenderのIPレンジを確認
    client_ip = request.client.host
    allowed_ips = ["52.89.214.238", ...]  # Render IPs
    if client_ip not in allowed_ips:
        raise HTTPException(403, "Forbidden")
```

## 8. 実装チェックリスト

- [ ] `app/api/v1/cron.py` 作成
- [ ] `app/api/v1/router.py` 更新
- [ ] `app/core/config.py` 更新
- [ ] 環境変数 `CRON_SECRET_TOKEN` 生成・設定
- [ ] ローカルでドライランテスト
- [ ] ローカルで限定実行テスト（10シンボル）
- [ ] Renderに環境変数設定
- [ ] Render Cron Job作成
- [ ] 本番でドライランテスト
- [ ] 本番で限定実行テスト（50シンボル）
- [ ] 監視設定
- [ ] 本番フル稼働