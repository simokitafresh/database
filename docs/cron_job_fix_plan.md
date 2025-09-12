# Cronジョブデータ更新問題 - 修正プラン

## 1. Why（なぜ修正が必要か）

### 1.1 根本原因
- **cronジョブがシミュレーションモードで動作している**
  - `app/api/v1/cron.py`の`daily_update`関数が実際のデータ取得処理を実装していない
  - `dry_run=false`でも「simulated」というメッセージが返されている
  - TODOコメント「Implement actual batch processing for non-dry-run」が残されたまま

### 1.2 ビジネスへの影響
- **データの鮮度が保たれない**
  - 株価データが自動更新されず、古いデータのままになる
  - ユーザーが最新の株価情報を取得できない
  - データの信頼性が損なわれる

### 1.3 技術的な問題
- **手動でのデータ更新が必要**
  - APIエンドポイント経由で個別にデータを取得する必要がある
  - 運用負荷が高い
  - スケーラビリティの問題

### 1.4 ログと実際の動作の乖離
```
[2025-09-12 01:00:41] Response: {"status":"success","message":"Processed 36 symbols successfully (simulated)",...}
```
- ログ上は「success」だが、実際にはデータベースは更新されていない
- 「simulated」という文言が実装未完了を示している

## 2. What（何を修正するか）

### 2.1 主要な修正対象
1. **`app/api/v1/cron.py`の`daily_update`関数**
   - シミュレーション処理を実際のデータ取得処理に置き換える
   - バッチ処理の実装

2. **データ取得処理の統合**
   - 既存の`ensure_coverage`関数を活用
   - Yahoo Financeからのデータ取得
   - Supabaseへのデータ保存

3. **エラーハンドリングの強化**
   - 個別シンボルの失敗を適切に処理
   - 部分的な成功を許容

### 2.2 活用する既存コンポーネント
- `app/db/queries.py::ensure_coverage()` - データ取得と保存の統合処理
- `app/services/fetcher.py::fetch_prices()` - Yahoo Financeからのデータ取得
- `app/services/upsert.py::upsert_prices_sql()` - データベースへのUPSERT
- `app/db/utils.py::advisory_lock()` - 同時実行制御

## 3. As-Is（現状）

### 3.1 現在のコードフロー

```python
# app/api/v1/cron.py (現状)

async def daily_update(request, background_tasks, session, authenticated):
    # 1. データベース接続確認
    await session.execute(text("SELECT 1"))
    
    # 2. アクティブシンボルの取得
    all_symbols = await list_symbols(session, active=True)
    
    # 3. dry_runチェック
    if request.dry_run:
        return CronDailyUpdateResponse(...)  # dry_run結果を返す
    
    # 4. ⚠️ 問題箇所：実際の処理が未実装
    # TODO: Implement actual batch processing for non-dry-run
    logger.info("Simulating batch processing (actual implementation pending)")
    
    # 5. シミュレーション結果を返す（データ更新なし）
    return CronDailyUpdateResponse(
        status="success",
        message=f"Processed {len(all_symbols)} symbols successfully (simulated)",
        ...
    )
```

### 3.2 現在の動作
1. cronジョブが定期実行される（Render Cron Jobs）
2. `/v1/daily-update`エンドポイントが呼ばれる
3. アクティブシンボルのリストを取得
4. **実際のデータ取得処理をスキップ**
5. 「simulated」という成功レスポンスを返す
6. **データベースは更新されない**

### 3.3 現在の問題点詳細
- **データ取得処理が呼ばれない**
  ```python
  # 以下の処理が実行されていない
  - fetch_prices_df()  # Yahoo Financeからデータ取得
  - upsert_prices_sql()  # データベースへの保存
  - ensure_coverage()  # 統合処理
  ```

- **バッチ処理が未実装**
  ```python
  # バッチ分割のコードはあるが使われていない
  batches = [all_symbols[i:i + batch_size] for i in range(0, total_symbols, batch_size)]
  ```

