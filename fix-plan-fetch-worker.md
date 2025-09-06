# Stock API 修正プラン

## 1. エグゼクティブサマリー

### 検出された問題
1. **P1 Critical**: Fetch Workerのトランザクション管理エラー
2. **P2 High**: 日付範囲ロジックエラー（GLD銘柄）
3. **P3 Medium**: YFinance API警告

### 影響範囲
- **P1**: すべてのバックグラウンドフェッチジョブが動作不能
- **P2**: 古いデータがないシンボルでAPIがエラーレスポンスを返す
- **P3**: ログに警告が出力され続ける

---

## 2. 問題1: Fetch Workerトランザクション管理（P1 Critical）

### WHY（なぜ問題か）
- SQLAlchemyで`session.begin()`コンテキスト内で`session.commit()`を呼ぶと`InvalidRequestError`が発生
- バックグラウンドジョブが最初のステータス更新で失敗し、データ取得が一切実行されない

### WHAT（何を修正するか）
- トランザクション管理の重複を解消
- セッション管理とトランザクション管理を分離

### AS-IS（現状）
```python
# app/services/fetch_worker.py
async def process_fetch_job(...):
    async with SessionLocal() as session:
        async with session.begin():  # ← 問題：外側でトランザクション開始
            try:
                await update_job_status(session, ...)  # ← 内部でcommit()実行 → エラー

# app/services/fetch_jobs.py
async def update_job_status(session, ...):
    # ...
    await session.commit()  # ← session.begin()内でのcommitはエラー
```

### TO-BE（修正後）
```python
# app/services/fetch_worker.py
async def process_fetch_job(...):
    async with SessionLocal() as session:
        # session.begin()を削除、各関数が独自にトランザクション管理
        try:
            await update_job_status(session, ...)  # 内部でcommit実行可能
```

---

## 3. 問題2: 日付範囲ロジックエラー（P2 High）

### WHY（なぜ問題か）
- GLD（2004年上場）のような銘柄で1990年のデータを要求すると、自動調整で2010年に変更
- しかし終了日（2001年）より後になってしまい、YFinanceがエラーを返す
- APIクライアントに500エラーが返される

### WHAT（何を修正するか）
- 自動調整された開始日が終了日を超える場合の処理を追加
- エラーメッセージを改善してクライアントに適切な情報を提供

### AS-IS（現状）
```python
# app/db/queries.py
async def ensure_coverage_with_auto_fetch(...):
    actual_start = await find_earliest_available_date(symbol, date_from)
    # actual_start > date_to のチェックなし
    df = await fetch_prices_df(symbol=symbol, start=actual_start, end=date_to)
    # → start > end でYFinanceエラー
```

### TO-BE（修正後）
```python
async def ensure_coverage_with_auto_fetch(...):
    actual_start = await find_earliest_available_date(symbol, date_from)
    
    # 自動調整された開始日が終了日より後の場合
    if actual_start > date_to:
        logger.warning(f"Symbol {symbol}: No data available in range {date_from} to {date_to}")
        result_meta["adjustments"][symbol] = f"No data available before {actual_start}"
        continue  # このシンボルをスキップ
    
    # 正常なケース
    df = await fetch_prices_df(symbol=symbol, start=actual_start, end=date_to)
```

---

## 4. 問題3: YFinance API警告（P3 Medium）

### WHY（なぜ問題か）
- YFinanceライブラリの新バージョンで`auto_adjust`のデフォルトがTrueに変更
- 明示的に指定しないと警告が出力される
- ログが警告で埋まり、重要なエラーを見逃す可能性

### WHAT（何を修正するか）
- すべての`yf.download()`呼び出しで`auto_adjust=True`を明示的に指定

### AS-IS（現状）
```python
# app/services/fetcher.py
df = yf.download(
    symbol,
    start=fetch_start,
    end=fetch_end,
    # auto_adjust省略 → 警告
    progress=False,
    timeout=settings.FETCH_TIMEOUT_SECONDS,
)
```

### TO-BE（修正後）
```python
df = yf.download(
    symbol,
    start=fetch_start,
    end=fetch_end,
    auto_adjust=True,  # 明示的に指定
    progress=False,
    timeout=settings.FETCH_TIMEOUT_SECONDS,
)
```

---

## 5. 実装ファイル一覧

### 修正対象ファイル
1. **app/services/fetch_worker.py**
   - L43-44: `async with session.begin():`を削除
   - インデントを調整

2. **app/db/queries.py**
   - L235-250: `ensure_coverage_with_auto_fetch`に日付チェック追加
   - L196-210: `find_earliest_available_date`の改善

3. **app/services/fetcher.py**
   - L58, L79: `auto_adjust=True`を明示的に追加

