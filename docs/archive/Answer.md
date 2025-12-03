# Stock API 現況回答

## 1. Stock API の現在のステータス

### サービス構成
| 項目 | 値 |
|------|-----|
| **プラットフォーム** | Render |
| **プラン** | **Starter プラン**（常時稼働） |
| **Workers** | 2（Gunicorn + Uvicorn） |
| **Gunicorn タイムアウト** | 60秒 |

✅ **コールドスタート問題はありません**（Free プランではないため）

---

## 2. `auto_fetch=true` の処理時間

### 処理フロー
1. シンボルの自動登録チェック
2. キャッシュチェック（バッチ → 個別）
3. **Yahoo Finance からデータ取得**（← ボトルネック）
4. DB への保存
5. レスポンス返却

### タイムアウト設定（Stock API側）

| 設定項目 | 値 | 説明 |
|---------|------|------|
| `FETCH_TIMEOUT_SECONDS` | **30秒** | Yahoo Finance への1シンボルあたりのタイムアウト |
| `FETCH_MAX_RETRIES` | 3回 | 失敗時のリトライ回数 |
| `YF_REQ_CONCURRENCY` | 8 | 並列フェッチ数 |
| `YF_RATE_LIMIT_REQUESTS_PER_SECOND` | 2.0 | レートリミット（秒間2リクエスト） |
| `YF_RATE_LIMIT_BURST_SIZE` | 10 | バーストサイズ |
| Gunicorn timeout | 60秒 | ワーカータイムアウト |

### 処理時間の見積もり

**最悪ケース（データがDB/キャッシュにない場合）:**

```
1シンボル × 30秒（タイムアウト） × 3回リトライ = 最大90秒
レートリミット（2req/秒）により、10シンボルで約5秒の遅延追加

→ 10シンボル × キャッシュミス時 = 60〜120秒以上
```

⚠️ **これが DM-chart の 120秒タイムアウトでも失敗する原因です。**

---

## 3. API 制限（Rate Limiting）

### Stock API 側の制限

| 設定 | 値 |
|------|-----|
| `API_MAX_SYMBOLS` | **10**（1リクエストあたり） |
| `API_MAX_ROWS` | 50,000 |

### Yahoo Finance 側（Stock API内部）

- Token bucket: 2 req/秒、バースト10
- 指数バックオフ: 最大60秒

**短時間に複数リクエストを送ってもStock API側でスロットリングはされません。**  
ただし、Yahoo Finance へのリクエストは内部でレート制限されています。

---

## 4. 推奨されるリクエスト方法

### ✅ ベストプラクティス

#### A. シンボル数を減らす（推奨: 5以下）

```bash
# 推奨: 1〜5シンボルずつリクエスト
GET /v1/prices?symbols=AAPL,MSFT,GOOGL&from=2024-12-01&to=2024-12-02&auto_fetch=true
```

#### B. `auto_fetch=false` で既存データのみ取得（高速）

```bash
# DBに既にあるデータのみ返す（Yahoo Finance へのアクセスなし）
GET /v1/prices?symbols=AAPL,MSFT,GOOGL&from=2024-12-01&to=2024-12-02&auto_fetch=false
```

#### C. 事前にカバレッジを確認

```bash
# 1. まずカバレッジを確認
GET /v1/coverage?symbols=AAPL,MSFT,GOOGL

# 2. カバレッジがあれば auto_fetch=false で取得
GET /v1/prices?symbols=AAPL,MSFT&from=2024-12-01&to=2024-12-02&auto_fetch=false
```

#### D. Fetch Job を使った非同期取得（大量データ向け）

```bash
# 1. ジョブを作成
POST /v1/fetch
Content-Type: application/json
{
  "symbols": ["AAPL", "MSFT", "GOOGL", ...],
  "date_from": "2024-12-01",
  "date_to": "2024-12-02"
}

# 2. ジョブ状態をポーリング
GET /v1/fetch/{job_id}

# 3. 完了後、auto_fetch=false で取得
GET /v1/prices?symbols=AAPL,MSFT&from=2024-12-01&to=2024-12-02&auto_fetch=false
```