- **エラーハンドリングが不十分**
  - 個別シンボルの失敗が全体を止める可能性

## 4. To-Be（あるべき姿）

### 4.1 修正後のコードフロー

```python
# app/api/v1/cron.py (修正後)

async def daily_update(request, background_tasks, session, authenticated):
    # 1. データベース接続確認
    await session.execute(text("SELECT 1"))
    
    # 2. アクティブシンボルの取得
    all_symbols_data = await list_symbols(session, active=True)
    all_symbols = [row["symbol"] for row in all_symbols_data]
    
    # 3. 日付範囲の計算
    date_from = date.today() - timedelta(days=settings.CRON_UPDATE_DAYS)
    date_to = date.today() - timedelta(days=1)  # 昨日まで
    
    # 4. dry_runチェック
    if request.dry_run:
        return CronDailyUpdateResponse(...)  # dry_run結果を返す
    
    # 5. ✅ 実際のデータ取得処理
    success_count = 0
    failed_symbols = []
    
    # バッチ処理
    batch_size = settings.CRON_BATCH_SIZE
    for i in range(0, len(all_symbols), batch_size):
        batch = all_symbols[i:i + batch_size]
        
        for symbol in batch:
            try:
                # データ取得と保存（既存関数を活用）
                await ensure_coverage(
                    session=session,
                    symbols=[symbol],
                    date_from=date_from,
                    date_to=date_to,
                    refetch_days=settings.YF_REFETCH_DAYS
                )
                await session.commit()
                success_count += 1
                logger.info(f"Updated {symbol} successfully")
                
            except Exception as e:
                logger.error(f"Failed to update {symbol}: {e}")
                failed_symbols.append(symbol)
                await session.rollback()
                continue
    
    # 6. 実際の結果を返す
    status = "success" if not failed_symbols else "completed_with_errors"
    message = f"Updated {success_count}/{len(all_symbols)} symbols"
    
    return CronDailyUpdateResponse(
        status=status,
        message=message,
        total_symbols=len(all_symbols),
        batch_count=(len(all_symbols) + batch_size - 1) // batch_size,
        date_range={"from": str(date_from), "to": str(date_to)},
        timestamp=start_time.isoformat()
    )
```

### 4.2 修正後の動作フロー

1. **cronジョブ実行**
   - Render Cron Jobsが定期的に`scripts/cron_command.sh`を実行
   - `/v1/daily-update`エンドポイントを呼び出し

2. **データ準備**
   - アクティブシンボルのリストを取得（36シンボル）
   - 更新対象期間を計算（過去7日分）

3. **バッチ処理でデータ更新**
   ```
   バッチ1 (1-50シンボル) → Yahoo Finance → Supabase
   バッチ2 (51-100シンボル) → Yahoo Finance → Supabase
   ...
   ```

4. **個別シンボル処理**
   - 各シンボルごとに`ensure_coverage`を実行
   - Yahoo Financeからデータ取得
   - Supabaseにデータ保存（UPSERT）
   - エラーが発生しても次のシンボルを処理

5. **結果の集計と報告**
   - 成功/失敗の統計
   - 適切なステータスコード
   - 詳細なログ出力

### 4.3 期待される結果

#### 4.3.1 正常系
```json
{
  "status": "success",
  "message": "Updated 36/36 symbols",
  "total_symbols": 36,
  "batch_count": 1,
  "date_range": {
    "from": "2025-09-05",
    "to": "2025-09-11"
  },
  "timestamp": "2025-09-12T01:00:40.177425"
}
```

#### 4.3.2 部分的成功
```json
{
  "status": "completed_with_errors",
  "message": "Updated 34/36 symbols",
  "total_symbols": 36,
  "batch_count": 1,
  "failed_symbols": ["INVALID1", "DELISTED2"],
  "date_range": {
    "from": "2025-09-05",
    "to": "2025-09-11"
  },
  "timestamp": "2025-09-12T01:00:40.177425"
}
```

### 4.4 実装の優先順位

