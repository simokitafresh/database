# APIおよびデータベースに関する質問への回答

お問い合わせいただきありがとうございます。タイムアウトやInternal Server Errorの発生についてご不便をおかけしており申し訳ございません。以下、各ご質問に対する回答をご案内いたします。

---

## 1. データベースのインデックスについて

### 現在の設定状況

**はい、インデックスは設定されております。**

本システムでは、`prices` テーブルに対して以下のインデックス構成を採用しております：

| インデックス名 | 対象カラム | 種別 |
|---|---|---|
| `PRIMARY KEY` | `(symbol, date)` | 複合主キー（B-tree） |
| `idx_prices_symbol_date_btree` | `(symbol, date)` | 複合インデックス |
| `idx_prices_last_updated` | `last_updated` | 単一カラムインデックス |

また、関連テーブルにも以下のインデックスが設定されております：

- `symbol_changes` テーブル：`idx_symbol_changes_old`、`idx_symbol_changes_new`
- `fetch_jobs` テーブル：`idx_fetch_jobs_status`、`idx_fetch_jobs_created`

**ご要望の `symbol` + `date` での範囲検索については、複合主キーおよび `idx_prices_symbol_date_btree` インデックスにより最適化されております。**

---

## 2. コネクションプーリングについて

### 現在の設定状況

**コネクションプーリングを導入しております。**

本システムでは、以下の構成でデータベース接続を管理しております：

| 項目 | 設定値 |
|---|---|
| 接続方式 | SQLAlchemy Async + asyncpg |
| プーリング | Supabase Pooler (PgBouncer) + NullPool |
| プールサイズ | 5接続 |
| 最大オーバーフロー | 5接続 |
| 接続リサイクル | 900秒（15分） |
| Pre-ping | 有効（接続ヘルスチェック） |

#### Supabase Pooler使用時の特記事項
- Supabase Pooler（PgBouncer）接続時は、`NullPool` を使用し、接続プーリングはサーバー側で管理
- ステートメントキャッシュは無効化（PgBouncer互換性のため）

### 推奨同時接続数

クライアント側での並列リクエストについては、以下を推奨いたします：

| 項目 | 推奨値 |
|---|---|
| 同時接続数 | **最大 4〜8 並列** |
| リクエスト間隔 | **0.5〜1秒以上** |

※ バックエンド側でYahoo Finance APIへのレート制限（2リクエスト/秒、バースト上限10）を設けているため、過度な並列リクエストはキューイングされます。

---

## 3. クエリの実行効率について

### 現在の実装状況

**一括取得（WHERE symbol IN (...)）を採用しております。**

複数銘柄を指定した場合、以下のようなSQLで一括取得を行っております：

```sql
SELECT DISTINCT
    pr.symbol, pr.date, pr.open, pr.high, pr.low, pr.close,
    pr.volume, pr.source, pr.last_updated, pr.source_symbol
FROM (
    SELECT p.symbol, p.date, p.open, p.high, p.low, p.close,
           p.volume, p.source, p.last_updated, NULL::text AS source_symbol
    FROM prices p
    LEFT JOIN symbol_changes sc ON sc.new_symbol = p.symbol
    WHERE p.symbol = ANY(:symbols)
      AND p.date BETWEEN :date_from AND :date_to
    ...
) pr
ORDER BY pr.symbol, pr.date;
```

### パフォーマンス最適化

本システムでは **QueryOptimizer** を導入しており、CTEベースのSQL最適化により **50〜70%のパフォーマンス向上** を実現しております。

ただし、**1リクエストあたりの銘柄数には制限** があります：

| パラメータ | 設定値 |
|---|---|
| `API_MAX_SYMBOLS` | **10**（1リクエストあたり） |
| `API_MAX_ROWS` | **50,000行**（1リクエストあたり） |

50〜100銘柄を取得される場合は、**複数リクエストに分割** していただく必要がございます。

---

## 4. キャッシュの利用について

### 現在の設定状況

**Redis キャッシュ層を実装しております。**

| 項目 | 設定値 |
|---|---|
| キャッシュ方式 | Redis（フォールバック：インメモリキャッシュ） |
| キャッシュTTL | **3,600秒（1時間）** |
| キャッシュ有効 | デフォルト有効 |

### キャッシュの動作

