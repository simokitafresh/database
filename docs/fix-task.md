# Fix Task List (spec: architecture.md 準拠)

ソースの優先順位は architecture.md を正本とします（Agents.md §1）。
本タスクは小粒度・テスト可能・単一関心に分割しています。外部I/O（yfinance/DB接続/スリープ等）は必ずモックし、pytest を使用してください。

---

## FX-001: coverage CSV テストの仕様整合（/v1/coverage.csv → /v1/coverage/export）
- 目的: テストをアーキテクチャ仕様の `GET /v1/coverage/export` に合わせる。
- 変更ファイル: `tests/integration/test_csv_export.py`
- テスト: 既存の `/v1/coverage.csv` 呼び出しを `/v1/coverage/export` に置換。ヘッダは aggregated coverage に合わせて検証（symbol, data_start, data_end, data_days, row_count, has_gaps 等）。
- 実装: 変更不要（実装は `app/api/v1/coverage.py` に既存）。
- AC: 対象テストが `/v1/coverage/export` に対してグリーン。
- 進捗: [x] 完了 2025-09-05

## FX-002: metrics CSV テストの削除/無効化（仕様に不存在）
- 目的: architecture.md に `/v1/metrics`/`metrics.csv` がないため、メトリクス関連のCSVテストを無効化。
- 変更ファイル: `tests/integration/test_csv_export.py`
- テスト: `pytest.skip("architecture.mdにmetricsエンドポイントは存在しないためスキップ")` を明示。
- 実装: なし。
- AC: metrics系テストがスキップされ、全体のテスト実行が進行可能。
- 進捗: [x] 完了 2025-09-05

## FX-003: prices CSV テスト撤去→JSONテストへ移行
- 目的: `/v1/prices.csv` は仕様外のため、JSONエンドポイントの検証に置換。
- 変更ファイル: `tests/integration/test_csv_export.py`
- テスト: `/v1/prices?symbols=AAPL&from=YYYY-MM-DD&to=YYYY-MM-DD` を使用し、レスポンスが配列であることと列の値域を検証。
- 実装: なし。
- AC: 旧CSVテストが存在せず、代替のJSONテストがパス。
- 進捗: [x] 完了 2025-09-05

## FX-004: DELETE /v1/prices/{symbol} の統合テスト追加
- 目的: 価格削除APIの完了条件をテストで担保。
- 参考実装: `app/api/v1/prices.py:98` 以降。
- 追加/変更ファイル: `tests/integration/test_delete_prices_api.py`（依存性オーバーライド方式に修正）
- テスト: 正常（全件/期間指定）・エラー（confirm必須/日付逆転/DB例外）をモックセッションで検証。
- 実装: なし（テストのみ）。
- AC: 当該テストがすべてパス。
- 進捗: [x] 完了 2025-09-05

## FX-005: fetch API 余剰コードの削除（create_fetch_job_endpoint）
- 目的: 到達不能な return/except ブロックの重複を除去。
- 変更ファイル: `app/api/v1/fetch.py`
- テスト: `tests/unit/test_fetch_api_handlers.py` で create 例外時 500 を検証（サービスをモック）。
- 実装: 現行コードを確認し、到達不能/重複がないことを検証。追加の修正は不要。
- AC: 新規ユニットテストがパスし、既存の統合テストも影響なしにパス。
- 進捗: [x] 完了 2025-09-05（確認とユニットテスト追加）

## FX-006: fetch API 余剰コードの削除（get_fetch_job_status）
- 目的: 到達不能コードの除去。
- 変更ファイル: `app/api/v1/fetch.py`
- テスト: `tests/unit/test_fetch_api_handlers.py` に status 例外時 500 を追加。
- 実装: 現行コードは単一の try/except 構造で重複/到達不能なし。追加修正不要。
- AC: ユニット/統合テストともにパス。
- 進捗: [x] 完了 2025-09-05（確認とユニットテスト追加）

## FX-007: fetch API 余剰コードの削除（cancel_fetch_job）
- 目的: 到達不能コードの除去。
- 変更ファイル: `app/api/v1/fetch.py`
- テスト: `tests/unit/test_fetch_api_handlers.py` に cancel の例外パス（例外→500）を追加。
- 実装: 現行コードは適切な分岐と例外処理で重複/到達不能なし。追加修正不要。
- AC: ユニット/統合テストともにパス。
- 進捗: [x] 完了 2025-09-05（確認とユニットテスト追加）

## FX-008: 004 fetch_jobs マイグレーションのスモークテスト
- 目的: マイグレーション内容を静的検証（文字列照合）。
- 追加ファイル: `tests/unit/test_migration_create_fetch_jobs.py`
- AC: 当該ユニットテストがパス。
- 進捗: [x] 完了 2025-09-05

## FX-009: 005 coverage view マイグレーションのスモークテスト
- 目的: ビュー作成/削除SQLの存在確認。
- 追加ファイル: `tests/unit/test_migration_create_coverage_view.py`
- AC: 当該ユニットテストがパス。
- 進捗: [x] 完了 2025-09-05

## FX-010: 006 performance indexes マイグレーションのスモークテスト
- 目的: 追加インデックス作成/削除の存在確認。
- 追加ファイル: `tests/unit/test_migration_add_performance_indexes.py`
- AC: 当該ユニットテストがパス。
- 進捗: [x] 完了 2025-09-05

## FX-011: 未使用ファイル削除（coverage_backup.py）
- 目的: デッドコードの除去。
- 変更ファイル: `app/api/v1/coverage_backup.py`（削除済みを確認）
- AC: インポートエラーが発生せず、既存テストがパス。
- 進捗: [x] 完了 2025-09-05（存在しないことを確認）

## FX-012: ドキュメントの文字化け修正（UTF-8化）
- 目的: `docs/implementation-task-list.md` の可読性確認と必要時のみ再保存。
- 変更ファイル: `docs/implementation-task-list.md`
- 手順: 環境依存の表示差であり、ユーザ環境では可読との報告のため変更不要（No-Op）。
- AC: ユーザ環境で可読であること（確認済み）。
- 進捗: [x] 完了 2025-09-05（No-Op）
