# Render.com Cron Job 設定トラブルシューティング

## 問題の概要
`curl: (6) Could not resolve host: https` エラーは、通常以下の原因で発生します：

1. **RENDER_EXTERNAL_URL が正しく設定されていない**
2. **環境変数の値に余分な文字が含まれている**
3. **Render の自動環境変数が利用できない**

## 解決手順

### 1. Render ダッシュボードで環境変数を確認

Render ダッシュボードの **Environment** タブで以下を設定：

```
RENDER_EXTERNAL_URL=https://stockdata-api-6xok.onrender.com
CRON_SECRET_TOKEN=8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA
```

**重要**: 
- `RENDER_EXTERNAL_URL` にはサービスの完全なURLを入力（例: `https://stockdata-api-6xok.onrender.com`）
- 末尾にスラッシュ `/` は付けない
- `http://` ではなく `https://` を使用

### 2. Render の自動環境変数を利用する場合

Render は以下の環境変数を自動で提供します：
- `RENDER_EXTERNAL_HOSTNAME`: サービスのホスト名
- `RENDER_SERVICE_NAME`: サービス名

`RENDER_EXTERNAL_URL` を手動設定しない場合、スクリプトがこれらから自動構築を試みます。

### 3. デバッグ用スクリプトの実行

トラブルシューティングには `scripts/cron_debug.sh` を使用：

```bash
# Render ダッシュボードの Cron Jobs で一時的に実行
bash scripts/cron_debug.sh
```

### 4. よくある設定ミス

❌ **間違った設定例**:
```
RENDER_EXTERNAL_URL=stockdata-api-6xok.onrender.com          # https:// がない
RENDER_EXTERNAL_URL=https://stockdata-api-6xok.onrender.com/ # 末尾の / が余分  
RENDER_EXTERNAL_URL="https://stockdata-api-6xok.onrender.com" # 引用符が余分
```

✅ **正しい設定例**:
```
RENDER_EXTERNAL_URL=https://stockdata-api-6xok.onrender.com
```

### 5. 手動テスト方法

Render の **Shell** タブで以下のコマンドを実行して動作確認：

```bash
# 環境変数確認
echo "URL: $RENDER_EXTERNAL_URL"
echo "Token: ${CRON_SECRET_TOKEN:+SET}"

# 接続テスト
curl -I "$RENDER_EXTERNAL_URL/healthz"

# Cron エンドポイントテスト  
curl -X POST "$RENDER_EXTERNAL_URL/v1/daily-update" \
  -H "X-Cron-Secret: $CRON_SECRET_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

### 6. Cron Job の設定

Render ダッシュボードの **Cron Jobs** で：

- **Command**: `bash scripts/cron_command.sh`
- **Schedule**: `0 2 * * *` (毎日午前2時UTC)

## 現在のエラーの直接的な修正

エラーログから判断すると、`RENDER_EXTERNAL_URL` が正しく設定されていない可能性が高いです。

**即座に試す手順**:
1. Render ダッシュボード → あなたのサービス → **Environment** 
2. `RENDER_EXTERNAL_URL` を追加/編集: `https://stockdata-api-6xok.onrender.com`
3. **Save Changes**
4. Cron Job を手動実行してテスト

修正後、ログに `Using URL: https://...` が正しく表示されるはずです。
