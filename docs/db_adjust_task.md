# 価格調整検出・自動修正機能 - 実装タスクリスト

**作成日**: 2025-11-30  
**参照**: `docs/db_adjust.md`  
**総工数見積**: 4-5日

---

## 実装ルール

1. **各タスクは独立してテスト可能** - タスク完了時に必ずテストを実行
2. **テスト通過を確認してから次へ** - 赤→緑→リファクタのサイクル
3. **コミット単位** - 1タスク = 1コミット（`feat/TID-ADJ-XXX`）

---

## Phase 1: 検出サービス実装（2-3日）

### TID-ADJ-001: 設定項目の追加
**優先度**: 🔴 高  
**工数**: 0.5h  
**依存**: なし

**成果物**: 
- `app/core/config.py`
- `.env.example`
- `tests/test_adjustment_config.py`

**開始条件**:
- なし（最初のタスク）

**実装内容**:
- [ ] `app/core/config.py` に設定項目追加
  - `ADJUSTMENT_CHECK_ENABLED: bool = True`
  - `ADJUSTMENT_MIN_THRESHOLD_PCT: float = 0.001`
  - `ADJUSTMENT_SAMPLE_POINTS: int = 10`
  - `ADJUSTMENT_MIN_DATA_AGE_DAYS: int = 60`
  - `ADJUSTMENT_AUTO_FIX: bool = False`
- [ ] `.env.example` に設定例を追加

**完了条件（テスト）**:
```bash
pytest tests/test_adjustment_config.py -v
```
- [ ] `test_adjustment_settings_defaults` - デフォルト値確認
- [ ] `test_adjustment_settings_from_env` - 環境変数からの読み込み確認
- [ ] 全テストパス ✅

---

### TID-ADJ-002: 基本クラス・Enum定義
**優先度**: 🔴 高  
**工数**: 1h  
**依存**: TID-ADJ-001 ✅

**成果物**: 
- `app/services/adjustment_detector.py`（新規作成）
- `tests/test_adjustment_detector.py`（新規作成）

**開始条件**:
- TID-ADJ-001 のテストがすべてパス

**実装内容**:
- [ ] `AdjustmentType` Enum
  - `STOCK_SPLIT`, `REVERSE_SPLIT`, `DIVIDEND`, `SPECIAL_DIVIDEND`, `CAPITAL_GAIN`, `SPINOFF`, `UNKNOWN`
- [ ] `AdjustmentSeverity` Enum
  - `CRITICAL`, `HIGH`, `NORMAL`, `LOW`
- [ ] `DetectionThresholds` データクラス
  - `float_noise_pct: float = 0.0001`
  - `min_detection_pct: float = 0.001`
  - `split_threshold_pct: float = 10.0`
  - `special_div_threshold_pct: float = 2.0`
  - `spinoff_threshold_pct: float = 15.0`
  - `sample_points: int = 10`
  - `min_data_age_days: int = 60`

**完了条件（テスト）**:
```bash
pytest tests/test_adjustment_detector.py::TestEnumsAndDataclasses -v
```
- [ ] `test_adjustment_type_values` - Enum値確認
- [ ] `test_adjustment_severity_values` - Enum値確認
- [ ] `test_detection_thresholds_defaults` - デフォルト値確認
- [ ] `test_detection_thresholds_custom` - カスタム値確認
- [ ] 全テストパス ✅

---

### TID-ADJ-003: 高精度価格比較メソッド
**優先度**: 🔴 高  
**工数**: 1h  
**依存**: TID-ADJ-002 ✅

**成果物**: 
- `app/services/adjustment_detector.py`（追記）
- `tests/test_adjustment_detector.py`（追記）

**開始条件**:
- TID-ADJ-002 のテストがすべてパス

**実装内容**:
- [ ] `PrecisionAdjustmentDetector` クラス作成
- [ ] `__init__(self, thresholds)` - 閾値設定
- [ ] `_compare_with_precision(db_price, yf_price)` 実装
  - Decimal型で高精度計算
  - 乖離率（%）と有意性フラグを返却
  - ゼロ除算対策
  - 浮動小数点ノイズ除外（0.0001%未満）

