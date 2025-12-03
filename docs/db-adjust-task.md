# 価格調整機能 実装タスクリスト

作成日: 2025-12-03  
参照: `db-adjust-2025-1203.md`

---

## 概要

`corporate_events` テーブルを追加し、価格調整イベント（配当・分割等）の履歴管理・重複防止・監査証跡機能を実装する。

**総工数見積もり**: 4.5日

---

## Phase 1: データベース（1日）

### Task 1.1: マイグレーションファイル作成
- [ ] `app/migrations/versions/xxxx_create_corporate_events.py` 作成
- [ ] テーブル定義
  - [ ] 主キー: `id` (SERIAL)
  - [ ] イベント識別: `symbol`, `event_date`, `event_type`
  - [ ] イベント詳細: `ratio`, `amount`, `currency`, `ex_date`
  - [ ] 検出情報: `detected_at`, `detection_method`, `pct_difference`, `severity`
  - [ ] 修正情報: `status`, `fixed_at`, `fix_job_id`, `rows_deleted`, `rows_refetched`
  - [ ] メタデータ: `source_data` (JSONB), `notes`
- [ ] CHECK制約
  - [ ] `event_type` IN ('stock_split', 'reverse_split', 'dividend', 'special_dividend', 'capital_gain', 'spinoff', 'unknown')
  - [ ] `status` IN ('detected', 'confirmed', 'fixing', 'fixed', 'ignored', 'failed')
  - [ ] `severity` IN ('critical', 'high', 'normal', 'low')
- [ ] UNIQUE制約: `(symbol, event_date, event_type)`
- [ ] 外部キー: `symbol` → `symbols.symbol`
- [ ] インデックス作成
  - [ ] `idx_corp_events_symbol`
  - [ ] `idx_corp_events_date`
  - [ ] `idx_corp_events_type`
  - [ ] `idx_corp_events_status` (WHERE status != 'fixed')
  - [ ] `idx_corp_events_detected`

### Task 1.2: モデル定義
- [ ] `app/db/models.py` に `CorporateEvent` クラス追加
- [ ] SQLAlchemy モデル定義
- [ ] `__table_args__` で制約定義

### Task 1.3: マイグレーション実行・検証
- [ ] ローカル環境でマイグレーション実行
- [ ] テーブル作成確認
- [ ] インデックス確認

---

## Phase 2: スキーマ定義（0.5日）

### Task 2.1: Pydanticスキーマ作成
- [ ] `app/schemas/events.py` 新規作成
- [ ] `CorporateEventBase` - 共通フィールド
- [ ] `CorporateEventCreate` - 作成用
- [ ] `CorporateEventUpdate` - 更新用
- [ ] `CorporateEventResponse` - レスポンス用
- [ ] `CorporateEventListResponse` - 一覧レスポンス（ページネーション付き）
- [ ] `EventTypeEnum` - イベントタイプ列挙
- [ ] `EventStatusEnum` - ステータス列挙
- [ ] `EventSeverityEnum` - 重要度列挙

### Task 2.2: スキーマ登録
- [ ] `app/schemas/__init__.py` にエクスポート追加

---

## Phase 3: サービス層更新（1.5日）

### Task 3.1: adjustment_detector.py 更新
- [ ] `_record_event()` メソッド追加
  - [ ] 検出イベントを `corporate_events` テーブルにINSERT
  - [ ] 既存イベント（UNIQUE制約）はスキップ
- [ ] `detect_adjustments()` 更新
  - [ ] 検出時に `_record_event()` を呼び出し
  - [ ] 既に `status='fixed'` のイベントはスキャン対象外
- [ ] `scan_symbols()` 更新
  - [ ] 重複検出防止ロジック追加

### Task 3.2: adjustment_fixer.py 更新
- [ ] `auto_fix_symbol()` 更新
  - [ ] 修正開始時: `status='fixing'` に更新
  - [ ] 修正完了時: `status='fixed'`, `fixed_at`, `rows_deleted`, `rows_refetched` を更新
  - [ ] 修正失敗時: `status='failed'` に更新
  - [ ] `fix_job_id` に fetch_job の job_id を記録

