# Cronジョブ修正 - 詳細実装タスクリスト

## 前提条件
- 現在のコードベース: Renderでデプロイ済み、Supabaseデータベース使用
- 問題箇所: `app/api/v1/cron.py`の`daily_update`関数（106-184行目）
- 実装言語: Python 3.12、FastAPI、SQLAlchemy、asyncpg

## Phase 1: 事前準備とコード分析

### Task 1.1: 現在のコード構造の確認
- [ ] `app/api/v1/cron.py`の全体構造を確認
  - [ ] 現在の`daily_update`関数（106-184行目）の内容を確認
  - [ ] `verify_cron_token`関数（18-38行目）の動作確認
  - [ ] インポート文（1-14行目）の確認

### Task 1.2: 依存関係の確認
- [ ] 必要なインポートの確認
  ```python
  # 現在のインポート（1-14行目）
  import logging
  from datetime import date, datetime, timedelta
  from typing import Dict, Any, List, Optional
  from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
  from sqlalchemy.ext.asyncio import AsyncSession
  from sqlalchemy import text
  from app.api.deps import get_session
  from app.core.config import settings
  from app.db.queries import list_symbols
  from app.schemas.cron import CronDailyUpdateRequest, CronDailyUpdateResponse, CronStatusResponse
  ```
- [ ] 追加で必要なインポートの特定
  ```python
  # 追加が必要なインポート
  from app.db.queries import ensure_coverage  # データ取得と保存の統合処理
  from typing import Tuple  # タプル型の追加
  ```

### Task 1.3: 既存関数の動作確認
- [ ] `app/db/queries.py`の`ensure_coverage`関数（436-588行目）の仕様確認
  - [ ] 引数: `(session, symbols, date_from, date_to, refetch_days)`
  - [ ] 戻り値: なし（データベースに直接書き込み）
  - [ ] エラー処理: 例外をraiseする
- [ ] `app/db/queries.py`の`list_symbols`関数（661-674行目）の仕様確認
  - [ ] 引数: `(session, active=None)`
  - [ ] 戻り値: `Sequence[Any]`（辞書のリスト）
  - [ ] 各辞書のキー: `symbol`, `name`, `exchange`, `currency`, `is_active`, `first_date`, `last_date`, `created_at`

## Phase 2: レスポンススキーマの更新

### Task 2.1: `app/schemas/cron.py`の修正
- [ ] 現在の`CronDailyUpdateResponse`クラス（26-35行目）を確認
  ```python
  class CronDailyUpdateResponse(BaseModel):
      status: str = Field(description="Status of the operation")
      message: str = Field(description="Human readable message")
      total_symbols: int = Field(description="Total number of symbols processed")
      batch_count: int = Field(description="Number of batches created")
      job_ids: Optional[List[int]] = Field(None, description="List of created fetch job IDs")
      date_range: Dict[str, str] = Field(description="Date range processed")
      timestamp: str = Field(description="When the operation started")
      estimated_completion_minutes: Optional[float] = Field(None, description="Estimated time to complete all jobs")
      batch_size: Optional[int] = Field(None, description="Size of each batch for dry run")
  ```
- [ ] `failed_symbols`フィールドを追加（35行目の後に）
  ```python
  failed_symbols: Optional[List[str]] = Field(None, description="List of symbols that failed to update")
  ```
- [ ] `success_count`フィールドを追加（36行目の後に）
  ```python
  success_count: Optional[int] = Field(None, description="Number of successfully updated symbols")
  ```

## Phase 3: メイン実装 - `daily_update`関数の修正

### Task 3.1: 関数シグネチャとインポートの更新
- [ ] 関数定義行（106-111行目）は変更なし
  ```python
  @router.post("/daily-update", response_model=CronDailyUpdateResponse)
  async def daily_update(
      request: CronDailyUpdateRequest,
      background_tasks: BackgroundTasks,
      session: AsyncSession = Depends(get_session),
      authenticated: bool = Depends(verify_cron_token)
  ) -> CronDailyUpdateResponse:
  ```
- [ ] 必要なインポートを追加（ファイル上部）
  ```python
  from app.db.queries import ensure_coverage
  ```

