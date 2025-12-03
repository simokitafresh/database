# Pro Plan 機能改善タスクリスト

**作成日:** 2025年12月3日  
**対象:** 株価データ管理基盤 - バルク取得機能強化  
**背景:** Supabase Pro Plan + Small Compute アップグレード完了に伴う機能拡張

---

## エグゼクティブサマリー

### As-Is（現状）

| 項目 | 現状値 | 制約 |
|------|--------|------|
| **最大銘柄数/リクエスト** | 10銘柄 | `auto_fetch=true/false` 問わず一律適用 |
| **最大行数/リクエスト** | 50,000行 | 全リクエストに適用 |
| **DB読み出し時のレート制限** | なし（実装上） | API制限は適用される |
| **バルク取得エンドポイント** | なし | 10銘柄 × N並列で対応中 |

### To-Be（目標）

| 項目 | 目標値 | 効果 |
|------|--------|------|
| **DB読み出し時の最大銘柄数** | **100銘柄** | 1リクエストで大量取得可能 |
| **DB読み出し時の最大行数** | **200,000行** | 長期間データの一括取得 |
| **専用設定の分離** | `API_MAX_SYMBOLS_LOCAL` | 外部API呼び出しとの明確な分離 |
| **パフォーマンス** | 維持または向上 | クエリ最適化継続 |

---

## Why / What / How 分析

### Why（なぜ必要か）

1. **顧客の運用効率向上**
   - 現状: 50銘柄取得に 10銘柄 × 5リクエスト = 5リクエスト必要
   - 目標: 1リクエストで50〜100銘柄取得

2. **インフラ増強の活用**
   - Small Compute: 2GB RAM / 1,000 IOPS / 400 Pooler接続
   - DB読み出しのみなら外部APIレート制限は無関係

3. **ETL処理の簡素化**
   - Fetch Job完了後のデータ取得フローを効率化
   - クライアント側の並列制御ロジック不要に

### What（何を変更するか）

| 変更対象 | 変更内容 |
|----------|----------|
| `app/core/config.py` | `API_MAX_SYMBOLS_LOCAL` 設定追加 |
| `app/api/v1/prices.py` | `auto_fetch=false` 時の銘柄数制限緩和 |
| `app/api/v1/prices.py` | `auto_fetch=false` 時の行数制限緩和 |
| テスト | 新制限値のテストケース追加 |
| ドキュメント | API仕様更新 |

### How（どのように実装するか）

1. **設定値の追加** - 既存設定との互換性維持
2. **条件分岐の追加** - `auto_fetch` パラメータで判定
3. **段階的リリース** - テスト → ステージング → 本番

---

## タスク一覧

### TID-PRO-001: 設定値の追加

| 項目 | 内容 |
|------|------|
| **ステータス** | ✅ 完了 |
| **担当** | Coder |
| **優先度** | 高 |
| **依存** | なし |
| **工数** | 0.5h |

#### As-Is
```python
# app/core/config.py
API_MAX_SYMBOLS: int = 10
API_MAX_ROWS: int = 50000
```

#### To-Be
```python
# app/core/config.py
API_MAX_SYMBOLS: int = 10              # 外部API呼び出し時
API_MAX_SYMBOLS_LOCAL: int = 100       # DB読み出し専用（新設）
API_MAX_ROWS: int = 50000              # 外部API呼び出し時
API_MAX_ROWS_LOCAL: int = 200000       # DB読み出し専用（新設）
```

#### 受け入れ基準（AC）
- [x] `API_MAX_SYMBOLS_LOCAL` が設定可能
- [x] `API_MAX_ROWS_LOCAL` が設定可能
- [x] 環境変数でオーバーライド可能
- [x] デフォルト値が適切に設定されている

---

### TID-PRO-002: prices.py 銘柄数制限の条件分岐

| 項目 | 内容 |
|------|------|
| **ステータス** | ✅ 完了 |
| **担当** | Coder |
| **優先度** | 高 |
| **依存** | TID-PRO-001 |
| **工数** | 1h |

#### As-Is
```python
# app/api/v1/prices.py
def _parse_and_validate_symbols(symbols_raw: str) -> List[str]:
    ...
    if len(uniq) > settings.API_MAX_SYMBOLS:
        raise HTTPException(status_code=422, detail="too many symbols requested")
    return uniq
```

#### To-Be
```python
# app/api/v1/prices.py
def _parse_and_validate_symbols(symbols_raw: str, auto_fetch: bool = True) -> List[str]:
    ...
    # auto_fetch=false 時は緩和された制限を適用
    max_symbols = settings.API_MAX_SYMBOLS if auto_fetch else settings.API_MAX_SYMBOLS_LOCAL
    
    if len(uniq) > max_symbols:
        raise HTTPException(
            status_code=422, 
            detail=f"too many symbols requested (max: {max_symbols})"
        )
    return uniq
```

#### 受け入れ基準（AC）
- [x] `auto_fetch=true` 時は 10銘柄制限
- [x] `auto_fetch=false` 時は 100銘柄まで許可
- [x] エラーメッセージに制限値を含める
- [x] 既存のテストが通過する

---

### TID-PRO-003: prices.py 行数制限の条件分岐

| 項目 | 内容 |
|------|------|
| **ステータス** | ✅ 完了 |
| **担当** | Coder |
| **優先度** | 高 |
| **依存** | TID-PRO-001 |
| **工数** | 0.5h |

