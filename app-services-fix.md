# app/services クリティカルエラー調査メモ

## 目的
- サービス層（fetcher/metrics/normalize/resolver/upsert）の致命的エラーの芽を洗い出し、運用上のハマり所と最小差分の改善案を整理する。

## 対象
- 参照ファイル:
  - `app/services/fetcher.py`
  - `app/services/metrics.py`
  - `app/services/normalize.py`
  - `app/services/resolver.py`
  - `app/services/upsert.py`
- 関連テスト:
  - `tests/unit/test_fetcher*.py`
  - `tests/unit/test_metrics*.py`
  - `tests/unit/test_resolver.py`
  - `tests/unit/test_upsert_*.py`

## 概要結論
- 現状の実装はユニットテストと仕様に整合し、直ちにクラッシュする要素は未検出。
- ただし、ライブラリの仕様差・運用環境差で“致命化”し得るポイントがあり、予防的な修正/運用ガイドを推奨。

## 詳細調査（要点）

### fetcher.py（Yahoo Finance 取得・リトライ）
- `yf.download()` に `timeout` を渡し、429/999 と各種 Timeout を指数バックオフ（1.0 → 2.0 → …、上限 `FETCH_BACKOFF_MAX_SECONDS`）。
- `last_date` が与えられた場合は `YF_REFETCH_DAYS` だけ巻き戻して取得開始日を繰り下げ（N日再取得）。
- 取得後は列名を小文字化し、`Adj Close` は捨てる。
- リスク/注意:
  - yfinance のバージョンによっては `timeout` 引数未対応の版があり、実行時に `TypeError` で落ちる可能性（テストはモックのため未検知）。
  - yfinance の `end` は多くの版で「排他的」扱いのため、日付の包括性に齟齬が出る可能性（本プロジェクトは inclusive 前提）。
  - 例外捕捉の網羅は妥当だが、`time.sleep` はスレッドをブロック（実利用は `run_in_threadpool` 経由のため問題最小）。

### metrics.py（メトリクス計算）
- 価格列の優先順（`adj_close`→`close`→`Adj Close`）。`date` 列があれば index に採用。共通営業日の交差で整列。
- r=log(Pt/Pt-1)、CAGR=exp(sum(r)*252/N)-1、STDEV=std(r,ddof=1)*sqrt(252)、最大DDは累積対数リターンから。NaN/非有限は0に丸め。
- リスク/注意:
  - 入力に 0 価格が含まれるとログが -inf になり得るが、非有限丸めで吸収（テストで担保）。

### normalize.py（シンボル正規化）
- 取引所サフィックス・クラス株記法（`.` → `-`）の処理。既知サフィックス集合を維持。
- リスク/注意:
  - サフィックス集合のカバレッジ外ケースは素通し（仕様上は許容）。必要に応じ増補。

### resolver.py（1ホップ分割）
- `change_date` 当日は新シンボル、前日は旧シンボルとして分割し、範囲を返す。旧/新どちらの入力でも同一結果。
- リスク/注意:
  - 仕様通り 1ホップのみ対応。複数段の改称が存在するデータ投入は想定外（DDL の `UNIQUE(new_symbol)` で抑止）。

### upsert.py（DataFrame→行、UPSERT SQL）
- NaN 行をスキップして Python 基本型にキャスト。UPSERT は `ON CONFLICT (symbol, date)` で更新し `last_updated=now()`。
- リスク/注意:
  - DataFrame の列欠落時（例: `volume` 無し）に `KeyError`。fetcher からの経路では発生しにくいが、他ソース連携時は注意。

## クリティカル化し得るポイントと対処
1) yfinance の `timeout` 非対応版
   - 事象: 実行時に `TypeError: download() got an unexpected keyword argument 'timeout'`。
   - 対処（最小差分案）:
     - `fetcher.fetch_prices` 内で `TypeError` を捕捉し、`timeout` を外して再試行。
     - もしくは `inspect.signature(yf.download)` で対応引数を事前判定。

2) `end` の包括性（inclusive/exclusive）
   - 事象: 取得最終日のデータが欠落し、カバレッジ検査で不足が解消しない恐れ。
   - 対処（運用/実装）:
     - 実運用で不足が観測される場合に限り、`end + 1 day` を渡すトグルを `Settings` に設ける（例: `YF_END_INCLUSIVE=true`）。デフォルトは現状維持。

3) リトライのブロッキング
   - 事象: `time.sleep` によりスレッドがブロック。イベントループ直下で直呼び出しすると待ち合わせ全体をブロック。
   - 対処: 現状 `queries.fetch_prices_df` から `run_in_threadpool` 経由で呼ぶため OK。別経路導入時のガイドとして明記。

4) DataFrame 列欠落
   - 事象: 他ソース統合時に `volume` などが欠落して変換エラー。
   - 対処: 列検証と欠落時のスキップ/デフォルト適用を `df_to_rows` に導入する余地（任意）。

## 推奨（任意・最小差分案）
1) fetcher の `timeout` フォールバック
   - 古い yfinance では `timeout` を外して再試行するガードを追加。

2) `end` 包括性のトグル化（必要時）
   - `Settings` に `YF_END_INCLUSIVE: bool = True` を追加し、True の場合は `end + timedelta(days=1)` を yfinance に渡す。

3) upsert 変換の堅牢化（必要時）
   - 必須列の存在チェックを追加し、欠落時は行スキップか明示的エラーにする方針を定義。

## スモーク/検証（参考）
- リトライ系: `tests/unit/test_fetcher_retry_timeout.py`, `test_fetcher_http_error.py`, `test_fetcher.py` を参照（モックで網羅）。
- 並行度: `tests/unit/test_fetcher_concurrency.py`（セマフォ遵守）。
- 変換/UPSERT: `tests/unit/test_upsert_df_to_rows.py`, `test_upsert_sql.py`。
- 1ホップ分割: `tests/unit/test_resolver.py`。
- メトリクス: `tests/unit/test_metrics*.py`。

## まとめ
- サービス層は現状テストに合致し安定。一方で yfinance の引数互換・日付の包括性は実運用での“落とし穴”。
- 互換フォールバック（timeout）と、必要に応じた `end` 包括性のトグル導入を推奨。変換処理は将来の他ソース連携時に列検証を強化すると良い。

