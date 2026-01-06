# 002: 追加パフォーマンス改善提案

**調査日**: 2026-01-06  
**最終更新**: 2026-01-07  
**ステータス**: 一部実装済み

---

## ステータスサマリー

| # | 項目 | 優先度 | ステータス |
|---|------|--------|----------|
| 1 | N+1クエリ問題 | 🔴 高 | ✅ 実装済み |
| 2 | DB_POOL_SIZE拡大 | 🟡 中 | 未実装 |
| 3 | PREFETCH_SYMBOLS拡充 | 🟡 中 | ✅ 実装済み (13銘柄) |
| 4 | 不要import削除 | 🟢 低 | 未実装 |

---

## 1. ✅ N+1クエリ問題（実装済み）

**ファイル**: `app/services/price_service.py` L122-132

```python
# 現在のコード（バッチクエリ - N+1解消済み）
all_rows = await queries.get_prices_resolved(
    session=self.session,
    symbols=uncached_symbols,  # ← 全シンボル一括
    date_from=date_from,
    date_to=effective_to,
)
```

---

## 2. 🟡 DB_POOL_SIZE拡大（未実装）

**現在**: `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5`

**Direct接続**では制限緩和可能。

**提案**: `DB_POOL_SIZE=10`, `DB_MAX_OVERFLOW=10`

---

## 3. ✅ PREFETCH_SYMBOLS拡充（実装済み）

**更新日**: 2026-01-07

```python
PREFETCH_SYMBOLS = "TQQQ,TECL,GLD,XLU,^VIX,QQQ,SPY,TMV,TMF,LQD,GDX,QLD,SPXL"
```

アクティブ銘柄13件全てをプリフェッチ対象に設定。

---

## 4. 🟢 不要import削除（未実装）

`_symbol_has_any_prices`内の`import inspect`は関数外に移動可能。

---

## 今後の検討事項

- 経済指標（DTB3）のプリフェッチ対応
- market_hours連携によるキャッシュ延長