1. **Redisが利用可能な場合**：Redis上にキャッシュを保存（TTL: 1時間）
2. **Redis利用不可の場合**：インメモリキャッシュにフォールバック（最大1,000エントリ）

### プリフェッチ機能

主要銘柄については、バックグラウンドで定期的にデータをプリフェッチしております：

- **対象銘柄**: `TQQQ, TECL, GLD, XLU, ^VIX, QQQ, SPY, TMV, TMF, LQD`
- **更新間隔**: 5分

### ヒストリカルデータの取得効率化

- 各シンボルに対して初回リクエスト時に **フルヒストリー（1970年〜現在）** を一括取得・保存
- 以降のリクエストではDBから直接取得（外部API呼び出し不要）
- 直近データのみリフレッシュ（`YF_REFETCH_DAYS`: 7日）

---

## 5. 推奨されるリクエスト方法について

### タイムアウト回避のための推奨設定

| 項目 | 推奨値 | 備考 |
|---|---|---|
| **1リクエストあたりの銘柄数** | **5〜10銘柄** | 上限: 10銘柄 |
| **並列リクエスト数** | **2〜4並列** | 推奨: 2並列 |
| **リクエスト間隔** | **1秒以上** | バースト時は2秒以上 |
| **期間指定** | **1年以内** | 長期間は分割推奨 |
| **クライアント側タイムアウト** | **60秒以上** | サーバー側: 30秒 |

### 具体的な推奨パターン

#### パターン1: 少数銘柄・長期間
```
GET /v1/prices?symbols=AAPL,MSFT&from=2020-01-01&to=2024-12-31
```
- 銘柄数: 2〜5
- 期間: 最大5年程度

#### パターン2: 多数銘柄・短期間
```
GET /v1/prices?symbols=AAPL,MSFT,GOOGL,AMZN,META,NVDA,TSLA,AMD,NFLX,INTC&from=2024-01-01&to=2024-12-31
```
- 銘柄数: 最大10（上限）
- 期間: 1年以内

#### パターン3: 大量データ取得（ジョブAPI使用）

50〜100銘柄の取得には、**Fetch Job API** のご利用を推奨いたします：

```bash
# ジョブ作成
POST /v1/fetch
{
  "symbols": ["AAPL", "MSFT", ...],  # 最大100銘柄
  "start_date": "2020-01-01",
  "end_date": "2024-12-31"
}

# ジョブ状態確認
GET /v1/fetch/{job_id}
```

ジョブAPIを使用することで：
- バックグラウンドで非同期処理
- タイムアウトを回避
- 進捗状況の追跡が可能

### エラー発生時の対処

| エラー | 推奨対処 |
|---|---|
| **429 Too Many Requests** | 30〜60秒待機後にリトライ |
| **504 Gateway Timeout** | 銘柄数/期間を縮小して再試行 |
| **500 Internal Server Error** | 数分後にリトライ、改善しない場合はお問い合わせください |

---

## 補足情報

### 現在の技術スタック

| 項目 | 技術 |
|---|---|
| バックエンド | FastAPI + SQLAlchemy 2.0 (Async) |
| データベース | PostgreSQL (Supabase) |
| キャッシュ | Redis（オプション）+ インメモリ |
| データソース | Yahoo Finance (yfinance) |
| ホスティング | Render |

### 今後の改善予定

- より大きなバッチサイズへの対応検討
- CDN/エッジキャッシュの導入検討
- データベースリードレプリカの追加検討

---

ご不明な点がございましたら、お気軽にお問い合わせください。
安定したデータ取得のため、上記推奨設定でのご利用をお願いいたします。

---

## 補足: 現在のインフラ構成（2024年12月 アップグレード完了）

### ✅ アップグレード完了: Pro Plan + Small Compute

**Supabase Pro Plan + Small Compute（$30/月）** へのアップグレードが完了しました。

### 現在のスペック

| 項目 | スペック |
|------|----------|
| **プラン** | Pro Plan + Small Compute |
| **月額** | $30（$25 + $5） |
| **メモリ** | **2 GB** |
| **CPU** | 2-core ARM（共有） |
| **ディスク容量** | **50 GB** |
| **ディスクスループット** | **174 Mbps** |
| **ディスク IOPS** | **1,000 IOPS** |
| **直接接続数** | **90** |
| **Pooler接続数** | **400** |
| **自動バックアップ** | 毎日（7日間保持） |
| **ログ保持期間** | 7日間 |
| **サポート** | メールサポート |

