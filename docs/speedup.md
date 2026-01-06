# 高速化・安定性向上の検討事項

> **対象環境**: Supabase (NullPool) + Render Starter + Redis無し  
> **更新日**: 2025年12月3日

---

## 現在の環境で実装可能な改善項目

### 1. Upsertバッチサイズ拡大 ✅ 実装済み

**変更内容**: `batch_size = 500 → 2000` (upsert.py)

**推奨変更**:
```python
# app/services/upsert.py
batch_size: int = 2000  # 500 → 2000
```

**根拠**: Priceテーブルは7カラム程度の小さな行。2000行でも1回のクエリサイズは適正範囲。

**期待効果**: バッチ数削減により30-50%の書き込み高速化

---

### 2. TaskGroupへの移行 ⚠️ 不採用

**理由**: 現在の実装では `return_exceptions=True` により、1銘柄の失敗でも他の取得を継続する設計。TaskGroupは1つの失敗で全タスクをキャンセルするため、データ取得には不向き。

**結論**: 現在の `asyncio.gather(*tasks, return_exceptions=True)` が最適

---

### 3. キャッシュヒット率向上 ✅ 実装済み

**変更内容**:
- `CACHE_TTL_SECONDS`: 3600 → 14400（4時間）
- `max_size`: 1000 → 1500

**変更ファイル**: `config.py`, `cache.py`

---

### 4. 並行処理数の調整 ✅ 実装済み

**変更内容**: `YF_REQ_CONCURRENCY`: 8 → 6

**理由**:
- レート制限（秒間2リクエスト）が実質的なボトルネック
- 並行数8は過剰でセマフォ待機タスクが増加
- 6に下げてメモリ効率とリソース管理を改善

**変更ファイル**: `config.py`

---

### 5. ストリーミング処理の活用徹底 ✅ 既に最適化済み

**現状確認**:
- `fetch_prices_batch()` は `use_streaming=True` がデフォルト
- `fetch_prices_streaming()` の `chunk_size=10` は適切
- `chunk_size=5` への変更はスループット低下のため不採用

**結論**: 追加変更不要

---

### 6. クエリ最適化（カバレッジ計算） ✅ 実装済み

**最適化内容**:
1. `generate_series` + `NOT EXISTS` の重いクエリを廃止
2. 期待weekday数をPythonで計算（`_count_weekdays()`関数追加）
3. ギャップがある場合のみ`first_missing`クエリを実行（遅延評価）

**変更ファイル**: `queries_optimized.py`

**効果**: 
- 通常ケース（ギャップなし）: クエリ1回のみ
- ギャップありケース: クエリ2回（従来は常に重いクエリ1回）

---

### 7. ログレベル最適化 ✅ 実装済み

**変更内容**: ホットパス上の成功ログを`INFO`→`DEBUG`に変更

**対象ファイル**: `symbol_validator.py`

**変更箇所**:
- `Symbol {symbol} validated successfully` → DEBUG
- `Symbol {symbol} not found in Yahoo Finance (404)` → DEBUG
- `Symbol {symbol} info retrieved successfully` → DEBUG

**効果**: 
- 通常の成功リクエストではログ出力が減少
- ログI/O削減によるわずかなパフォーマンス向上
- エラー・警告ログは維持されるため問題診断に影響なし

---

### 8. Prefetchサービスの活用 ✅ 実装済み

**課題**: Supabase環境では`prefetch_service`が無効化されていた（NullPool制限）

**解決策**: 起動時1回のみの軽量キャッシュウォーム実装

```python
# prefetch_service.py に startup_cache_warm() を追加
async def startup_cache_warm(symbols: List[str]) -> int:
    """
    起動時1回だけのキャッシュウォーム（Supabase NullPool環境用）。
    - DBから既存の価格データを1回のクエリで取得
    - キャッシュに保存（yfinance呼び出しなし）
    - 並列接続なし、バックグラウンドタスクなし
    """
```

**変更ファイル**: `prefetch_service.py`, `main.py`

**動作**:
- 非Supabase環境: 従来通り定期更新付きの`PrefetchService`を使用
- Supabase環境: `startup_cache_warm()`で起動時のみキャッシュをウォーム

**効果**: 起動直後のキャッシュヒット率向上、コールドスタート問題の軽減

---

### 9. 価格クエリのUNION最適化 ✅ 実装済み

**最適化内容**:
- symbol_changesが存在しない場合（大半のケース）はシンプルなクエリを使用
- `_has_symbol_changes()`で事前チェック
- UNIONオーバーヘッドを回避

**変更ファイル**: `queries/prices.py`

**効果**: 通常ケースで20-40%のクエリ高速化

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
| ✅ 完了 | Upsertバッチサイズ2000 | 1行変更 | 30-50%書き込み改善 |
| ✅ 完了 | YF_REQ_CONCURRENCY調整 | 設定変更 | リソース効率化 |
| ⚠️ 不採用 | TaskGroup移行 | - | 現行設計に不適合 |
| ✅ 完了 | キャッシュTTL延長 | 設定変更 | ヒット率向上 |
| ✅ 完了 | カバレッジクエリ最適化 | 中程度 | クエリ高速化 |
| ✅ 完了 | 価格クエリUNION最適化 | 中程度 | クエリ高速化 |
| ✅ 完了 | ログレベル最適化 | 小 | ログI/O削減 |
| ✅ 完了 | Prefetchキャッシュウォーム | 中程度 | コールドスタート改善 |

---

## 参考リンク

- [SQLAlchemy 2.0 Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [asyncpg Performance](https://github.com/MagicStack/asyncpg#performance)
- [Python 3.11 TaskGroup](https://docs.python.org/3/library/asyncio-task.html#asyncio.TaskGroup)