4. **app/services/fetch_worker.py（追加修正）**
   - L162: `ticker.history()`にも`auto_adjust=True`を確認

---

## 6. テスト方針

### 単体テスト
```python
# test_fetch_worker.py
async def test_process_fetch_job_transaction():
    """トランザクションエラーが発生しないことを確認"""
    job_id = await create_test_job()
    await process_fetch_job(job_id, ["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
    job = await get_job_status(session, job_id)
    assert job.status in ["completed", "completed_with_errors"]

# test_coverage.py
async def test_auto_fetch_date_validation():
    """開始日が終了日より後の場合の処理を確認"""
    result = await ensure_coverage_with_auto_fetch(
        session, ["GLD"], date(1990, 1, 1), date(2001, 1, 1)
    )
    assert "No data available" in result["adjustments"].get("GLD", "")
```

### 統合テスト
```bash
# APIエンドポイントテスト
curl -X GET "http://localhost:8000/v1/prices?symbols=GLD&from=1990-01-01&to=2001-01-01"
# Expected: 200 OK with empty data or appropriate message

curl -X POST "http://localhost:8000/v1/fetch" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL"], "date_from": "2024-01-01", "date_to": "2024-01-31"}'
# Expected: 200 OK with job_id
```

---

## 7. リスク評価

### リスク項目
1. **既存ジョブへの影響**: 実行中のジョブはそのまま失敗する（修正後は新規ジョブから正常動作）
2. **データ整合性**: トランザクション粒度が変わるが、各操作は原子性を保つ
3. **パフォーマンス**: 複数コミットになるが、長時間実行ジョブには適切

### 軽減策
1. デプロイ前に失敗したジョブをクリーンアップ
2. 段階的ロールアウト（カナリアデプロイ）
3. モニタリング強化（エラー率、ジョブ完了率）

---

## 8. デプロイ手順

### Step 1: 事前準備
```sql
-- 失敗したジョブのクリーンアップ
UPDATE fetch_jobs 
SET status = 'cancelled' 
WHERE status = 'processing' 
  AND started_at < NOW() - INTERVAL '1 hour';
```

### Step 2: コード修正
1. ローカルで修正実装
2. テスト実行（単体・統合）
3. PRレビュー

### Step 3: デプロイ
```bash
# Renderへのデプロイ
git push origin main
# 自動デプロイが開始

# ヘルスチェック
curl https://your-api.onrender.com/healthz
```

### Step 4: 検証
```bash
# 新規ジョブの作成と確認
curl -X POST https://your-api.onrender.com/v1/fetch ...
curl -X GET https://your-api.onrender.com/v1/fetch/{job_id}
```

---

## 10. 成功基準（定量的KPI）

### 必須達成指標（デプロイ後1時間以内）
- [ ] **P1修正**: ジョブ成功率 > 95%（直近10ジョブ）
- [ ] **P2修正**: GLD等のシンボルで200レスポンス確認
- [ ] **P3修正**: YFinance警告ゼロ（ログ確認）
- [ ] **API安定性**: 5xxエラー率 < 1%
- [ ] **レスポンス時間**: p95 < 3秒（価格API）

### 監視ダッシュボード設定
```python
# Prometheus/Grafana メトリクス例
metrics = {
    "fetch_job_success_rate": "rate(fetch_jobs_completed[5m])",
    "api_error_rate": "rate(http_requests_total{status=~'5..'}[5m])",
    "response_time_percentile": "histogram_quantile(0.95, http_request_duration_seconds)",
    "yfinance_warnings": "count(log_messages{level='WARNING', message=~'.*auto_adjust.*'})"
}
```

### 外部アプリケーション検証
```bash
# 統合テストスクリプト
#!/bin/bash
set -e

API_URL="https://your-api.onrender.com"

# Test 1: ジョブ作成と実行
JOB_ID=$(curl -s -X POST "$API_URL/v1/fetch" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL"], "date_from": "2024-01-01", "date_to": "2024-01-31"}' \
  | jq -r '.job_id')

echo "Created job: $JOB_ID"
sleep 10

# Test 2: ジョブステータス確認
STATUS=$(curl -s "$API_URL/v1/fetch/$JOB_ID" | jq -r '.status')
if [[ "$STATUS" == "failed" ]]; then
  echo "❌ Job failed"
  exit 1
fi

# Test 3: 境界条件テスト（GLD）
RESPONSE=$(curl -s -w "\n%{http_code}" "$API_URL/v1/prices?symbols=GLD&from=1990-01-01&to=2001-01-01")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
if [[ "$HTTP_CODE" != "200" ]]; then
  echo "❌ GLD test failed with HTTP $HTTP_CODE"
  exit 1
fi

echo "✅ All tests passed"
```

---

## 11. ロールバック計画（詳細版）