**完了条件（テスト）**:
```bash
pytest tests/test_adjustment_detector.py::TestCompareWithPrecision -v
```
- [ ] `test_compare_identical_prices` - 同一価格 → 0%, False
- [ ] `test_compare_significant_difference` - 1%差 → 1.0%, True
- [ ] `test_compare_noise_level` - 0.00001%差 → False（ノイズ）
- [ ] `test_compare_threshold_boundary` - 0.001%ちょうど → True
- [ ] `test_compare_zero_price` - ゼロ価格 → 0%, False
- [ ] 全テストパス ✅

---

### TID-ADJ-004: イベント分類メソッド
**優先度**: 🔴 高  
**工数**: 3h  
**依存**: TID-ADJ-003 ✅

**成果物**: 
- `app/services/adjustment_detector.py`（追記）
- `tests/test_adjustment_detector.py`（追記）

**開始条件**:
- TID-ADJ-003 のテストがすべてパス

**実装内容**:
- [ ] `_classify_event(pct_diff, ticker, check_date)` 実装
  - 株式分割検出（乖離10%以上 + splits履歴あり）
  - 逆分割検出（factor < 1）
  - スピンオフ検出（乖離15%以上 + splits履歴なし）
  - 特別配当検出（乖離2%以上 + 平均の2倍以上の配当）
  - 通常配当検出（dividends履歴あり）
  - キャピタルゲイン検出（ETF用、capital_gains履歴）
  - 不明イベント（上記に該当しない）

**完了条件（テスト）**:
```bash
pytest tests/test_adjustment_detector.py::TestClassifyEvent -v
```
- [ ] `test_classify_stock_split` - 分割検出（モックticker）
- [ ] `test_classify_reverse_split` - 逆分割検出
- [ ] `test_classify_dividend` - 配当検出
- [ ] `test_classify_special_dividend` - 特別配当検出
- [ ] `test_classify_spinoff` - スピンオフ検出
- [ ] `test_classify_unknown` - 不明イベント
- [ ] 全テストパス ✅

---

### TID-ADJ-005: サンプル価格取得メソッド
**優先度**: 🔴 高  
**工数**: 2h  
**依存**: TID-ADJ-003 ✅

**成果物**: 
- `app/services/adjustment_detector.py`（追記）
- `tests/test_adjustment_detector.py`（追記）

**開始条件**:
- TID-ADJ-003 のテストがすべてパス

**実装内容**:
- [ ] `get_sample_prices(session, symbol)` 実装
  - 60日以上前のデータのみ対象
  - 等間隔で最大10ポイントをサンプリング
  - 最古と最新（閾値内）を必ず含む
  - データ不足時は空リスト返却

**完了条件（テスト）**:
```bash
pytest tests/test_adjustment_detector.py::TestGetSamplePrices -v
```
- [ ] `test_sample_prices_normal` - 正常ケース（モックDB）
- [ ] `test_sample_prices_insufficient_data` - データ不足 → 空リスト
- [ ] `test_sample_prices_includes_oldest_newest` - 最古・最新を含む
- [ ] `test_sample_prices_respects_age_limit` - 60日制限
- [ ] 全テストパス ✅

---

### TID-ADJ-006: 単一シンボル検出メソッド
**優先度**: 🔴 高  
**工数**: 2h  
**依存**: TID-ADJ-004 ✅, TID-ADJ-005 ✅

**成果物**: 
- `app/services/adjustment_detector.py`（追記）
- `tests/test_adjustment_detector.py`（追記）

**開始条件**:
- TID-ADJ-004, TID-ADJ-005 のテストがすべてパス

**実装内容**:
- [ ] `detect_adjustments(session, symbol)` 実装
  - DBからサンプル取得
  - yfinanceから同期間の調整済み価格取得
  - 各サンプルポイントを比較
  - 有意な乖離があればイベント分類
  - 結果をDict形式で返却
  - エラーハンドリング（yfinance接続失敗等）