### Task 3.2: 初期設定部分の確認（112-127行目）
- [ ] 現在のコードを保持
  ```python
  start_time = datetime.utcnow()
  
  try:
      logger.info(f"Starting daily stock data update (dry_run={request.dry_run})")
      
      # Basic configuration check
      if not hasattr(settings, 'CRON_BATCH_SIZE'):
          logger.warning("CRON_BATCH_SIZE not set, using default: 50")
          batch_size = 50
      else:
          batch_size = settings.CRON_BATCH_SIZE or 50
  ```

### Task 3.3: データベース接続テスト（128-136行目）
- [ ] 現在のコードを保持
  ```python
  # Test database connection first
  try:
      await session.execute(text("SELECT 1"))
      logger.info("Database connection verified")
  except Exception as db_error:
      logger.error(f"Database connection failed: {db_error}")
      raise HTTPException(
          status_code=500,
          detail={"error": {"code": "DATABASE_ERROR", "message": f"Database connection failed: {str(db_error)}"}}
      )
  ```

### Task 3.4: シンボル取得処理（137-153行目）
- [ ] 現在のコードを修正
  ```python
  # Get active symbols
  try:
      all_symbols_data = await list_symbols(session, active=True)
      all_symbols = [row["symbol"] for row in all_symbols_data]  # 辞書からsymbolを抽出
      
      if not all_symbols:
          logger.warning("No active symbols found in database")
          return CronDailyUpdateResponse(
              status="success",
              message="No active symbols found to update", 
              total_symbols=0,
              batch_count=0,
              date_range={"from": "N/A", "to": "N/A"},
              timestamp=start_time.isoformat()
          )
      
      logger.info(f"Found {len(all_symbols)} active symbols")
      
  except Exception as symbols_error:
      logger.error(f"Failed to fetch symbols: {symbols_error}")
      raise HTTPException(
          status_code=500,
          detail={"error": {"code": "SYMBOLS_ERROR", "message": f"Failed to fetch symbols: {str(symbols_error)}"}}
      )
  ```

### Task 3.5: 日付範囲の計算（dry_run前に追加）
- [ ] dry_runチェック（154行目）の前に日付計算を追加
  ```python
  # Calculate date range for updates
  if request.date_from:
      try:
          date_from = datetime.strptime(request.date_from, '%Y-%m-%d').date()
      except ValueError:
          date_from = date.today() - timedelta(days=settings.CRON_UPDATE_DAYS)
  else:
      date_from = date.today() - timedelta(days=settings.CRON_UPDATE_DAYS)
  
  if request.date_to:
      try:
          date_to = datetime.strptime(request.date_to, '%Y-%m-%d').date()
      except ValueError:
          date_to = date.today() - timedelta(days=1)
  else:
      date_to = date.today() - timedelta(days=1)  # Yesterday
  
  logger.info(f"Date range for update: {date_from} to {date_to}")
  ```

### Task 3.6: dry_runチェックの修正（154-164行目）
- [ ] 現在のdry_runロジックを修正
  ```python
  if request.dry_run:
      execution_time = (datetime.utcnow() - start_time).total_seconds()
      return CronDailyUpdateResponse(
          status="success", 
          message=f"Dry run completed. Would process {len(all_symbols)} symbols in batches of {batch_size}",
          total_symbols=len(all_symbols),
          batch_count=(len(all_symbols) + batch_size - 1) // batch_size,
          date_range={"from": str(date_from), "to": str(date_to)},  # 実際の日付を使用
          timestamp=start_time.isoformat(),
          batch_size=batch_size
      )
  ```