### 自動ロールバックトリガー
```yaml
# monitoring/rollback-triggers.yaml
triggers:
  - name: "high_error_rate"
    condition: "error_rate > 10%"
    duration: "5m"
    action: "auto_rollback"
    
  - name: "job_failure_spike"
    condition: "job_success_rate < 50%"
    duration: "3m"
    action: "alert_then_rollback"
    
  - name: "api_timeout"
    condition: "p99_latency > 10s"
    duration: "5m"
    action: "manual_review"
```

### 手動ロールバック手順
```bash
# 1. Renderダッシュボードでのロールバック
# Deploy History → Select Previous Version → Rollback

# 2. Git revertでのロールバック
git revert HEAD --no-edit
git push origin main

# 3. 緊急時のデータベースロールバック
psql $DATABASE_URL << EOF
-- ジョブ状態のリセット
UPDATE fetch_jobs 
SET status = 'cancelled'
WHERE status = 'processing' 
  AND started_at < NOW() - INTERVAL '1 hour';
EOF
```

### ロールバック後の確認事項
- [ ] ヘルスチェック正常（`/healthz`）
- [ ] 基本API動作確認（`/v1/symbols`, `/v1/prices`）
- [ ] エラーログ確認（新規エラーなし）
- [ ] ジョブキューの状態確認
- [ ] 外部アプリケーションとの連携確認

---

## 7. 修正実装チェックリスト（全問題対応版）

### Phase 1: 実装前準備（30分）
- [ ] 現在のコードのバックアップ作成
- [ ] テスト環境の準備完了
- [ ] 既存ジョブのステータス確認
- [ ] ロールバック手順の確認

### Phase 2: コード修正（90分）
#### P1: トランザクション管理（15分）
- [ ] fetch_worker.py: `session.begin()` 削除
- [ ] インデント調整
- [ ] 関連するヘルパー関数の確認

#### P2: 日付境界条件（30分）
- [ ] queries.py: 日付範囲バリデーション追加
- [ ] エラーメッセージの改善
- [ ] 部分データ取得の処理追加

#### P3: YFinance警告（10分）
- [ ] fetcher.py: `auto_adjust=True` 明示化
- [ ] fetch_worker.py: `ticker.history()` も同様に修正

#### P4: データ可用性（35分）
- [ ] find_earliest_available_date: 二分探索実装
- [ ] ensure_coverage_unified: 新規統一関数作成
- [ ] merge_date_ranges: ユーティリティ追加
- [ ] 既存関数との統合

### Phase 3: テスト実行（60分）
- [ ] P1: トランザクションテスト（10分）
- [ ] P2: 境界条件テスト（15分）
- [ ] P3: 警告確認テスト（5分）
- [ ] P4: DB未登録データテスト（20分）
- [ ] 統合テスト実行（10分）

### Phase 4: デプロイ（30分）
- [ ] ステージング環境へのデプロイ（10分）
- [ ] ステージング検証（10分）
- [ ] 本番環境へのデプロイ（5分）
- [ ] 本番環境初期確認（5分）

### Phase 5: デプロイ後検証（30分）
- [ ] 包括的検証スクリプト実行
- [ ] KPI達成確認
- [ ] ログ監視（エラー・警告）
- [ ] 外部アプリケーション動作確認
- [ ] 1時間後の最終確認

---

## 8. まとめ

### 修正の優先度と推定時間（更新版）
| 優先度 | 問題 | 影響度 | 修正時間 | テスト時間 |
|--------|------|--------|----------|------------|
| **P1** | トランザクション管理 | Critical | 15分 | 10分 |
| **P2** | 日付範囲ロジック | High | 30分 | 15分 |
| **P3** | YFinance警告 | Medium | 10分 | 5分 |
| **P4** | データ可用性判定 | High | 35分 | 20分 |

**総所要時間**: 約4時間（準備30分 + 実装90分 + テスト60分 + デプロイ30分 + 検証30分）

### 📊 期待される改善効果

#### 定量的改善
- **ジョブ成功率**: 0% → 95%以上
- **APIエラー率**: 10% → 1%未満
- **データ完全性**: 60% → 98%以上
- **警告ログ**: 100件/時 → 0件

#### 定性的改善
- **ユーザー体験**: 過去データの完全取得が可能に
- **運用性**: ログ品質向上、監視容易化
- **拡張性**: 統一実装により将来の機能追加が容易
- **信頼性**: 境界条件でも安定動作

### 🎯 成功の定義

**技術的成功**:
- 全4問題の解決確認
- テストカバレッジ90%以上
- パフォーマンス劣化なし

**ビジネス成功**:
- 外部アプリケーションからの100%正常動作
- ユーザークレームゼロ
- データ品質向上

この包括的修正により、Stock APIは**エンタープライズレベルの品質と信頼性**を達成します。