**完了条件（テスト）**:
```bash
pytest tests/test_adjustment_detector.py::TestDetectAdjustments -v
```
- [ ] `test_detect_no_adjustment_needed` - 調整不要ケース
- [ ] `test_detect_split_detected` - 分割検出ケース
- [ ] `test_detect_dividend_detected` - 配当検出ケース
- [ ] `test_detect_yfinance_error` - yfinanceエラー時
- [ ] `test_detect_insufficient_data` - データ不足時
- [ ] 全テストパス ✅

---

### TID-ADJ-007: 全シンボルスキャンメソッド
**優先度**: 🔴 高  
**工数**: 2h  
**依存**: TID-ADJ-006 ✅

**成果物**: 
- `app/services/adjustment_detector.py`（追記）
- `tests/test_adjustment_detector.py`（追記）

**開始条件**:
- TID-ADJ-006 のテストがすべてパス

**実装内容**:
- [ ] `scan_all_symbols(session, symbols, auto_fix)` 実装
  - symbols省略時は全アクティブシンボル取得
  - 各シンボルをループ処理
  - サマリー統計の集計（by_type, by_severity）
  - needs_refresh, no_change, errorsを分類
  - 進捗ログ出力

**完了条件（テスト）**:
```bash
pytest tests/test_adjustment_detector.py::TestScanAllSymbols -v
```
- [ ] `test_scan_multiple_symbols` - 複数シンボルスキャン
- [ ] `test_scan_summary_statistics` - サマリー統計確認
- [ ] `test_scan_categorization` - needs_refresh/no_change/errors分類
- [ ] `test_scan_empty_symbols` - 空シンボルリスト
- [ ] 全テストパス ✅

---

### TID-ADJ-008: 自動修正メソッド
**優先度**: 🟡 中  
**工数**: 2h  
**依存**: TID-ADJ-007 ✅

**成果物**: 
- `app/services/adjustment_detector.py`（追記）
- `tests/test_adjustment_detector.py`（追記）

**開始条件**:
- TID-ADJ-007 のテストがすべてパス

**実装内容**:
- [ ] `auto_fix_symbol(session, symbol)` 実装
  - 既存の `bulk_delete_prices` を利用
  - 既存の Fetch Job 作成機能を利用
  - 削除行数と作成したジョブIDを返却
  - ログ出力

**完了条件（テスト）**:
```bash
pytest tests/test_adjustment_detector.py::TestAutoFix -v
```
- [ ] `test_auto_fix_deletes_prices` - 価格削除確認
- [ ] `test_auto_fix_creates_job` - ジョブ作成確認
- [ ] `test_auto_fix_returns_stats` - 統計返却確認
- [ ] 全テストパス ✅

---

### TID-ADJ-009: Phase 1 統合テスト
**優先度**: 🔴 高  
**工数**: 1h  
**依存**: TID-ADJ-008 ✅

**成果物**: 
- `tests/test_adjustment_detector.py`（統合テスト追記）

**開始条件**:
- TID-ADJ-008 のテストがすべてパス

**実装内容**:
- [ ] 全テストを通しで実行
- [ ] カバレッジ確認（80%以上目標）

**完了条件（テスト）**:
```bash
pytest tests/test_adjustment_detector.py -v --cov=app/services/adjustment_detector
```
- [ ] 全テストパス
- [ ] カバレッジ 80%以上
- [ ] Phase 1 完了 ✅

---

## Phase 2: APIエンドポイント実装（1日）

### TID-ADJ-010: スキーマ定義
**優先度**: 🔴 高  
**工数**: 1h  
**依存**: Phase 1 完了 ✅

**成果物**: 
- `app/schemas/maintenance.py`（新規作成）
- `tests/test_maintenance_schemas.py`（新規作成）

**開始条件**:
- TID-ADJ-009 (Phase 1 統合テスト) 完了

**実装内容**:
- [ ] `AdjustmentCheckRequest` スキーマ
  - `symbols: Optional[List[str]]`
  - `auto_fix: bool = False`
  - `threshold_pct: float = 0.001`
- [ ] `AdjustmentEvent` スキーマ（single event）
- [ ] `AdjustmentCheckResponse` スキーマ（サマリー付き）
- [ ] `AdjustmentFixRequest` スキーマ
- [ ] `AdjustmentFixResponse` スキーマ