### Task 3.7: 実際のデータ更新処理の実装（165-173行目を置き換え）
- [ ] TODOコメントとシミュレーション処理を削除
- [ ] 実際のデータ更新処理を実装
  ```python
  # Actual data update processing
  logger.info(f"Starting actual data update for {len(all_symbols)} symbols")
  
  # Initialize counters and tracking
  success_count = 0
  failed_symbols = []
  processed_count = 0
  batch_number = 0
  
  # Process symbols in batches for better resource management
  for batch_start in range(0, len(all_symbols), batch_size):
      batch_end = min(batch_start + batch_size, len(all_symbols))
      batch_symbols = all_symbols[batch_start:batch_end]
      batch_number += 1
      
      logger.info(f"Processing batch {batch_number}: symbols {batch_start+1} to {batch_end}")
      
      # Process each symbol in the batch
      for symbol in batch_symbols:
          processed_count += 1
          logger.debug(f"Processing symbol {processed_count}/{len(all_symbols)}: {symbol}")
          
          try:
              # Use ensure_coverage to fetch and update data
              await ensure_coverage(
                  session=session,
                  symbols=[symbol],
                  date_from=date_from,
                  date_to=date_to,
                  refetch_days=settings.YF_REFETCH_DAYS
              )
              
              # Commit after each successful symbol
              await session.commit()
              success_count += 1
              logger.info(f"Successfully updated {symbol} ({success_count}/{processed_count})")
              
          except Exception as symbol_error:
              # Log the error but continue with next symbol
              logger.error(f"Failed to update {symbol}: {str(symbol_error)}", exc_info=True)
              failed_symbols.append(symbol)
              
              # Rollback the failed transaction
              await session.rollback()
              
          # Add small delay to avoid overwhelming Yahoo Finance API
          if processed_count % 10 == 0:
              import asyncio
              await asyncio.sleep(1)  # 1 second delay every 10 symbols
  
  # Determine final status based on results
  if failed_symbols:
      if success_count == 0:
          final_status = "failed"
          final_message = f"All {len(all_symbols)} symbols failed to update"
      else:
          final_status = "completed_with_errors"
          final_message = f"Updated {success_count}/{len(all_symbols)} symbols successfully"
  else:
      final_status = "success"
      final_message = f"Successfully updated all {success_count} symbols"
  
  logger.info(f"Data update completed: {final_message}")
  if failed_symbols:
      logger.warning(f"Failed symbols: {', '.join(failed_symbols[:10])}" + 
                    (f" and {len(failed_symbols)-10} more" if len(failed_symbols) > 10 else ""))
  ```

### Task 3.8: 最終レスポンスの構築（174-184行目を置き換え）
- [ ] 実際の結果を含むレスポンスを返す
  ```python
  execution_time = (datetime.utcnow() - start_time).total_seconds()
  return CronDailyUpdateResponse(
      status=final_status,
      message=final_message,
      total_symbols=len(all_symbols),
      batch_count=batch_number,
      date_range={"from": str(date_from), "to": str(date_to)},
      timestamp=start_time.isoformat(),
      batch_size=batch_size,
      success_count=success_count,
      failed_symbols=failed_symbols if failed_symbols else None
  )
  ```

### Task 3.9: 例外処理の更新（185-200行目）
- [ ] 現在の例外処理を保持し、実行時間を追加
  ```python
  except HTTPException:
      # Re-raise HTTP exceptions as-is
      raise
  except Exception as e:
      logger.exception("Unexpected error in daily_update")
      execution_time = (datetime.utcnow() - start_time).total_seconds()
      
      # Log summary even on failure
      logger.error(f"Cron job failed after {execution_time:.2f} seconds")
      
      raise HTTPException(
          status_code=500,
          detail={
              "error": {
                  "code": "INTERNAL_ERROR",
                  "message": f"Internal server error: {str(e)}",
                  "execution_time_seconds": execution_time
              }
          }
      )
  ```

## Phase 4: 追加の最適化とエラーハンドリング

### Task 4.1: タイムアウト処理の追加
- [ ] 各シンボルの処理にタイムアウトを設定
  ```python
  import asyncio
  
  # In the symbol processing loop:
  try:
      # Set timeout for each symbol (30 seconds)
      await asyncio.wait_for(
          ensure_coverage(
              session=session,
              symbols=[symbol],
              date_from=date_from,
              date_to=date_to,
              refetch_days=settings.YF_REFETCH_DAYS
          ),
          timeout=30.0
      )
      await session.commit()
      success_count += 1
      
  except asyncio.TimeoutError:
      logger.error(f"Timeout updating {symbol} (exceeded 30 seconds)")
      failed_symbols.append(symbol)
      await session.rollback()
  except Exception as symbol_error:
      logger.error(f"Failed to update {symbol}: {str(symbol_error)}")
      failed_symbols.append(symbol)
      await session.rollback()
  ```