### Free Plan からの改善効果

| 項目 | Free Plan (Nano) | **現在 (Small)** | 改善率 |
|------|------------------|------------------|--------|
| **メモリ** | 0.5 GB | **2 GB** | **4倍** |
| **ディスク** | 500 MB | **50 GB** | **100倍** |
| **IOPS** | 250 | **1,000** | **4倍** |
| **スループット** | 43 Mbps | **174 Mbps** | **4倍** |
| **Pooler接続** | 200 | **400** | **2倍** |
| **プロジェクト停止** | 1週間で自動停止 | **停止なし** | ✅ |
| **バックアップ** | なし | **毎日** | ✅ |

### 期待される改善効果

| 問題 | 改善見込み |
|------|-----------|
| **タイムアウト** | メモリ4倍・IOPS4倍で **大幅減少** |
| **Internal Server Error** | リソース安定化で **大幅減少** |
| **Cold Start** | プロジェクト停止なしで **完全解消** |
| **同時リクエスト処理** | Pooler接続2倍で **2〜3倍の処理能力** |
| **大量データ取得** | ディスクI/O向上で **安定動作** |

### 推奨されるリクエスト設定（更新）

Small Compute へのアップグレードにより、以下の設定が推奨されます：

| 項目 | 旧推奨値 | **新推奨値** |
|------|----------|-------------|
| **1リクエストあたりの銘柄数** | 5〜10銘柄 | **最大10銘柄**（余裕あり） |
| **並列リクエスト数** | 2〜4並列 | **4〜8並列** |
| **リクエスト間隔** | 1秒以上 | **0.5秒以上** |
| **期間指定** | 1年以内 | **2〜3年でも安定** |

---

ご不明な点がございましたら、お気軽にお問い合わせください。

---

## 追加質問への回答（2025年12月3日）

インフラ増強後の追加ご質問について、現在のコードベースを確認した上で回答いたします。

### 1. DB取得（キャッシュヒット）時の銘柄数制限の緩和について

#### 現状の実装

現在、`API_MAX_SYMBOLS = 10` の制限は **全リクエストに一律適用** されています。

```python
# app/api/v1/prices.py
if len(uniq) > settings.API_MAX_SYMBOLS:
    raise HTTPException(status_code=422, detail="too many symbols requested")
```

#### 回答

**ご指摘の通り、DBからの読み出しのみであれば制限緩和は技術的に可能です。**

現在の実装では `auto_fetch` パラメータが既に存在しており、これを活用できます：

```
GET /v1/prices?symbols=...&from=...&to=...&auto_fetch=false
```

`auto_fetch=false` の場合、外部API（Yahoo Finance）へのアクセスは行われず、**DBに存在するデータのみ返却** されます。

**対応案（検討中）：**

| 案 | 内容 | 実装難易度 |
|----|------|-----------|
| **案A** | `auto_fetch=false` 時のみ `API_MAX_SYMBOLS` を 50〜100 に緩和 | 低 |
| **案B** | 新パラメータ `local_only=true` を追加し、制限を別設定 | 中 |
| **案C** | 別エンドポイント `/v1/prices/bulk` を新設 | 中〜高 |

**推奨: 案A** - 既存の `auto_fetch=false` を活用し、制限を緩和する方向で検討いたします。

---

### 2. レート制限とキューイングの適用範囲

#### 現状の実装

レート制限（2リクエスト/秒）は **Yahoo Finance API への外部アクセス時のみ** 適用されています。

```python
# app/services/coverage_service.py
_fetch_semaphore = anyio.Semaphore(settings.YF_REQ_CONCURRENCY)

async def fetch_prices_df(symbol: str, start: date, end: date):
    async with _fetch_semaphore:  # ← 外部API呼び出し時のみ制限
        return await run_in_threadpool(fetch_prices, ...)
```

#### 回答

**DBからの読み出しのみのリクエストには、レート制限は適用されません。**

| リクエスト種別 | レート制限 | 理由 |
|---------------|-----------|------|
| **DB読み出しのみ** | **なし** | 外部APIを叩かないため |
| **外部API呼び出しあり** | 2リクエスト/秒 | Yahoo Finance のレート制限対策 |