**完了条件（テスト）**:
```bash
pytest tests/test_maintenance_schemas.py -v
```
- [ ] `test_adjustment_check_request_defaults` - デフォルト値
- [ ] `test_adjustment_check_request_validation` - バリデーション
- [ ] `test_adjustment_event_schema` - イベントスキーマ
- [ ] `test_adjustment_fix_request_requires_confirm` - confirm必須
- [ ] 全テストパス ✅

---

### TID-ADJ-011: check-adjustments エンドポイント
**優先度**: 🔴 高  
**工数**: 2h  
**依存**: TID-ADJ-010 ✅

**成果物**: 
- `app/api/v1/maintenance.py`（新規作成）
- `tests/test_maintenance_api.py`（新規作成）

**開始条件**:
- TID-ADJ-010 のテストがすべてパス

**実装内容**:
- [ ] `POST /v1/maintenance/check-adjustments` 実装
- [ ] X-Cron-Secret 認証
- [ ] リクエストボディからパラメータ取得
- [ ] 検出サービス呼び出し
- [ ] レスポンス形式準拠
- [ ] エラーハンドリング

**完了条件（テスト）**:
```bash
pytest tests/test_maintenance_api.py::TestCheckAdjustments -v
```
- [ ] `test_check_adjustments_auth_required` - 認証なし → 401
- [ ] `test_check_adjustments_success` - 正常系（モック）
- [ ] `test_check_adjustments_with_symbols` - symbols指定
- [ ] `test_check_adjustments_empty_response` - 調整不要時
- [ ] 全テストパス ✅

---

### TID-ADJ-012: adjustment-report エンドポイント
**優先度**: 🟡 中  
**工数**: 1h  
**依存**: TID-ADJ-011 ✅

**成果物**: 
- `app/api/v1/maintenance.py`（追記）
- `tests/test_maintenance_api.py`（追記）

**開始条件**:
- TID-ADJ-011 のテストがすべてパス

**実装内容**:
- [ ] `GET /v1/maintenance/adjustment-report` 実装
- [ ] X-Cron-Secret 認証
- [ ] 最新のスキャン結果を返却（メモリキャッシュ or DB保存）
- [ ] レポートがない場合は適切なレスポンス

**完了条件（テスト）**:
```bash
pytest tests/test_maintenance_api.py::TestAdjustmentReport -v
```
- [ ] `test_adjustment_report_auth_required` - 認証なし → 401
- [ ] `test_adjustment_report_no_data` - レポートなし → 404
- [ ] `test_adjustment_report_with_data` - レポートあり
- [ ] 全テストパス ✅

---

### TID-ADJ-013: fix-adjustments エンドポイント
**優先度**: 🟡 中  
**工数**: 2h  
**依存**: TID-ADJ-011 ✅

**成果物**: 
- `app/api/v1/maintenance.py`（追記）
- `tests/test_maintenance_api.py`（追記）

**開始条件**:
- TID-ADJ-011 のテストがすべてパス

**実装内容**:
- [ ] `POST /v1/maintenance/fix-adjustments` 実装
- [ ] X-Cron-Secret 認証
- [ ] symbols指定で対象を限定可能
- [ ] 各シンボルの修正結果を返却
- [ ] confirm=true 必須（安全装置）

**完了条件（テスト）**:
```bash
pytest tests/test_maintenance_api.py::TestFixAdjustments -v
```
- [ ] `test_fix_adjustments_auth_required` - 認証なし → 401
- [ ] `test_fix_adjustments_confirm_required` - confirm未指定 → 400
- [ ] `test_fix_adjustments_success` - 正常系（モック）
- [ ] `test_fix_adjustments_partial_failure` - 一部失敗時
- [ ] 全テストパス ✅

---

### TID-ADJ-014: ルーター登録
**優先度**: 🔴 高  
**工数**: 0.5h  
**依存**: TID-ADJ-011 ✅

**成果物**: 
- `app/api/v1/router.py`（編集）

**開始条件**:
- TID-ADJ-011 のテストがすべてパス