### Task 4.2: 進捗ログの改善
- [ ] バッチごとの進捗表示を追加
  ```python
  # After each batch
  batch_success = success_count - (batch_start - len([s for s in failed_symbols if s in batch_symbols]))
  batch_failed = len([s for s in failed_symbols if s in batch_symbols])
  
  logger.info(f"Batch {batch_number} completed: {batch_success} success, {batch_failed} failed")
  
  # Estimate remaining time
  if processed_count > 0:
      avg_time_per_symbol = execution_time / processed_count
      estimated_remaining = avg_time_per_symbol * (len(all_symbols) - processed_count)
      logger.info(f"Estimated time remaining: {estimated_remaining:.1f} seconds")
  ```

### Task 4.3: メモリ管理の改善
- [ ] セッションのクリア処理を追加
  ```python
  # After each batch, clear session to free memory
  session.expire_all()
  
  # Force garbage collection for large batches
  if batch_number % 5 == 0:
      import gc
      gc.collect()
      logger.debug(f"Memory cleanup after batch {batch_number}")
  ```

## Phase 5: 重複したdaily_update関数の削除

### Task 5.1: 重複関数の確認と削除
- [ ] 201-299行目にある重複した`daily_update`関数を確認
- [ ] この関数定義全体を削除（decoratorから関数の終わりまで）
- [ ] 削除する行番号: 201-299

### Task 5.2: 関連する未使用コードの削除
- [ ] 削除後、ファイル全体の整合性を確認
- [ ] インデントエラーがないことを確認
- [ ] 関数の重複定義エラーが解消されることを確認

## Phase 6: ステータスエンドポイントの修正

### Task 6.1: `get_cron_status`関数の更新（301-332行目）
- [ ] 現在のコードを確認
- [ ] 実際のジョブ履歴を取得する処理を追加（fetch_jobsテーブルが存在する場合）
  ```python
  @router.get("/status", response_model=CronStatusResponse, summary="Get cron job status")
  async def get_cron_status(
      authenticated: bool = Depends(verify_cron_token),
      session: AsyncSession = Depends(get_session)
  ) -> CronStatusResponse:
      """Get current status of cron jobs"""
      
      try:
          # Check if we can access symbols table
          result = await session.execute(
              text("SELECT COUNT(*) as count FROM symbols WHERE is_active = true")
          )
          active_symbols = result.scalar()
          
          # Get last cron execution (if logged)
          last_run = None
          try:
              last_run_result = await session.execute(
                  text("""
                      SELECT MAX(last_updated) as last_update 
                      FROM prices 
                      WHERE last_updated > NOW() - INTERVAL '24 hours'
                  """)
              )
              last_update = last_run_result.scalar()
              if last_update:
                  last_run = last_update.isoformat()
          except Exception:
              pass
          
          return CronStatusResponse(
              status="active",
              last_run=last_run,
              recent_job_count=0,  # fetch_jobs table doesn't exist yet
              job_status_counts={},
              settings={
                  "batch_size": settings.CRON_BATCH_SIZE,
                  "update_days": settings.CRON_UPDATE_DAYS,
                  "yf_concurrency": getattr(settings, 'YF_REQ_CONCURRENCY', 5),
                  "active_symbols": active_symbols
              }
          )
          
      except Exception as e:
          logger.error(f"Failed to get cron status: {e}")
          raise HTTPException(
              status_code=500,
              detail={"error": {"code": "STATUS_ERROR", "message": f"Failed to get cron status: {str(e)}"}}
          )
  ```

## Phase 7: ログ設定の改善

### Task 7.1: ログレベルの調整
- [ ] ファイル上部でloggerの設定を確認（16行目）
  ```python
  logger = logging.getLogger(__name__)
  ```
