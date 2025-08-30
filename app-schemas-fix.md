# app/schemas クリティカルエラー調査メモ

## 目的
- Pydantic ベースのスキーマ（common/prices/metrics/symbols）における致命的エラーの芽を洗い出し、現状の健全性と改善案を整理する。

## 対象
- 参照ファイル:
  - `app/schemas/common.py`（DateRange）
  - `app/schemas/prices.py`（PriceRowOut）
  - `app/schemas/metrics.py`（MetricsOut）
  - `app/schemas/symbols.py`（SymbolOut）
- 関連テスト:
  - `tests/unit/test_schemas.py`
  - `tests/unit/test_price_row_out_date_serialization.py`

## 概要結論
- 現状のスキーマ定義はテスト要件に適合し、直ちにクラッシュする要素は未検出。
- ただし Pydantic v1/v2 の差異やタイムゾーン取り扱い、JSON 直列化等で“致命化”し得る注意点があるため、予防策を提示する。

## 詳細調査（要点）

### 1) DateRange（`app/schemas/common.py`）
- `from_`（alias: `from`）と `to` の順序検証を `field_validator('to')` で実施。`ConfigDict(populate_by_name=True)` により、エイリアス/実名どちらでも入力可能。
- テスト（`test_date_range_invalid_order_raises`）に合致。
- 注意点:
  - v1 互換不要なら問題なし。v1 系で動かす場合は `ValidationInfo` など API 差異あり（本プロジェクトは v2 指向）。

### 2) PriceRowOut（`app/schemas/prices.py`）
- Pydantic v2/v1 両対応の import ガードを実装済み。`last_updated` は tz-aware を強制し、UTC 正規化。`date` は date 型（JSON では YYYY-MM-DD）。
- `test_price_row_out_date_serialization.py` と `test_schemas.py` の期待に整合（naive datetime は ValidationError、UTC へ正規化）。
- 注意点/ハマり所:
  - 入力 `volume` 型は int 前提。外部 I/O 層で float/str が来るとバリデーションエラーに。I/O 側で正規化する前提で妥当。
  - `last_updated` の UTC 正規化により、実際の DB のタイムゾーン（`now()`）がローカル TZ でも表示は UTC となる。仕様どおりだが、運用でのギャップに注意。

### 3) MetricsOut / SymbolOut
- 単純なフィールド集合で、型整合に問題なし。

## クリティカル化し得るポイントと対処
- Pydantic v1/v2 のミックス
  - 事象: 本スキーマは v2 を前提（`field_validator`/`ValidationInfo` 等）。`PriceRowOut` は v1 フォールバックを持つが、`DateRange` は v2 固定。
  - 対処: ランタイムは v2 で固定し、CI で import チェック。v1 互換を強めるなら `common.py` も v1 フォールバックを実装（任意）。
- JSON 直列化の差
  - 事象: v1 と v2 で `model_dump_json()`/`json()` の API が異なる。テストは両対応ヘルパーで回避済みだが、呼び出し側実装で混同すると落ちる。
  - 対処: コード側は `model_dump()`/`model_dump_json()` を優先。v1 環境では呼び出し箇所にフォールバック実装を用意。
- タイムゾーンの厳格化
  - 事象: `last_updated` が naive の場合に ValidationError で落ちる。上流で tz を落とすミドルウェア/ORM 設定があると障害に直結。
  - 対処: DB 層は `timestamptz` を堅持し、値取得時は tz-aware を保証する（現状 OK）。もし ORM 経由で naive が来るケースがあるなら、取り出し時に `timezone.utc` を付与（運用側ガイド）。

## 推奨（任意・最小差分案）
1) `common.DateRange` に v1 フォールバックを追加（必要時）
   - v1 互換が要る場合のみ、`ValidationInfo`/`field_validator` の代替実装を追加。

2) ドキュメント補足
   - `schemas/prices.py` の UTC 正規化仕様を README/docs に明記。

## スモーク/検証（参考）
- DateRange: `DateRange(from_='2024-01-02', to='2024-01-01')` が ValidationError。
- PriceRowOut: naive `last_updated` で ValidationError、tz-aware は UTC へ変換。

## まとめ
- 現状のスキーマは v2 前提で安定。`PriceRowOut` は v1 フォールバック済み。運用の安定性向上として、v1 混在を避けるバージョン固定、UTC 正規化の明記を推奨。

