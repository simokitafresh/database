# API Usage Guide 確認後のご質問への回答

作成日: 2025年12月3日

---

## 追加の質問・要望への回答

### 2. レート制限とキューイングの適用範囲

**【ご理解の通りです】**

`auto_fetch=false` の場合、Yahoo Finance への外部API呼び出しは発生しません。したがって：

- **外部APIレート制限（2リクエスト/秒）は適用されません**
- DB参照のみの場合、スロットリングはありません

ただし、以下の点にご留意ください：
- **コネクションプール制限**: Supabase Standard Planの場合、同時接続数に上限があります
- **サーバー側のリクエスト処理能力**: 同時に大量のリクエストを行うと、サーバーリソース（メモリ・CPU）が制約になる可能性があります

**推奨**: 並列リクエストは **5〜10件程度** に抑えることをお勧めします。

---

### 3. Fetch Job API のデータ受渡フロー

**【ご理解の通りです】**

Fetch Job は **非同期データ取り込み** のための機能であり、レスポンスにはステータス情報のみが含まれます。

正しいフロー:
```
POST /v1/fetch (ジョブ作成) 
    ↓
GET /v1/fetch/{job_id} (ステータス確認、status=completed まで待機)
    ↓
GET /v1/prices?auto_fetch=false (DBからデータ取得)
```

---

### 5. ページネーションと大量データ

**【回答】**

現在の `GET /v1/prices` には **ページネーション機能はありません**。200,000行を超えるデータを取得する場合、以下の分割取得を推奨します：

| 方法 | 推奨度 | 説明 |
|------|--------|------|
| **日付範囲で分割** | ⭐⭐⭐ | `from`/`to` パラメータで年単位・四半期単位に分割 |
| **銘柄グループで分割** | ⭐⭐ | 50銘柄ずつのバッチに分割 |

**具体例（100銘柄×20年分 = 約500万行の場合）**:
```python
# 1年ごとに分割して取得
for year in range(2005, 2025):
    response = requests.get(
        f"/v1/prices?symbols={symbols}&from={year}-01-01&to={year}-12-31&auto_fetch=false"
    )
```

---

## データベースに関する質問への回答

### 1. データベースのインデックスについて

**【回答】**

`prices` テーブルには **複合主キー (`symbol`, `date`) が設定されています**。

```python
# app/db/models.py より
class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (
        sa.PrimaryKeyConstraint("symbol", "date"),  # ← 複合主キー = インデックス
        ...
    )
```

PostgreSQL では主キー制約によって **自動的に B-tree インデックスが作成** されるため、`symbol` と `date` での範囲検索は効率的に動作します。

---

### 2. コネクションプーリングについて

**【回答】**

**コネクションプーリングは実装されています**。設定は以下の通りです：

| 設定項目 | 値 | 説明 |
|----------|-----|------|
| `DB_POOL_SIZE` | 5 | プール内の基本接続数 |
| `DB_MAX_OVERFLOW` | 5 | 追加可能な接続数 |
| `DB_POOL_PRE_PING` | True | 接続ヘルスチェック有効 |
| `DB_POOL_RECYCLE` | 900秒 | 接続の再利用期間 |

また、Supabase Pooler（PgBouncer互換）利用時は **NullPool** に自動切替されます：

```python
# app/db/engine.py より
if "pooler.supabase.com" in database_url:
    poolclass = NullPool
    logger.info("Using NullPool for Supabase Pooler mode")
```

---

### 3. クエリの実行効率について

**【回答】**

**一括取得 (`WHERE symbol = ANY(:symbols)`) を採用しています**。

```sql
-- app/db/queries/prices.py より
SELECT ...
FROM prices p
WHERE p.symbol = ANY(:symbols)  -- ← 複数銘柄を一括取得
  AND p.date BETWEEN :date_from AND :date_to
```

PostgreSQL の `ANY` 演算子は内部的に `IN` と同等に最適化され、複合インデックス `(symbol, date)` を活用した効率的なクエリ実行が可能です。

---

### 4. キャッシュの利用について

**【回答】**

キャッシュの詳細設定は以下の通りです：

| 項目 | 設定値 | 説明 |
|------|--------|------|
| **TTL（有効期間）** | **3600秒（1時間）** | `CACHE_TTL_SECONDS` |
| **バックエンド** | Redis（フォールバック: インメモリ） | |
| **最大エントリ数** | 1000（インメモリ時） | |

**キャッシュ対象**:
- クエリ結果（銘柄×日付範囲の組み合わせ）
- 個別キャッシュキー: `prices:{symbol}:{date_from}:{date_to}`
- バッチキャッシュキー: `prices:batch:{symbols}:{date_from}:{date_to}`

**補足**: `auto_fetch=false` の大量取得時もキャッシュは有効ですが、大量データの場合はキャッシュ効果より DB 直接アクセスの方が効率的な場合があります。

---

### 5. 推奨されるリクエスト方法について

**【ご認識の通りで問題ありません】**

ETL処理での推奨フロー:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  POST /v1/fetch │ --> │ GET /v1/fetch/  │ --> │ GET /v1/prices  │
│  (非同期取込)    │     │ {job_id}        │     │ auto_fetch=false│
│                 │     │ (ステータス確認) │     │ (データ取得)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**まとめ表**:

| ユースケース | エンドポイント | パラメータ | 銘柄上限 | 行数上限 |
|-------------|---------------|-----------|---------|---------|
| 通常表示 | `GET /v1/prices` | `auto_fetch=true` (default) | 10 | 50,000 |
| 大量取得（計算用） | `GET /v1/prices` | `auto_fetch=false` | 100 | 200,000 |
| データ補完 | `POST /v1/fetch` | - | 100 | - |

---

## 補足: 関連する設定値一覧

以下は `app/core/config.py` で定義されている関連設定です：

```python
# API制限
API_MAX_SYMBOLS: int = 10           # auto_fetch=true 時の銘柄上限
API_MAX_SYMBOLS_LOCAL: int = 100    # auto_fetch=false 時の銘柄上限
API_MAX_ROWS: int = 50000           # auto_fetch=true 時の行数上限
API_MAX_ROWS_LOCAL: int = 200000    # auto_fetch=false 時の行数上限

# Yahoo Finance レート制限
YF_RATE_LIMIT_REQUESTS_PER_SECOND: float = 2.0
YF_RATE_LIMIT_BURST_SIZE: int = 10

# キャッシュ
CACHE_TTL_SECONDS: int = 3600       # 1時間
ENABLE_CACHE: bool = True

# Fetch Job
FETCH_JOB_MAX_SYMBOLS: int = 100
FETCH_JOB_MAX_DAYS: int = 3650      # 約10年
```

---

ご不明な点がございましたら、お気軽にお問い合わせください。