- [ ] 詳細ログの追加（デバッグ用）
  ```python
  # In daily_update function, add debug logs
  if settings.DEBUG or settings.LOG_LEVEL == "DEBUG":
      logger.debug(f"Processing {symbol}: dates {date_from} to {date_to}")
  ```

### Task 7.2: エラーログの改善
- [ ] スタックトレースを含むエラーログ
  ```python
  logger.error(f"Failed to update {symbol}: {str(symbol_error)}", exc_info=True)
  ```

## Phase 8: テストとデバッグ

### Task 8.1: ローカルテスト用のスクリプト作成
- [ ] `scripts/test_cron_local.py`を作成
  ```python
  #!/usr/bin/env python3
  import asyncio
  import os
  from datetime import date, timedelta
  from app.api.v1.cron import daily_update
  from app.schemas.cron import CronDailyUpdateRequest
  from app.db.engine import create_engine_and_sessionmaker
  
  async def test_daily_update():
      # Create session
      _, SessionLocal = create_engine_and_sessionmaker(
          database_url=os.getenv("DATABASE_URL")
      )
      
      async with SessionLocal() as session:
          # Create request
          request = CronDailyUpdateRequest(
              dry_run=False,
              date_from=(date.today() - timedelta(days=7)).isoformat(),
              date_to=(date.today() - timedelta(days=1)).isoformat()
          )
          
          # Mock background_tasks
          class MockBackgroundTasks:
              def add_task(self, *args, **kwargs):
                  pass
          
          # Run update
          result = await daily_update(
              request=request,
              background_tasks=MockBackgroundTasks(),
              session=session,
              authenticated=True
          )
          
          print(f"Result: {result}")
  
  if __name__ == "__main__":
      asyncio.run(test_daily_update())
  ```

### Task 8.2: 単体テストの作成
- [ ] `tests/test_cron.py`を作成または更新
  ```python
  import pytest
  from datetime import date, timedelta
  from app.schemas.cron import CronDailyUpdateRequest
  
  @pytest.mark.asyncio
  async def test_daily_update_dry_run(test_session):
      """Test dry run mode"""
      from app.api.v1.cron import daily_update
      
      request = CronDailyUpdateRequest(dry_run=True)
      
      # Mock background_tasks
      class MockBackgroundTasks:
          def add_task(self, *args, **kwargs):
              pass
      
      result = await daily_update(
          request=request,
          background_tasks=MockBackgroundTasks(),
          session=test_session,
          authenticated=True
      )
      
      assert result.status == "success"
      assert "Dry run completed" in result.message
  
  @pytest.mark.asyncio
  async def test_daily_update_with_data(test_session, mock_yfinance):
      """Test actual data update"""
      from app.api.v1.cron import daily_update
      
      request = CronDailyUpdateRequest(dry_run=False)
      
      # Mock background_tasks
      class MockBackgroundTasks:
          def add_task(self, *args, **kwargs):
              pass
      
      result = await daily_update(
          request=request,
          background_tasks=MockBackgroundTasks(),
          session=test_session,
          authenticated=True
      )
      
      assert result.status in ["success", "completed_with_errors"]
      assert result.total_symbols >= 0
  ```

## Phase 9: デプロイ前の確認

### Task 9.1: コード品質チェック
- [ ] `black`でフォーマット
  ```bash
  black app/api/v1/cron.py
  black app/schemas/cron.py
  ```
- [ ] `ruff`でリンティング
  ```bash
  ruff check app/api/v1/cron.py
  ruff check app/schemas/cron.py
  ```
- [ ] `mypy`で型チェック
  ```bash
  mypy app/api/v1/cron.py
  mypy app/schemas/cron.py
  ```

### Task 9.2: インポートの整理
- [ ] 未使用のインポートを削除
- [ ] インポートの順序を整理（標準ライブラリ → サードパーティ → ローカル）
  ```python
  # Standard library
  import asyncio
  import logging
  from datetime import date, datetime, timedelta
  from typing import Dict, Any, List, Optional, Tuple
  
  # Third-party
  from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
  from sqlalchemy.ext.asyncio import AsyncSession
  from sqlalchemy import text
  
  # Local application
  from app.api.deps import get_session
  from app.core.config import settings
  from app.db.queries import list_symbols, ensure_coverage
  from app.schemas.cron import (
      CronDailyUpdateRequest, 
      CronDailyUpdateResponse, 
      CronStatusResponse
  )
  ```

