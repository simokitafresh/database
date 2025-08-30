# app/db クリティカルエラー調査メモ

## 目的
- `app/db` 層（エンジン/ORM/ユーティリティ/クエリ）の致命的エラーの芽と運用上の落とし穴を洗い出し、改善提案をまとめる。

## 対象
- 参照ファイル:
  - `app/db/base.py`（Declarative Base）
  - `app/db/engine.py`（非同期エンジン/セッションファクトリ）
  - `app/db/models.py`（ORM モデル: `symbols`, `symbol_changes`, `prices`）
  - `app/db/utils.py`（`advisory_lock`）
  - `app/db/queries.py`（カバレッジ検査/取得・解決セレクト・シンボル列挙）
- 関連テスト:
  - `tests/unit/test_engine.py`, `tests/unit/test_models.py`,
    `tests/unit/test_db_utils.py`, `tests/unit/test_db_coverage.py`,
    `tests/unit/test_db_queries_signatures.py`, ほかマイグレーション検証

## 概要結論
- 仕様・テストの観点では、重大なクラッシュ要因は直ちには見当たらない。
- ただし運用/方言依存やバージョン差で“致命化”しうるポイントが複数あるため、予防的なガイドと最小差分の改善案を提示する。

## 詳細調査（要点）

### 1) エンジン/セッション: `app/db/engine.py`
- `create_engine_and_sessionmaker()` は `create_async_engine(database_url)` でエンジンを生成し、`async_sessionmaker` を返却。`future=True` 等の明示設定はなし。
- テストではドライバ名が `postgresql+asyncpg` であることを確認。
- 潜在的リスク:
  - `DATABASE_URL` が非 async（例: `postgresql://`）の場合、起動時にドライバ不整合で失敗。→ 設定バリデーションを `Settings` 側で行うと安全。
  - `pool_pre_ping=True` を付与しないと、接続アイドル切断時に初回失敗が起こりうる（運用時）。

推奨（任意・最小差分）:
- `create_async_engine(database_url, pool_pre_ping=True)` を使用。

### 2) ORM モデル: `app/db/models.py`
- `prices` テーブルに複合 PK と各種 CHECK を定義。`volume` は `BigInteger`、`last_updated` は `timezone=True` で `server_default=now()`。
- `symbol_changes` は `(old_symbol, change_date)` を PK、`new_symbol` に `UNIQUE` を付与（1ホップ保証）。
- 潜在的リスク:
  - `last_updated` のサーバデフォルトは DB 側のタイムゾーンに依存。UTC 前提の仕様であれば DB 側の `timezone` 設定を合わせる（運用事項）。
  - `prices` の FK は `ondelete=RESTRICT`。シンボル削除時に価格行が残るため、メンテフローが必要（仕様どおり）。

### 3) ユーティリティ: `app/db/utils.py`（アドバイザリロック）
- `pg_advisory_xact_lock(hashtext(:symbol))` を使用。トランザクション境界内でのロックが前提。
- 潜在的リスク:
  - SQLite や非 PostgreSQL 方言では実行不能。テストでは `AsyncMock` で抽象化されているが、統合環境は PostgreSQL 前提で運用する。
  - トランザクション外で呼び出すと文脈に依存。`ensure_coverage()` では `session.begin()` の外で呼び出さないように注意（現状は `session.begin()` → `advisory_lock()` の順で OK）。

### 4) クエリ: `app/db/queries.py`
- `_get_coverage()` は `generate_series` とウィークデイ検出を用いたギャップ検出 SQL。PostgreSQL 前提。
- `ensure_coverage()` は 3 条件（`last_date-refetch_days`, `first_missing_weekday`, `first_date>from`）の最小開始日で取得範囲を決定し、`upsert_prices_sql()` で UPSERT。
- `get_prices_resolved()` は `get_prices_resolved(:symbol, :date_from, :date_to)` をシンボルごとに呼び出し、マッピングを辞書化して結合後、`(date, symbol)` キーでソート返却。
- `list_symbols()` は生 SQL で `active` をバインドして返却。
- 潜在的リスク/ハマり所:
  - `_get_coverage()` の SQL は休日テーブルを考慮しておらず「土日以外の休場日」はギャップ扱いになる可能性（仕様上は許容）。必要なら将来の拡張点。
  - `ensure_coverage()` の最小開始日の決定ロジックで `first_missing_weekday` が無い場合の `has_gaps=True` 分岐をガード済みだが、DB 方言差/集計結果の `None` 取り扱いに注意（現状は `Optional[date]` として取り扱い OK）。
  - `get_prices_resolved()` は複数シンボルをループで呼ぶ設計。SQL 側で multi-symbol 対応のラッパーがあると往復が減るが、現状でも AC は満たす。

## 推奨変更（任意・最小差分）
1) エンジンのプレピン有効化
```python
# app/db/engine.py（参考パッチ案）
engine = create_async_engine(database_url, pool_pre_ping=True)
```
効果: アイドル切断に強くなり、運用時の接続エラーが緩和。

2) 設定バリデーション（Settings 側）
- `DATABASE_URL` が `postgresql+asyncpg://` で始まることを軽く検証（運用安全策）。

3) 休日テーブル拡張の余地をコメント化
- `_get_coverage()` に将来の JOIN 余地をコメントで明示（実装は現状維持）。

## スモークと検証（参考）
- 署名/SQL 形状: `tests/unit/test_db_queries_signatures.py` を参照。
- カバレッジ判定: `tests/unit/test_db_coverage.py` は `fetch_prices_df` 周りをモックし、期待開始日を検証。
- アドバイザリロック: `tests/unit/test_db_utils.py` で SQL 文面とパラメータを検証。
- DDL 整合: `tests/unit/test_models.py` で CHECK/PK/FK/UNIQUE を検証。

## まとめ
- 現状、DB 層は仕様・テスト整合の範囲で致命的エラーは検出されず、PostgreSQL 前提で妥当。
- 運用時の安定性向上として、`pool_pre_ping=True` の付与と URL の軽い検証を推奨。休日考慮は将来の拡張点として整理済み。