1. **Phase 1: 基本実装**（必須）
   - `ensure_coverage`を使った実際のデータ取得
   - 基本的なエラーハンドリング
   - ログ出力の改善

2. **Phase 2: バッチ最適化**（推奨）
   - 並行処理の導入（asyncio.gather）
   - バッチサイズの動的調整
   - リトライ機構

3. **Phase 3: 監視と通知**（将来）
   - 失敗通知（Slack/Email）
   - パフォーマンスメトリクス
   - ダッシュボード連携

## 5. 実装詳細

### 5.1 必要な変更ファイル

1. **`app/api/v1/cron.py`**
   - `daily_update`関数の実装
   - 約100行の変更

2. **`app/schemas/cron.py`**（オプション）
   - レスポンススキーマに`failed_symbols`フィールド追加
   - 約5行の追加

### 5.2 既存機能の活用

```python
# 既存の関数をそのまま使用
from app.db.queries import ensure_coverage  # データ取得と保存
from app.db.queries import list_symbols     # シンボルリスト取得

# 設定値の活用
from app.core.config import settings
# - settings.CRON_BATCH_SIZE: 50
# - settings.CRON_UPDATE_DAYS: 7
# - settings.YF_REFETCH_DAYS: 7
```

### 5.3 データベーストランザクション

```python
# シンボルごとに独立したトランザクション
for symbol in batch:
    try:
        await ensure_coverage(...)
        await session.commit()  # 成功したら即座にコミット
    except Exception:
        await session.rollback()  # 失敗してもロールバック
        continue  # 次のシンボルへ
```

### 5.4 パフォーマンス考慮事項

- **並行度の制限**
  - Yahoo Finance APIの制限を考慮
  - `YF_REQ_CONCURRENCY=2`の設定を尊重

- **タイムアウト設定**
  - 各シンボル: 30秒
  - 全体: 3600秒（1時間）

- **メモリ使用量**
  - バッチサイズを50に制限
  - データフレームの適切な解放

## 6. テスト計画

### 6.1 単体テスト
```bash
# dry_runモード
curl -X POST "https://stockdata-api-6xok.onrender.com/v1/daily-update" \
  -H "X-Cron-Secret: ${CRON_TOKEN}" \
  -d '{"dry_run": true}'

# 実行モード（少数のシンボルでテスト）
curl -X POST "https://stockdata-api-6xok.onrender.com/v1/daily-update" \
  -H "X-Cron-Secret: ${CRON_TOKEN}" \
  -d '{"dry_run": false, "test_symbols": ["AAPL", "MSFT"]}'
```

### 6.2 統合テスト
1. テスト環境でcronジョブ実行
2. データベースの更新確認
3. ログの確認

### 6.3 本番デプロイ
1. コード変更のコミット
2. Renderへの自動デプロイ
3. cronジョブの実行確認
4. Supabaseでデータ更新確認

## 7. リスクと対策

### 7.1 リスク
1. **Yahoo Finance APIレート制限**
   - 対策: バッチサイズとconcurrencyの調整

2. **データベース接続プール枯渇**
   - 対策: プールサイズの適切な設定

3. **長時間実行によるタイムアウト**
   - 対策: タイムアウト値の調整

### 7.2 ロールバック計画
- Git revertでコードを戻す
- Renderの手動デプロイで前バージョンに戻す
- cronジョブの一時停止

## 8. 成功指標

### 8.1 技術的指標
- cronジョブ成功率: >95%
- 平均実行時間: <5分（36シンボル）
- エラー率: <5%

### 8.2 ビジネス指標
- データ鮮度: 24時間以内
- データ完全性: 100%
- 自動化率: 100%

## 9. まとめ

### 現状の問題
- cronジョブが「シミュレーション」で動作し、実際のデータ更新が行われていない

### 解決策
- `daily_update`関数に実際のデータ取得処理を実装
- 既存の`ensure_coverage`関数を活用
- 適切なエラーハンドリングとバッチ処理

### 期待効果
- 株価データの自動更新が実現
- 運用負荷の削減
- データの信頼性向上
