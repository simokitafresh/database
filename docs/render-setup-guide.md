# Render.com でのCron Job設定ガイド

## 1. Web Service設定（既存）

まず、既存のWeb Serviceに新しい環境変数を追加します。

### 環境変数の追加

Render Dashboard → あなたのWeb Service → Environment で以下を追加：

```
CRON_SECRET_TOKEN=8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA
CRON_BATCH_SIZE=50
CRON_UPDATE_DAYS=7
```

### 既存の環境変数確認

以下の変数が設定されていることを確認：
```
DATABASE_URL=(既存値)
YF_REQ_CONCURRENCY=2
FETCH_TIMEOUT_SECONDS=30
PORT=8000
```

## 2. Cron Job Service作成

### Step 1: 新しいサービス作成

1. Render Dashboard で **"New +"** ボタンをクリック
2. **"Cron Job"** を選択
3. 既存のリポジトリ（database）を選択

### Step 2: Cron Job設定

#### Basic Settings:
- **Name**: `stock-data-daily-update`
- **Region**: 既存のWeb Serviceと同じリージョン
- **Branch**: `main`

#### Command Settings:
```bash
bash scripts/cron_command.sh
```

#### Schedule Settings:
- **Schedule**: `0 1 * * *` (毎日 AM 1:00 UTC = AM 10:00 JST)
- **Timezone**: `UTC`

### Step 3: Environment Variables

Cron Jobサービスでも同じ環境変数を設定：

```
CRON_SECRET_TOKEN=8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA
RENDER_EXTERNAL_URL=https://your-app-name.onrender.com
```

**重要**: `RENDER_EXTERNAL_URL`は既存のWeb ServiceのURLを設定

## 3. 設定確認手順

### 3.1 Web Service動作確認（必須ステップ）

#### Step 1: 基本的なヘルスチェック
```bash
# あなたのRender App URLに置き換えて実行
curl https://your-app-name.onrender.com/v1/health
```

**期待される応答:**
```json
{
  "status": "ok",
  "service": "Stock OHLCV API", 
  "scope": "v1"
}
```

#### Step 2: Swagger UI確認
ブラウザで以下にアクセス:
```
https://your-app-name.onrender.com/docs
```

**確認ポイント:**
- [ ] ページが正常に表示される
- [ ] `/v1/daily-update` エンドポイントが表示される
- [ ] `/v1/status` エンドポイントが表示される
- [ ] 両方のエンドポイントに🔒マークが表示される（認証必要）

#### Step 3: 環境変数の動作確認
```bash
# 設定値確認（トークンなしでアクセス）
curl -X GET "https://your-app-name.onrender.com/v1/status"
```

**期待される応答（CRON_SECRET_TOKENが設定済みの場合）:**
```json
{
  "detail": {
    "error": {
      "code": "MISSING_AUTH",
      "message": "Missing X-Cron-Secret header"
    }
  }
}
```
→ この401エラーは**正常**（認証が機能している証拠）

### 3.2 Cron Job手動テスト（段階的テスト）

#### Step 1: ドライランテスト
```bash
curl -X POST "https://your-app-name.onrender.com/v1/daily-update" \
  -H "X-Cron-Secret: 8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

**期待される成功応答:**
```json
{
  "status": "dry_run",
  "message": "Dry run completed", 
  "total_symbols": 27,
  "batch_count": 1,
  "date_range": {
    "from": "2025-09-02",
    "to": "2025-09-08"
  },
  "timestamp": "2025-09-09T01:00:00.123456"
}
```

**チェックポイント:**
- [ ] `status: "dry_run"` が表示される
- [ ] `total_symbols` が0より大きい
- [ ] `batch_count` が1以上
- [ ] エラーが返されない

#### Step 2: ステータスエンドポイント確認
```bash
curl -X GET "https://your-app-name.onrender.com/v1/status" \
  -H "X-Cron-Secret: 8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA"
```

**期待される応答:**
```json
{
  "status": "active",
  "last_run": null,
  "recent_job_count": 0,
  "job_status_counts": {},
  "settings": {
    "batch_size": 50,
    "update_days": 7,
    "yf_concurrency": 4
  }
}
```

**設定値確認:**
- [ ] `settings.batch_size: 50`
- [ ] `settings.update_days: 7` 
- [ ] 200 OKステータスコード

#### Step 3: Render Dashboard での手動実行

1. **Render Dashboard にログイン**
2. **Cron Job サービス (`stock-data-daily-update`) を選択**
3. **"Manual Jobs" セクション** を確認
4. **"Trigger Job" ボタンをクリック**

**実行後の確認:**
- [ ] Job Status: "Running" → "Succeeded"
- [ ] 実行時間: 1-3分程度
- [ ] Logs にエラーが表示されない

#### Step 4: ログの確認

**Render Dashboard → Logs タブ** で以下を確認:

**成功時のログ例:**
```
[2025-09-09 01:00:00] Starting daily stock data update cron job
[2025-09-09 01:00:01] Executing daily update endpoint...
[2025-09-09 01:00:02] Cron job completed successfully
[2025-09-09 01:00:02] Response: {"status":"success",...}
[2025-09-09 01:00:02] Job status: success
[2025-09-09 01:00:02] Daily stock data update completed
```

### 3.3 エラー時の対処法

#### 認証エラー (401/403)
```bash
# トークンの確認
curl -X POST "https://your-app-name.onrender.com/v1/daily-update" \
  -H "X-Cron-Secret: wrong-token" \
  -d '{"dry_run": true}'
