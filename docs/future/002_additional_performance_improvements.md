# 002: 追加パフォーマンス改善提案

**調査日**: 2026-01-06  
**ステータス**: 提案段階

---

## 発見した改善点

### 1. 🔴 N+1クエリ問題（高優先度）

**ファイル**: `app/services/price_service.py` L133-140

```python
# 現在のコード（N+1問題）
for symbol in uncached_symbols:
    symbol_rows = await queries.get_prices_resolved(
        session=self.session,
        symbols=[symbol],  # ← 毎回1シンボルずつ
        ...
    )
```

**問題**: シンボルごとに個別DBクエリ発行。20シンボル → 20クエリ

**改善案**: 
```python
# 1回のバッチクエリに変更
all_rows = await queries.get_prices_resolved(
    session=self.session,
    symbols=uncached_symbols,  # ← 全シンボル一括
    date_from=date_from,
    date_to=effective_to,
)
```

**期待効果**: クエリ数 N → 1（90%削減）

---

### 2. 🟡 DB_POOL_SIZE拡大（中優先度）

**現在**: `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5`

**Direct接続**では制限緩和可能。

**提案**: `DB_POOL_SIZE=10`, `DB_MAX_OVERFLOW=10`

**期待効果**: 高負荷時の接続待ち削減

---

### 3. 🟡 PREFETCH_SYMBOLS拡充（中優先度）

**現在**: 10シンボル固定
```
PREFETCH_SYMBOLS=TQQQ,TECL,GLD,XLU,^VIX,QQQ,SPY,TMV,TMF,LQD
```

**提案**: 最頻利用シンボルを追加（~30シンボル）

**期待効果**: キャッシュヒット率向上

---

### 4. 🟢 不要import削除（低優先度）

`_symbol_has_any_prices`内の`import inspect`は関数外に移動可能。

---

## 推奨実施順序

1. **N+1修正** - 最も効果大（即時実施推奨）
2. **DB_POOL_SIZE調整** - 並行処理改善後に効果測定
3. **PREFETCH拡充** - 運用データ分析後に決定