**実装内容**:
- [ ] maintenance router をインポート
- [ ] v1ルーターに登録
- [ ] タグ設定（"maintenance"）

**完了条件（テスト）**:
```bash
pytest tests/test_maintenance_api.py::TestRouterIntegration -v
```
- [ ] `test_maintenance_router_registered` - ルーター登録確認
- [ ] `test_maintenance_endpoint_accessible` - エンドポイントアクセス可能
- [ ] 全テストパス ✅

---

### TID-ADJ-015: Phase 2 統合テスト
**優先度**: 🔴 高  
**工数**: 1h  
**依存**: TID-ADJ-012 ✅, TID-ADJ-013 ✅, TID-ADJ-014 ✅

**成果物**: 
- `tests/test_maintenance_api.py`（統合テスト追記）

**開始条件**:
- TID-ADJ-012, TID-ADJ-013, TID-ADJ-014 のテストがすべてパス

**実装内容**:
- [ ] 全APIテストを通しで実行
- [ ] カバレッジ確認

**完了条件（テスト）**:
```bash
pytest tests/test_maintenance_api.py -v --cov=app/api/v1/maintenance
```
- [ ] 全テストパス
- [ ] カバレッジ 80%以上
- [ ] Phase 2 完了 ✅

---

## Phase 3: Cron統合（0.5日）

### TID-ADJ-016: 週次調整チェックエンドポイント
**優先度**: 🟡 中  
**工数**: 1h  
**依存**: Phase 2 完了 ✅

**成果物**: 
- `app/api/v1/cron.py`（編集）
- `tests/test_cron_adjustment.py`（新規作成）

**開始条件**:
- TID-ADJ-015 (Phase 2 統合テスト) 完了

**実装内容**:
- [ ] `POST /v1/weekly-adjustment-check` 実装
- [ ] X-Cron-Secret 認証
- [ ] 全アクティブシンボルをチェック
- [ ] auto_fix=False（レポートのみ）
- [ ] 結果をログ出力
- [ ] サマリーをレスポンス

**完了条件（テスト）**:
```bash
pytest tests/test_cron_adjustment.py -v
```
- [ ] `test_weekly_adjustment_check_auth` - 認証確認
- [ ] `test_weekly_adjustment_check_success` - 正常系
- [ ] `test_weekly_adjustment_check_logs` - ログ出力確認
- [ ] 全テストパス ✅

---

### TID-ADJ-017: Cronスクリプト追加
**優先度**: 🟡 中  
**工数**: 0.5h  
**依存**: TID-ADJ-016 ✅

**成果物**: 
- `scripts/cron_adjustment_check.sh`（新規作成）

**開始条件**:
- TID-ADJ-016 のテストがすべてパス

**実装内容**:
- [ ] curlコマンドでエンドポイント呼び出し
- [ ] CRON_SECRET環境変数使用
- [ ] ログファイル出力

**完了条件**:
```bash
# スクリプト実行可能確認
bash -n scripts/cron_adjustment_check.sh
echo $?  # 0 なら成功
```
- [ ] シンタックスエラーなし
- [ ] 実行権限設定済み
- [ ] スクリプト完了 ✅

---

### TID-ADJ-018: render.yaml Cron設定
**優先度**: 🟢 低  
**工数**: 0.5h  
**依存**: TID-ADJ-017 ✅

**成果物**: 
- `render.yaml`（編集）

**開始条件**:
- TID-ADJ-017 完了

**実装内容**:
- [ ] 週次ジョブ定義追加
- [ ] 日曜深夜3時実行
- [ ] スクリプトパス指定

**完了条件**:
```bash
# YAML構文チェック
python -c "import yaml; yaml.safe_load(open('render.yaml'))"
echo $?  # 0 なら成功
```
- [ ] YAML構文エラーなし
- [ ] cron定義含む
- [ ] Phase 3 完了 ✅

---

## Phase 4: ドキュメント更新（0.5日）

### TID-ADJ-019: architecture.md 更新
**優先度**: 🟡 中  
**工数**: 1h  
**依存**: Phase 3 完了 ✅

**成果物**: 
- `architecture.md`（編集）

