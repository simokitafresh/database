# app/migrations クリティカルエラー調査メモ

## 目的
- Alembic マイグレーション（env.py・各バージョン）における致命的エラーの芽を洗い出し、改善案を整理する。

## 対象
- 参照ファイル:
  - `app/migrations/env.py`
  - `app/migrations/versions/001_init.py`
  - `app/migrations/versions/002_fn_prices_resolved.py`
  - `app/migrations/versions/003_add_price_checks.py`
- 関連テスト:
  - `tests/unit/test_migration_init.py`
  - `tests/unit/test_migration_fn_prices_resolved.py`
  - `tests/unit/test_migration_add_price_checks.py`

## 概要結論
- 現状のスクリプトは仕様とテストに整合し、直ちにクラッシュする箇所は未検出。
- ただし、実行環境のドライバ差異や関数属性、制約の冗長さなどで“致命化”し得るポイントあり。予防策を提案する。

## 詳細調査（要点）
- `env.py`
  - `DATABASE_URL`/`ALEMBIC_DATABASE_URL` を優先し、`postgresql+asyncpg://` を `postgresql+psycopg://` に置換して同期エンジンで実行。
  - `compare_type=True` 設定、メタデータは `app.db.base.Base.metadata`。
- `001_init.py`
  - テーブル作成: `symbols`, `symbol_changes(UNIQUE(new_symbol), PK(old_symbol, change_date))`, `prices(PK(symbol,date), FK symbols, volume BigInteger, last_updated timestamptz default now())`。
  - 初期 CHECK: `ck_prices_high_low_range`, `ck_prices_positive` を定義。
- `002_fn_prices_resolved.py`
  - SQL 関数 `get_prices_resolved(text,date,date)` を `CREATE OR REPLACE FUNCTION` で作成、`downgrade` で DROP。
  - 1ホップ解決: `p.date >= sc.change_date` と `p.date < sc.change_date` により区間分割、`source_symbol` を旧側に付与、`ORDER BY date`。
- `003_add_price_checks.py`
  - 追加 CHECK: `ck_prices_low_le_open_close`, `ck_prices_open_close_le_high`, `ck_prices_positive_ohlc`, `ck_prices_volume_nonneg` を作成・ダウングレードで削除。

## クリティカル化し得るポイントと対処
- ドライバ置換の前提差
  - 事象: env.py は `psycopg`（psycopg3）前提に置換。環境が `psycopg2` のみの場合に接続失敗の恐れ。
  - 対処: `postgresql+psycopg://` が使えない場合は `postgresql+psycopg2://` へのフォールバックを検討（任意の改善案）。
- 価格テーブルの CHECK 冗長化
  - 事象: 001 の `ck_prices_high_low_range`/`ck_prices_positive` と 003 の 4 つの CHECK は意味が重複し部分的に冗長。
  - 対処: 問題ではないが、将来整理するなら「003 で明示した 4 つに統一し、001 の CHECK は削除」などのマイグレーションを追加（現状維持でもテストは合格）。
- SQL 関数の属性
  - 事象: `LANGUAGE sql` で VOLATILE が暗黙。読み取りのみのため `STABLE` 指定が望ましいケースあり。
  - 対処: パフォーマンス・プラン安定性重視なら `CREATE OR REPLACE FUNCTION ... STABLE` へ更新（任意）。
- スキーマ修飾と search_path
  - 事象: 関数内のテーブル参照がスキーマ無指定（既定 `public` 前提）。環境で `search_path` が変更されていると失敗し得る。
  - 対処: 運用 DB の `search_path` を既定に保つか、関数内参照を `public.` 修飾に変更（任意）。

## 推奨（任意・最小差分案）
- env.py のドライバ置換をフォールバック対応に拡張（例）
  - 置換後に `psycopg` が未インストールなら `psycopg2` へ再置換（try/except で import 確認）。
- `get_prices_resolved` を STABLE に更新（例）
  - `CREATE OR REPLACE FUNCTION ... STABLE LANGUAGE sql AS $$ ... $$;`
- 将来的な制約整理
  - 001 の初期 CHECK を 003 の粒度に統一する追加マイグレーションを検討（互換性に配慮）。

## スモーク/検証（参考）
- 反映: `alembic upgrade head`（env 経由 URL 指定: `-x db_url=...` も可）。
- テスト参照:
  - `test_migration_init.py`: 3 テーブル作成、`UNIQUE(new_symbol)`、初期 CHECK 名の存在を検証。
  - `test_migration_fn_prices_resolved.py`: 関数作成/削除と区間条件文字列の存在を検証。
  - `test_migration_add_price_checks.py`: 追加 CHECK 名の存在を検証。

## まとめ
- 既存マイグレーションは仕様・テスト要件に適合し、即時の致命的エラーはなし。
- 実運用の堅牢性向上として、ドライバ置換のフォールバック、関数 `STABLE` 指定、（必要なら）スキーマ修飾の明示や CHECK の整理を推奨。

