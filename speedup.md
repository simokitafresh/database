# 高速化・安定性向上の検討事項

> **対象環境**: Supabase (NullPool) + Render Starter + Redis無し  
> **更新日**: 2025年12月3日

---

## 現在の環境で実装可能な改善項目

### 1. Upsertバッチサイズ拡大 🟡 未実装

**現状**: `batch_size = 500` (upsert.py)

**推奨変更**:
```python
# app/services/upsert.py
batch_size: int = 2000  # 500 → 2000
```

**根拠**: Priceテーブルは7カラム程度の小さな行。2000行でも1回のクエリサイズは適正範囲。

**期待効果**: バッチ数削減により30-50%の書き込み高速化

---

### 2. TaskGroupへの移行 🟡 未実装

**現状**: `asyncio.gather()` 使用 (fetcher.py, coverage_service.py)

**推奨変更**:
```python
# Python 3.11+ TaskGroup（エラーハンドリング改善）
async with asyncio.TaskGroup() as tg:
    tasks = [tg.create_task(fetch_symbol(s)) for s in symbols]
```

**期待効果**: 
- 1つのタスク失敗時に他タスクも即キャンセル（リソース節約）
- より明確なエラー伝播

---

### 3. キャッシュヒット率向上 🟡 調整可能

**現状**:
- `CACHE_TTL_SECONDS = 3600`（1時間）
- `max_size = 1000`（インメモリキャッシュ上限）

**検討項目**:
| 設定 | 現在値 | 検討値 | 効果 |
|-----|-------|-------|-----|
| CACHE_TTL_SECONDS | 3600 | 7200〜14400 | ヒット率向上（日次データ向け） |
| max_size | 1000 | 2000 | より多くの銘柄をメモリ保持 |

**トレードオフ**: メモリ使用量増加（Render Starter 512MBに注意）

---

### 4. 並行処理数の調整 🟢 設定変更のみ

**現状**:
- `YF_REQ_CONCURRENCY = 8`
- `FETCH_WORKER_CONCURRENCY = 2`

**検討項目**:
```
YF_REQ_CONCURRENCY: 8 → 5〜6に下げて429エラー削減を検討
※ yfinance非公式APIのため、高すぎるとIPブロックリスク
```

---

### 5. ストリーミング処理の活用徹底 🟢 既存機能の活用

**現状**: `fetch_prices_streaming()` は実装済みだが一部で未使用

**推奨**: 大量データ処理時はストリーミングを強制
```python
# chunk_size調整（現在: 10）
chunk_size: int = 5  # メモリ制約環境では小さめに
```

---

### 6. クエリ最適化（カバレッジ計算） 🟡 改善余地あり

**現状**: `get_coverage_optimized()` で `generate_series` 使用

**検討項目**:
- Supabaseでも `generate_series` は問題なく動作
- ただし `NOT EXISTS` サブクエリが重い可能性

**代替案**: 日付カウント比較のみで簡易判定
```sql
-- 現在の複雑なギャップ検出
WITH date_range AS (SELECT generate_series(...))
-- ↓ 簡易版
SELECT COUNT(*) AS actual_count,
       (date_to - date_from) * 5 / 7 AS expected_estimate
FROM prices WHERE ...
```

---

## 環境アップグレード時に実装可能な項目

| 施策 | 必要な環境 | 効果 |
|-----|----------|------|
| Redis分散レート制限 | Redis Cloud or Render Standard | ワーカー間で状態共有 |
| Redis L2キャッシュ | 同上 | キャッシュ永続化 |
| コネクションプール | Supabase Session Mode or 専用PostgreSQL | pool_size有効化 |
| PostgreSQL設定変更 | 専用PostgreSQL | shared_buffers等の調整 |

---

## 優先度まとめ

| 優先度 | 項目 | 工数 | 効果 |
|-------|-----|-----|------|
| 🔴 高 | Upsertバッチサイズ2000 | 1行変更 | 30-50%書き込み改善 |
| 🔴 高 | YF_REQ_CONCURRENCY調整 | 設定変更 | 429エラー削減 |
| 🟡 中 | TaskGroup移行 | 中程度 | エラー処理改善 |
| 🟡 中 | キャッシュTTL延長 | 設定変更 | ヒット率向上 |
| 🟢 低 | カバレッジクエリ簡易化 | 中程度 | 軽微な高速化 |

---

## 参考リンク

- [SQLAlchemy 2.0 Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [asyncpg Performance](https://github.com/MagicStack/asyncpg#performance)
- [Python 3.11 TaskGroup](https://docs.python.org/3/library/asyncio-task.html#asyncio.TaskGroup)