**開始条件**:
- TID-ADJ-018 (Phase 3) 完了

**実装内容**:
- [ ] 調整検出機能の概要追加
- [ ] 新規APIエンドポイント記載
- [ ] 設定項目一覧追加
- [ ] フロー図更新

**完了条件**:
- [ ] architecture.md に maintenance セクション追加
- [ ] 新規エンドポイント3つの記載あり
- [ ] 設定項目5つの記載あり
- [ ] ドキュメントレビュー完了 ✅

---

### TID-ADJ-020: api-usage-guide.md 更新
**優先度**: 🟡 中  
**工数**: 1h  
**依存**: TID-ADJ-019 ✅

**成果物**: 
- `docs/api-usage-guide.md`（編集）

**開始条件**:
- TID-ADJ-019 完了

**実装内容**:
- [ ] Maintenance Endpoints セクション追加
- [ ] 各エンドポイントの詳細説明
- [ ] リクエスト/レスポンス例
- [ ] エラーコード説明

**完了条件**:
- [ ] api-usage-guide.md に Maintenance セクション追加
- [ ] curl例3つ以上
- [ ] レスポンス例あり
- [ ] ドキュメントレビュー完了 ✅

---

### TID-ADJ-021: README.md 更新
**優先度**: 🟡 中  
**工数**: 0.5h  
**依存**: TID-ADJ-020 ✅

**成果物**: 
- `README.md`（編集）

**開始条件**:
- TID-ADJ-020 完了

**実装内容**:
- [ ] 機能概要に調整検出を追加
- [ ] 環境変数一覧更新
- [ ] 使用例追加

**完了条件**:
- [ ] README.md に価格調整検出機能の記載あり
- [ ] 新規環境変数5つの記載あり
- [ ] Phase 4 完了 ✅
- [ ] **全タスク完了** 🎉

---

## タスクサマリー

| Phase | タスク数 | タスクID | 工数合計 | ステータス |
|-------|----------|----------|----------|------------|
| Phase 1: 検出サービス | 9 | TID-ADJ-001〜009 | 14.5h | ✅ 完了 |
| Phase 2: API | 6 | TID-ADJ-010〜015 | 7.5h | ✅ 完了 |
| Phase 3: Cron統合 | 3 | TID-ADJ-016〜018 | 2h | ✅ 完了 |
| Phase 4: ドキュメント | 3 | TID-ADJ-019〜021 | 2.5h | ✅ 完了 |
| **合計** | **21** | - | **26.5h (約4日)** | **完了** |

---

## 進捗トラッキング

### Phase 1: 検出サービス
| タスクID | タイトル | 完了テスト | ステータス |
|----------|----------|------------|------------|
| TID-ADJ-001 | 設定項目の追加 | `pytest tests/test_adjustment_config.py` | ⬜ |
| TID-ADJ-002 | 基本クラス・Enum定義 | `pytest tests/test_adjustment_detector.py::TestEnumsAndDataclasses` | ⬜ |
| TID-ADJ-003 | 高精度価格比較メソッド | `pytest tests/test_adjustment_detector.py::TestCompareWithPrecision` | ⬜ |
| TID-ADJ-004 | イベント分類メソッド | `pytest tests/test_adjustment_detector.py::TestClassifyEvent` | ⬜ |
| TID-ADJ-005 | サンプル価格取得メソッド | `pytest tests/test_adjustment_detector.py::TestGetSamplePrices` | ⬜ |
| TID-ADJ-006 | 単一シンボル検出メソッド | `pytest tests/test_adjustment_detector.py::TestDetectAdjustments` | ⬜ |
| TID-ADJ-007 | 全シンボルスキャンメソッド | `pytest tests/test_adjustment_detector.py::TestScanAllSymbols` | ⬜ |
| TID-ADJ-008 | 自動修正メソッド | `pytest tests/test_adjustment_detector.py::TestAutoFix` | ⬜ |
| TID-ADJ-009 | Phase 1 統合テスト | `pytest tests/test_adjustment_detector.py --cov` | ⬜ |