---

## 5. DM-chart 側の推奨設定

### タイムアウト設定の調整

| 設定 | 現在値 | 推奨値 | 理由 |
|------|--------|--------|------|
| 接続タイムアウト | 30秒 | **15秒** | Starterプランなのでコールドスタートなし |
| 読み取りタイムアウト | 120秒 | **180秒** | auto_fetch時の最悪ケースに対応 |
| リトライ回数 | 5回 | **3回** | 5回は過剰、サーバー負荷軽減 |

### 推奨実装パターン

```python
async def fetch_prices_from_stock_api(symbols: List[str], date_from: str, date_to: str):
    """
    Stock API から価格データを取得する推奨実装
    """
    BATCH_SIZE = 5  # 5シンボルずつバッチ処理
    results = []
    
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i:i + BATCH_SIZE]
        symbols_param = ','.join(batch)
        
        # Step 1: まず auto_fetch=false で試行（高速、30秒タイムアウト）
        try:
            response = await fetch_with_timeout(
                url=f"/v1/prices?symbols={symbols_param}&from={date_from}&to={date_to}&auto_fetch=false",
                timeout=30
            )
            if response:
                results.extend(response)
                continue
        except TimeoutError:
            pass
        
        # Step 2: データがなければ auto_fetch=true（180秒タイムアウト）
        try:
            response = await fetch_with_timeout(
                url=f"/v1/prices?symbols={symbols_param}&from={date_from}&to={date_to}&auto_fetch=true",
                timeout=180
            )
            results.extend(response)
        except TimeoutError:
            logger.error(f"Timeout fetching {batch}")
            # 個別にリトライするか、スキップ
    
    return results
```

---

## 6. タイムアウト問題の根本原因

### 原因分析

```
DM-chart リクエスト
    ↓
Stock API (Render Starter)
    ↓
Yahoo Finance API
    ↓ ← ここが遅い（1シンボル最大30秒）
レスポンス
```

| 要因 | 影響 |
|------|------|
| **複数シンボル** | シンボル数に比例して処理時間増加 |
| **キャッシュミス** | Yahoo Finance へのフェッチが発生 |
| **Yahoo Finance 遅延** | 1シンボル30秒、リトライ込みで90秒 |
| **レートリミット** | 秒間2リクエスト制限 |

### 成功しているリクエストとの違い

- ✅ 成功: DBにデータがある（キャッシュヒット）
- ❌ 失敗: 新規シンボルまたは期間（Yahoo Finance フェッチ発生）

---

## 7. まとめ

| 質問 | 回答 |
|------|------|
| **サービス稼働状況** | Starter プラン（常時稼働）、正常構成 |
| **コールドスタート** | **なし**（Free プランではない） |
| **auto_fetch 処理時間** | 1シンボル最大90秒、10シンボルで120秒超の可能性 |
| **推奨シンボル数** | API制限は10、**実用的には5以下を推奨** |
| **Rate Limiting** | Yahoo Finance向けに内部実装済み（2req/秒） |
| **タイムアウト原因** | 複数シンボル × キャッシュミス × Yahoo Finance遅延 |

### 即効性のある対策（優先度順）

1. **`auto_fetch=false` を優先使用**（DB既存データのみ、高速）
2. **シンボル数を5以下に分割**してリクエスト
3. **読み取りタイムアウトを180秒に延長**
4. 定期的に `/v1/coverage` でデータ存在を確認してから取得
5. 大量データは **Fetch Job API** (`POST /v1/fetch`) で非同期処理

---

## 8. 関連エンドポイント一覧

| エンドポイント | 用途 |
|---------------|------|
| `GET /healthz` | ヘルスチェック |
| `GET /v1/prices` | 価格データ取得 |
| `GET /v1/coverage` | データカバレッジ確認 |
| `POST /v1/fetch` | 非同期フェッチジョブ作成 |
| `GET /v1/fetch/{job_id}` | ジョブ状態確認 |
| `GET /v1/symbols` | シンボル一覧 |