したがって、`auto_fetch=false` でリクエストする場合、並列リクエスト数に関して **サーバー側の制限はありません**（Pooler 接続数 400 の範囲内）。

---

### 3. Fetch Job API のデータ受渡フロー

#### 現状の実装

**パターンB** が正解です。

```python
# app/api/v1/fetch.py
@router.get("/fetch/{job_id}", response_model=FetchJobResponse)
async def get_fetch_job_status(job_id: str, ...):
    # ジョブのステータス・進捗のみを返却
    # 株価データ自体は含まれない
```

#### フローの詳細

```
1. POST /v1/fetch → ジョブ作成（バックグラウンドでDB取り込み開始）
2. GET /v1/fetch/{job_id} → 進捗確認（status: pending → processing → completed）
3. GET /v1/prices?symbols=... → ジョブ完了後、DBからデータ取得
```

#### ご懸念への回答

**ジョブ完了後の `GET /v1/prices` については、上記1の回答と組み合わせることで効率化可能です：**

```
# ジョブ完了後（データはDB内に存在）
GET /v1/prices?symbols=AAPL,MSFT,...(50銘柄)&from=2020-01-01&to=2024-12-31&auto_fetch=false
```

- ジョブでDBへの取り込みが完了済み → 外部APIアクセス不要
- `auto_fetch=false` により純粋なDB読み出し
- **制限緩和（50〜100銘柄）が実装されれば、1リクエストで一括取得可能**

---

### 4. 要望: バルクRead用エンドポイントまたはオプション

#### 対応方針（検討中）

ご要望を踏まえ、以下の対応を検討しております：

| 優先度 | 対応内容 | 詳細 |
|--------|----------|------|
| **高** | `auto_fetch=false` 時の銘柄数制限緩和 | `API_MAX_SYMBOLS_LOCAL = 100` を新設 |
| **中** | レスポンスサイズ制限の緩和 | `API_MAX_ROWS` を 50,000 → 200,000 に |
| **低** | 専用バルクエンドポイント | `/v1/prices/bulk` の新設 |

#### 暫定的な推奨フロー

現時点での効率的なETL処理フローは以下となります：

```python
# ETLクライアント側の実装例

import asyncio
import httpx

async def bulk_fetch_prices(symbols: list, date_from: str, date_to: str):
    """50銘柄を5並列 × 10銘柄で取得"""
    
    async with httpx.AsyncClient(timeout=60) as client:
        tasks = []
        
        # 10銘柄ずつ分割
        for i in range(0, len(symbols), 10):
            chunk = symbols[i:i+10]
            task = client.get(
                "https://api.example.com/v1/prices",
                params={
                    "symbols": ",".join(chunk),
                    "from": date_from,
                    "to": date_to,
                    "auto_fetch": "false"  # DB読み出しのみ
                }
            )
            tasks.append(task)
        
        # 5並列で実行（DB読み出しのみなのでレート制限なし）
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 結果をマージ
        all_prices = []
        for result in results:
            if isinstance(result, httpx.Response) and result.status_code == 200:
                all_prices.extend(result.json())
        
        return all_prices

# 使用例
prices = await bulk_fetch_prices(
    symbols=["AAPL", "MSFT", ...],  # 50銘柄
    date_from="2020-01-01",
    date_to="2024-12-31"
)
```

---

### まとめ

| ご質問 | 回答 |
|--------|------|
| **DB取得時の銘柄数制限緩和** | `auto_fetch=false` 時の緩和を検討中（50〜100銘柄） |
| **レート制限の適用範囲** | DB読み出しのみの場合は **適用されません** |
| **Fetch Job API のフロー** | パターンB（DBへの取り込みのみ、データは別途取得） |
| **バルクReadエンドポイント** | `auto_fetch=false` + 制限緩和で対応予定 |

**現時点の推奨:**
1. 事前に `POST /v1/fetch` でデータをDBに取り込み
2. ジョブ完了後、`GET /v1/prices?auto_fetch=false` で取得（10銘柄 × 5並列）
3. 制限緩和の実装後は、50〜100銘柄を1リクエストで取得可能に

ご要望の機能追加について、優先度を上げて対応を検討いたします。
進捗がありましたら改めてご連絡いたします。