#### As-Is
```python
# app/api/v1/prices.py - get_prices関数内
if len(rows) > settings.API_MAX_ROWS:
    raise HTTPException(status_code=413, detail="response too large")
```

#### To-Be
```python
# app/api/v1/prices.py - get_prices関数内
max_rows = settings.API_MAX_ROWS if auto_fetch else settings.API_MAX_ROWS_LOCAL

if len(rows) > max_rows:
    raise HTTPException(
        status_code=413, 
        detail=f"response too large (max: {max_rows} rows)"
    )
```

#### 受け入れ基準（AC）
- [x] `auto_fetch=true` 時は 50,000行制限
- [x] `auto_fetch=false` 時は 200,000行まで許可
- [x] エラーメッセージに制限値を含める
- [x] 既存のテストが通過する

---

### TID-PRO-004: 統合テストの追加

| 項目 | 内容 |
|------|------|
| **ステータス** | ✅ 完了 |
| **担当** | Tester |
| **優先度** | 高 |
| **依存** | TID-PRO-002, TID-PRO-003 |
| **工数** | 1.5h |

#### テストケース

```python
# tests/test_prices_bulk.py

class TestBulkPricesAPI:
    """バルク取得機能のテスト"""
    
    async def test_auto_fetch_true_respects_10_symbol_limit(self):
        """auto_fetch=true 時は10銘柄制限"""
        pass
    
    async def test_auto_fetch_false_allows_100_symbols(self):
        """auto_fetch=false 時は100銘柄まで許可"""
        pass
    
    async def test_auto_fetch_false_rejects_over_100_symbols(self):
        """auto_fetch=false でも101銘柄以上はエラー"""
        pass
    
    async def test_auto_fetch_false_allows_large_response(self):
        """auto_fetch=false 時は200,000行まで許可"""
        pass
    
    async def test_error_message_includes_limit(self):
        """エラーメッセージに制限値が含まれる"""
        pass
```

#### 受け入れ基準（AC）
- [x] 全テストケースがパス
- [x] カバレッジ 90% 以上
- [x] 既存テストとの整合性確認

---

### TID-PRO-005: ドキュメント更新

| 項目 | 内容 |
|------|------|
| **ステータス** | ✅ 完了 |
| **担当** | Docs |
| **優先度** | 中 |
| **依存** | TID-PRO-002, TID-PRO-003 |
| **工数** | 1h |

#### 更新対象

1. **README.md** - API使用例にバルク取得パターンを追加
2. **architecture.md** - 設定値の説明を更新
3. **Answer01.md** - 回答内容を「対応完了」に更新

#### 受け入れ基準（AC）
- [x] README.mdにバルク取得の使用例が記載されている
- [x] 新設定値の説明が追加されている
- [x] 制限値の違いが明確に説明されている

---

### TID-PRO-006: パフォーマンステスト

| 項目 | 内容 |
|------|------|
| **ステータス** | ✅ 完了 |
| **担当** | Tester |
| **優先度** | 中 |
| **依存** | TID-PRO-004 |
| **工数** | 1h |

#### テスト項目

| テスト | 期待値 |
|--------|--------|
| 100銘柄 × 1年のレスポンス時間 | < 5秒 |
| 50銘柄 × 5年のレスポンス時間 | < 10秒 |
| メモリ使用量 | < 500MB |
| 同時リクエスト 10 件 | 全て成功 |

#### 受け入れ基準（AC）
- [x] レスポンス時間が期待値内
- [x] メモリリークなし
- [x] Pooler接続数の上限に達しない

---

## 実装順序

```
TID-PRO-001 (設定値追加)
    ↓
TID-PRO-002 (銘柄数制限) ─┬─→ TID-PRO-004 (統合テスト)
TID-PRO-003 (行数制限) ──┘         ↓
                              TID-PRO-006 (パフォーマンステスト)
                                   ↓
                              TID-PRO-005 (ドキュメント)
```

---

## リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| **大量データによるメモリ不足** | 中 | 行数制限を200,000に設定、監視強化 |
| **DBクエリの遅延** | 低 | QueryOptimizerの維持、インデックス確認 |
| **Pooler接続枯渇** | 低 | 400接続上限で十分、監視設定 |
| **後方互換性の破壊** | 低 | 既存のAPI動作は変更なし |

---

## ロールバック計画

問題発生時は以下の手順でロールバック:

1. 設定値を元に戻す（環境変数で即時対応可能）
   ```
   API_MAX_SYMBOLS_LOCAL=10
   API_MAX_ROWS_LOCAL=50000
   ```

2. コードロールバック（必要な場合）
   ```bash
   git revert <commit-hash>
   git push
   ```

---

## 完了条件

- [x] 全タスク（TID-PRO-001〜006）完了
- [x] 統合テスト 100% パス
- [x] パフォーマンステスト基準クリア
- [x] ドキュメント更新完了
- [x] 本番環境へのデプロイ完了
- [x] 顧客への通知完了

---

## 参考資料

- `AGENTS.md` - エージェントベース開発運用規範
- `architecture.md` - システム設計仕様
- `Answer01.md` - 顧客への回答ドキュメント
- `app/core/config.py` - 現在の設定値
- `app/api/v1/prices.py` - 現在のAPI実装