### Task 9.3: 設定値の確認
- [ ] `.env`ファイルの確認
  ```env
  CRON_SECRET_TOKEN=8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA
  CRON_BATCH_SIZE=50
  CRON_UPDATE_DAYS=7
  YF_REQ_CONCURRENCY=2
  YF_REFETCH_DAYS=7
  ```
- [ ] Render環境変数の確認
  - [ ] `CRON_SECRET_TOKEN`が設定されている
  - [ ] `CRON_BATCH_SIZE`が適切（50）
  - [ ] `CRON_UPDATE_DAYS`が適切（7）

## Phase 10: デプロイと検証

### Task 10.1: Gitコミット
- [ ] 変更ファイルの確認
  ```bash
  git status
  # Modified: app/api/v1/cron.py
  # Modified: app/schemas/cron.py
  ```
- [ ] 変更内容の差分確認
  ```bash
  git diff app/api/v1/cron.py
  git diff app/schemas/cron.py
  ```
- [ ] コミット
  ```bash
  git add app/api/v1/cron.py app/schemas/cron.py
  git commit -m "fix: Implement actual data update in cron job daily_update function

  - Replace simulation with real ensure_coverage calls
  - Add proper error handling for individual symbol failures
  - Add success_count and failed_symbols to response
  - Remove duplicate daily_update function definition
  - Add timeout handling for each symbol update
  - Improve logging with progress tracking"
  ```

### Task 10.2: デプロイ
- [ ] Gitプッシュ
  ```bash
  git push origin main
  ```
- [ ] Renderの自動デプロイを確認
  - [ ] Renderダッシュボードでデプロイステータスを確認
  - [ ] ビルドログでエラーがないことを確認
  - [ ] デプロイ完了を待つ（約3-5分）

### Task 10.3: デプロイ後の動作確認
- [ ] ヘルスチェック
  ```bash
  curl https://stockdata-api-6xok.onrender.com/healthz
  # Expected: {"status":"ok"}
  ```
- [ ] APIドキュメントアクセス
  ```bash
  curl https://stockdata-api-6xok.onrender.com/docs
  # Expected: HTTP 200
  ```
- [ ] Cronステータス確認
  ```bash
  curl -X GET https://stockdata-api-6xok.onrender.com/v1/status \
    -H "X-Cron-Secret: 8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA"
  ```

### Task 10.4: Dry Runテスト
- [ ] Dry runモードでテスト
  ```bash
  curl -X POST https://stockdata-api-6xok.onrender.com/v1/daily-update \
    -H "X-Cron-Secret: 8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA" \
    -H "Content-Type: application/json" \
    -d '{"dry_run": true}'
  ```
- [ ] レスポンスの確認
  - [ ] statusが"success"
  - [ ] messageに"Dry run completed"が含まれる
  - [ ] total_symbolsが36（または実際のアクティブシンボル数）
  - [ ] date_rangeが正しい

### Task 10.5: 実際のデータ更新テスト（小規模）
- [ ] 特定の日付範囲でテスト
  ```bash
  curl -X POST https://stockdata-api-6xok.onrender.com/v1/daily-update \
    -H "X-Cron-Secret: 8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA" \
    -H "Content-Type: application/json" \
    -d '{
      "dry_run": false,
      "date_from": "'$(date -d '2 days ago' +%Y-%m-%d)'",
      "date_to": "'$(date -d 'yesterday' +%Y-%m-%d)'"
    }'
  ```
- [ ] レスポンスの確認
  - [ ] statusが"success"または"completed_with_errors"
  - [ ] messageに実際の更新数が含まれる
  - [ ] success_countが0より大きい
  - [ ] failed_symbolsの確認（あれば）