```
→ 403エラーが返されることを確認（正常な動作）

**解決方法:**
1. Render Dashboard → Environment でトークンを確認
2. Web Service と Cron Job で同じトークンを使用
3. トークンに特殊文字が含まれていないか確認

#### タイムアウトエラー
**症状:** Job が長時間 "Running" のまま
**解決方法:**
1. `CRON_BATCH_SIZE` を50から25に縮小
2. `scripts/cron_command.sh` の `--max-time` を延長

#### データベース接続エラー
**症状:** 500エラーまたは Database connection failed
**解決方法:**
1. `DATABASE_URL` 環境変数の確認
2. Web Service でのデータベース接続テスト:
```bash
curl "https://your-app-name.onrender.com/v1/symbols?limit=1"
```

### 3.4 実際の実行テスト（注意して実行）

**警告:** これは実際にデータ取得を開始します

```bash
curl -X POST "https://your-app-name.onrender.com/v1/daily-update" \
  -H "X-Cron-Secret: 8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

**実行前チェックリスト:**
- [ ] ドライランが成功している
- [ ] データベース容量に余裕がある
- [ ] 平日の営業時間外に実行
- [ ] ログ監視の準備ができている

**実行後の確認:**
- [ ] `status: "success"` が返される
- [ ] `job_ids` 配列に値が入っている
- [ ] 推定完了時間内に処理が完了する

## 4. スケジュール設定例

### 推奨スケジュール
```
0 1 * * *    # 毎日 AM 1:00 UTC (AM 10:00 JST)
```

### その他のオプション
```
0 1 * * 1-5  # 平日のみ AM 1:00 UTC
0 1,13 * * * # 1日2回 AM 1:00, PM 1:00 UTC
0 2 * * *    # 毎日 AM 2:00 UTC (AM 11:00 JST)
```

## 5. モニタリング設定

### Log確認
- Render Dashboard → Cron Job Service → Logs
- 実行結果とエラーを確認

### 通知設定（オプション）
- Render Dashboard → Settings → Notifications
- Slack/Email通知を設定可能

## 6. エラー対処

### よくある問題と解決方法

#### 1. 認証エラー (401/403)
```bash
# 環境変数確認
echo $CRON_SECRET_TOKEN
echo $RENDER_EXTERNAL_URL
```

#### 2. タイムアウトエラー
- `scripts/cron_command.sh`の`--max-time`を延長
- バッチサイズ(`CRON_BATCH_SIZE`)を縮小

#### 3. データベース接続エラー
- `DATABASE_URL`が正しく設定されているか確認
- Web ServiceとCron Jobで同じDATABASE_URLを使用

## 7. セキュリティベストプラクティス

### Token管理
- 定期的にCRON_SECRET_TOKENを再生成
- 新しいトークン生成: `python scripts/generate_token.py`

### アクセス制御
- HTTPSのみ使用（Renderは自動でHTTPS）
- トークンをログに出力しない

## 8. 本番運用チェックリスト

### 初回デプロイ前
- [ ] Web Serviceに3つの環境変数追加
- [ ] Cron Jobサービス作成
- [ ] 手動テスト実行成功
- [ ] ドライラン実行成功

### 運用開始後
- [ ] 初回自動実行の確認
- [ ] ログ監視設定
- [ ] エラー通知設定
- [ ] パフォーマンス監視

## 9. トラブルシューティング

### デバッグコマンド

```bash
# ステータス確認
curl -X GET "https://your-app-name.onrender.com/v1/status" \
  -H "X-Cron-Secret: 8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA"

# 手動ドライラン
curl -X POST "https://your-app-name.onrender.com/v1/daily-update" \
  -H "X-Cron-Secret: 8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA" \
  -d '{"dry_run": true}'
```

### ログ分析
- 成功時: `"status": "success"`
- エラー時: `"error"` フィールドで詳細確認

**注意**: `your-app-name`を実際のRender App名に置き換えてください。