### Phase 2: APIエンドポイント
| タスクID | タイトル | 完了テスト | ステータス |
|----------|----------|------------|------------|
| TID-ADJ-010 | スキーマ定義 | `pytest tests/test_maintenance_schemas.py` | ⬜ |
| TID-ADJ-011 | check-adjustments エンドポイント | `pytest tests/test_maintenance_api.py::TestCheckAdjustments` | ⬜ |
| TID-ADJ-012 | adjustment-report エンドポイント | `pytest tests/test_maintenance_api.py::TestAdjustmentReport` | ⬜ |
| TID-ADJ-013 | fix-adjustments エンドポイント | `pytest tests/test_maintenance_api.py::TestFixAdjustments` | ⬜ |
| TID-ADJ-014 | ルーター登録 | `pytest tests/test_maintenance_api.py::TestRouterIntegration` | ⬜ |
| TID-ADJ-015 | Phase 2 統合テスト | `pytest tests/test_maintenance_api.py --cov` | ⬜ |

### Phase 3: Cron統合
| タスクID | タイトル | 完了条件 | ステータス |
|----------|----------|----------|------------|
| TID-ADJ-016 | 週次調整チェックエンドポイント | `pytest tests/test_cron_adjustment.py` | ⬜ |
| TID-ADJ-017 | Cronスクリプト追加 | `bash -n scripts/cron_adjustment_check.sh` | ⬜ |
| TID-ADJ-018 | render.yaml Cron設定 | YAML構文チェック | ⬜ |

### Phase 4: ドキュメント
| タスクID | タイトル | 完了条件 | ステータス |
|----------|----------|----------|------------|
| TID-ADJ-019 | architecture.md 更新 | maintenance セクション追加 | ⬜ |
| TID-ADJ-020 | api-usage-guide.md 更新 | Maintenance セクション追加 | ⬜ |
| TID-ADJ-021 | README.md 更新 | 環境変数記載 | ⬜ |

---

## 依存関係グラフ

```
Phase 1: 検出サービス
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TID-ADJ-001 (config)
    │
    ▼
TID-ADJ-002 (Enum/Dataclass)
    │
    ▼
TID-ADJ-003 (compare_with_precision)
    │
    ├─────────────────┐
    ▼                 ▼
TID-ADJ-004       TID-ADJ-005
(classify)        (sample_prices)
    │                 │
    └────────┬────────┘
             ▼
    TID-ADJ-006 (detect_adjustments)
             │
             ▼
    TID-ADJ-007 (scan_all_symbols)
             │
             ▼
    TID-ADJ-008 (auto_fix)
             │
             ▼
    TID-ADJ-009 (Phase 1 統合テスト)
             │
             ▼ ═══════════════════════════════════════════════

Phase 2: APIエンドポイント
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TID-ADJ-010 (schemas)
             │
             ▼
    TID-ADJ-011 (check-adjustments API)
             │
    ┌────────┼────────┬────────┐
    ▼        ▼        ▼        ▼
TID-ADJ-012  TID-ADJ-013  TID-ADJ-014
(report API) (fix API)    (router)
    │        │            │
    └────────┴────────────┘
             │
             ▼
    TID-ADJ-015 (Phase 2 統合テスト)
             │
             ▼ ═══════════════════════════════════════════════

Phase 3: Cron統合
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TID-ADJ-016 (週次チェック endpoint)
             │
             ▼
    TID-ADJ-017 (cron script)
             │
             ▼
    TID-ADJ-018 (render.yaml)
             │
             ▼ ═══════════════════════════════════════════════

Phase 4: ドキュメント
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TID-ADJ-019 (architecture.md)
             │
             ▼
    TID-ADJ-020 (api-usage-guide.md)
             │
             ▼
    TID-ADJ-021 (README.md)
             │
             ▼
       🎉 全タスク完了
```

---

## 実装順序（推奨）

1. **Day 1**: TID-ADJ-001 → 002 → 003 → 004 → 005
2. **Day 2**: TID-ADJ-006 → 007 → 008 → 009
3. **Day 3**: TID-ADJ-010 → 011 → 012 → 013 → 014 → 015
4. **Day 4**: TID-ADJ-016 → 017 → 018 → 019 → 020 → 021