### Task 3.3: イベントサービス新規作成
- [ ] `app/services/event_service.py` 新規作成
- [ ] `get_events()` - 一覧取得（フィルタ・ページネーション）
- [ ] `get_event_by_id()` - 単一取得
- [ ] `get_events_by_symbol()` - 銘柄別取得
- [ ] `get_pending_events()` - 未処理イベント取得
- [ ] `confirm_event()` - イベント確認
- [ ] `ignore_event()` - イベント無視（誤検出）
- [ ] `get_dividend_calendar()` - 配当カレンダー
- [ ] `get_split_history()` - 分割履歴

---

## Phase 4: API実装（1日）

### Task 4.1: イベントAPIエンドポイント
- [ ] `app/api/v1/events.py` 新規作成
- [ ] `GET /v1/events` - 全イベント一覧
  - [ ] クエリパラメータ: `symbol`, `event_type`, `status`, `from`, `to`, `page`, `page_size`
- [ ] `GET /v1/events/{symbol}` - 銘柄別イベント履歴
- [ ] `GET /v1/events/pending` - 未処理イベント一覧
- [ ] `GET /v1/events/dividends` - 配当カレンダー
  - [ ] クエリパラメータ: `from`, `to`, `symbol`
- [ ] `GET /v1/events/splits` - 分割履歴
  - [ ] クエリパラメータ: `from`, `to`, `symbol`
- [ ] `POST /v1/events/{id}/confirm` - イベント確認（認証必要）
- [ ] `POST /v1/events/{id}/ignore` - 誤検出として無視（認証必要）

### Task 4.2: ルーター登録
- [ ] `app/api/v1/__init__.py` にルーター追加
- [ ] `app/main.py` でルーター登録確認

### Task 4.3: 既存API更新
- [ ] `app/api/v1/maintenance.py` 更新
  - [ ] `/v1/maintenance/adjustment-report` で `corporate_events` を参照
  - [ ] レスポンスにイベントID含める

---

## Phase 5: テスト（0.5日）

### Task 5.1: 単体テスト
- [ ] `tests/test_corporate_events_model.py` - モデルテスト
- [ ] `tests/test_event_service.py` - サービステスト
- [ ] `tests/test_events_api.py` - APIテスト

### Task 5.2: 統合テスト
- [ ] 検出→記録→修正の一連フローテスト
- [ ] 重複検出防止のテスト
- [ ] ステータス遷移テスト

### Task 5.3: 既存テスト更新
- [ ] `tests/test_adjustment_detector.py` 更新
- [ ] `tests/test_cron_adjustment.py` 更新

---

## Phase 6: ドキュメント更新（0.5日）

### Task 6.1: API Usage Guide更新
- [ ] `docs/api-usage-guide.md` にイベントAPIセクション追加
- [ ] エンドポイント一覧
- [ ] リクエスト/レスポンス例

### Task 6.2: アーキテクチャドキュメント更新
- [ ] `docs/architecture.md` 更新
- [ ] ER図に `corporate_events` 追加
- [ ] データフロー図更新

### Task 6.3: README更新
- [ ] `README.md` に機能概要追加

---

## 依存関係

```
Phase 1 (DB)
    ↓
Phase 2 (スキーマ)
    ↓
Phase 3 (サービス) ←─ Phase 1, 2 完了後
    ↓
Phase 4 (API) ←─ Phase 3 完了後
    ↓
Phase 5 (テスト) ←─ Phase 4 完了後
    ↓
Phase 6 (ドキュメント) ←─ 並行可能
```

---

## チェックリスト（デプロイ前）

- [ ] ローカル環境で全テスト通過
- [ ] マイグレーションのロールバック確認
- [ ] ステージング環境でのマイグレーション実行
- [ ] ステージング環境での動作確認
- [ ] 既存機能への影響なし確認
- [ ] パフォーマンス影響確認（スキャン時間）
- [ ] ドキュメント整備完了

---

## ロールバック計画

万が一問題が発生した場合：

1. マイグレーションのダウングレード実行
   ```bash
   alembic downgrade -1
   ```

2. サービス層の変更を revert
   - `adjustment_detector.py`
   - `adjustment_fixer.py`

3. 新規ファイルの削除
   - `app/services/event_service.py`
   - `app/api/v1/events.py`
   - `app/schemas/events.py`

---

## 完了条件

- [ ] 全Phaseのタスク完了
- [ ] 全テスト通過
- [ ] ドキュメント更新完了
- [ ] ステージング環境での動作確認完了
- [ ] コードレビュー完了
- [ ] 本番デプロイ完了