### Task 10.6: Supabaseでのデータ確認
- [ ] Supabaseダッシュボードにログイン
- [ ] `prices`テーブルを確認
  ```sql
  -- 最新のデータ更新を確認
  SELECT symbol, MAX(last_updated) as latest_update, COUNT(*) as record_count
  FROM prices
  WHERE last_updated > NOW() - INTERVAL '1 hour'
  GROUP BY symbol
  ORDER BY latest_update DESC
  LIMIT 10;
  ```
- [ ] 更新されたレコード数を確認
  ```sql
  -- 過去1時間に更新されたレコード数
  SELECT COUNT(*) as updated_records
  FROM prices
  WHERE last_updated > NOW() - INTERVAL '1 hour';
  ```
- [ ] 特定シンボルのデータ確認
  ```sql
  -- 例: AAPLの最新データ
  SELECT *
  FROM prices
  WHERE symbol = 'AAPL'
  ORDER BY date DESC
  LIMIT 10;
  ```

### Task 10.7: Renderログの確認
- [ ] Renderダッシュボードでログを確認
- [ ] エラーログがないことを確認
- [ ] 以下のログメッセージを確認
  - [ ] "Starting daily stock data update"
  - [ ] "Database connection verified"
  - [ ] "Found X active symbols"
  - [ ] "Successfully updated SYMBOL"
  - [ ] "Data update completed"

### Task 10.8: Cronジョブの実行確認
- [ ] Render Cron Jobsで手動実行
  ```bash
  # Renderダッシュボード → Cron Jobs → Run Now
  ```
- [ ] 実行ログの確認
  - [ ] "Cron job completed successfully"
  - [ ] "Job status: success"
  - [ ] エラーがないこと

## Phase 11: 本番運用の準備

### Task 11.1: エラー通知の設定（オプション）
- [ ] Slackウェブフック設定（必要に応じて）
- [ ] エラー時の通知処理追加
  ```python
  if failed_symbols and len(failed_symbols) > len(all_symbols) * 0.1:  # 10%以上失敗
      # Send alert (implement notification service)
      logger.critical(f"High failure rate: {len(failed_symbols)}/{len(all_symbols)} symbols failed")
  ```

### Task 11.2: パフォーマンスチューニング
- [ ] バッチサイズの最適化
  - [ ] 現在の50から調整が必要か確認
  - [ ] Yahoo Finance APIの制限を考慮
- [ ] タイムアウト値の調整
  - [ ] シンボルごとのタイムアウト（30秒）
  - [ ] 全体のタイムアウト（3600秒）

### Task 11.3: ドキュメント更新
- [ ] README.mdにcronジョブの説明を追加
- [ ] 運用手順書の作成
  - [ ] cronジョブの監視方法
  - [ ] エラー時の対処法
  - [ ] 手動実行の方法

## Phase 12: 完了確認

### Task 12.1: 最終チェックリスト
- [ ] コードの変更が正しく反映されている
- [ ] テストが通過している
- [ ] デプロイが成功している
- [ ] cronジョブが正常に動作している
- [ ] データベースにデータが保存されている
- [ ] ログに適切な情報が記録されている
- [ ] エラーハンドリングが機能している

### Task 12.2: 成功基準の確認
- [ ] cronジョブのレスポンスに"simulated"が含まれない
- [ ] Supabaseの`prices`テーブルに新しいデータが追加されている
- [ ] `last_updated`フィールドが現在時刻に更新されている
- [ ] 36個のアクティブシンボルが処理されている

### Task 12.3: ロールバック準備
- [ ] 問題が発生した場合のロールバック手順
  ```bash
  # Gitで前のコミットに戻す
  git revert HEAD
  git push origin main
  
  # またはRenderで前のデプロイに戻す
  # Render Dashboard → Deploys → Rollback to previous
  ```

## 完了後の監視

### 継続的な監視項目
1. **日次確認**
   - cronジョブの実行ログ
   - データ更新の成功率
   - エラーの有無

2. **週次確認**
   - パフォーマンスメトリクス
   - APIレート制限の状況
   - データベース容量

3. **月次確認**
   - 全体的なシステムヘルス
   - コスト最適化の機会
   - アップデートの必要性
