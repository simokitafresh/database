# 001: Supabase Direct接続最適化

**調査日**: 2026-01-06  
**ステータス**: ✅ 完了・本番適用済み

---

## 概要

Supabase Transaction Pooler前提の過剰な制約を発見し、Direct接続（IPv4 Add-on）への移行を実施。パフォーマンスと機能が大幅に改善された。

---

## 実施した変更

### 1. Pooler判定ロジック修正

**ファイル**: `app/db/engine.py`

```diff
- if "supabase.com" in database_url:
-     poolclass = NullPool
+ is_transaction_pooler = "pooler.supabase.com" in database_url and ":6543" in database_url
+ if is_transaction_pooler or is_pgbouncer:
+     poolclass = NullPool
+ elif "supabase.com" in database_url:
+     logger.info("Using connection pool for Supabase (Session/Direct mode)")
```

### 2. 並行処理制限解除

**ファイル**: `app/services/fetch_worker.py`, `app/api/v1/fetch.py`

```diff
- max_concurrency=1  # Supabase NullPool制約
+ max_concurrency=4  # Direct/Session Pooler対応
```

### 3. プリフェッチ制限解除

**ファイル**: `app/main.py`

```diff
- if settings.ENABLE_CACHE and not is_supabase:  # Supabase環境では無効
+ is_transaction_pooler = "pooler.supabase.com" in url and ":6543" in url
+ if settings.ENABLE_CACHE and not is_transaction_pooler:  # Transaction Poolerのみ制限
```

### 4. リトライ設定適正化

**ファイル**: `app/api/deps.py`

```diff
- MAX_SESSION_RETRIES = 5
- RETRY_DELAY_SECONDS = 0.5
+ MAX_SESSION_RETRIES = 3
+ RETRY_DELAY_SECONDS = 0.3
```

### 5. 環境変数整理

**ファイル**: `render.yaml`

- 55個 → 必須のみ（~10個）に削減
- デフォルト値は`config.py`に委譲

---

## ベンチマーク結果（2026-01-06）

| Concurrency | RPS | Total Time | Avg Latency |
|-------------|-----|------------|-------------|
| 4 | 3.18 | 9.42s | 1212ms |
| 8 | 5.05 | 5.93s | 1432ms |
| 12 | 6.60 | 4.55s | 1617ms |
| 16 | 6.99 | 4.29s | 1671ms |
| **20** | **7.39** | **4.06s** | 1967ms |
| 24 | 6.79 | 4.42s | 2397ms |

**結論**: `concurrency=20`が最高スループットだが、レイテンシ増加傾向。安定性とサーバーリソース考慮で`concurrency=8`を採用。

---

## 改善結果

| 指標 | Before | After |
|------|--------|-------|
| 接続方式 | Session Pooler + NullPool | **Direct + ConnectionPool** |
| 並行処理 | 1 | **4** |
| プリフェッチ | 起動時1回のみ | **バックグラウンド更新** |
| 135シンボル推定時間 | ~30分 | **~8分** |
| リトライ遅延 | 最大2.5秒 | **最大0.9秒** |

---

## 本番確認ログ

```
{"level": "INFO", "message": "Prefetched 10 symbols"}  ← バックグラウンド更新動作
{"level": "INFO", "message": "prices served"}          ← API正常稼働
```

---

## 今後の注意点

- **Transaction Pooler（ポート6543）** を使用する場合のみNullPool制限が適用される
- **Direct接続** または **Session Pooler（ポート5432）** では通常のプール機能が利用可能
- IPv4 Add-onは月額料金が発生する可能性あり（Supabaseプランによる）
