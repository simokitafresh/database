# app/api クリティカルエラー調査メモ

## 目的
- `app/api` 配下および `app/api/v1` ルータ層の「致命的エラー」要因を洗い出し、現状の健全性と改善案を整理する。

## 対象
- 参照ファイル:
  - `app/api/errors.py`
  - `app/api/deps.py`
  - `app/api/v1/health.py`
  - `app/api/v1/router.py`
  - `app/api/v1/symbols.py`
  - `app/api/v1/prices.py`
  - `app/api/v1/metrics.py`
  - 関連: `app/main.py`, `app/db/queries.py`, `app/services/*`, `app/schemas/*`

## 概要結論
- 走査時点で import/アプリ起動段階でクラッシュする要素は確認できず（設計・依存性・入出力スキーマは整合）。
- 一方、運用上の「ハマり所」や誤設定で致命化し得るポイントが複数あるため、再発防止観点での推奨事項を提示する。

## 調査ログ（要点）
- エラーハンドラ: `app/api/errors.py`
  - FastAPI の `HTTPException` と `RequestValidationError` に対し、統一エラーペイロード `{error:{code,message}}` を返すハンドラが登録済み。
  - 404 については `app.add_exception_handler(404, ...)` で個別にも登録。型的には冗長だが挙動としては問題なし（404 も `HTTPException` ハンドラで拾える）。
- 依存性: `app/api/deps.py`
  - DSN ごとに `create_async_engine` → `async_sessionmaker` を LRU キャッシュ。
  - `get_session()` は async generator で `AsyncSession` を `yield`。テストの依存性差し替えとも整合。
- ルータ: `app/api/v1/*`
  - `/healthz`: 正常。
  - `/v1/symbols`: 生 SQL 実行で最小実装。`active` フィルタ対応済み。
  - `/v1/prices`: 入力検証 → カバレッジ確保（`queries.ensure_coverage`）→ 解決済み取得（`queries.get_prices_resolved`）→ 行数上限制御（413）。ログ `extra` 付き。
  - `/v1/metrics`: `TextClause` + `expanding` で `IN (:symbols)` を実行し、`compute_metrics` に渡す前にシンボルごと DataFrame 化。式は仕様に一致。
- アプリ起動: `app/main.py`
  - `lifespan` は `@asynccontextmanager` で「非同期ジェネレータ」を満たす形に修正済み（`AttributeError('__anext__')` を回避）。

## クリティカル化し得るポイントと対処方針
1) 404 ハンドラの二重登録
   - 事象: `HTTPException` ハンドラと 404 個別ハンドラの二重登録は冗長。通常は前者だけで 404 も同一フォーマットにできる。
   - リスク: 実害はほぼ無し（Starlette はステータスコード別ハンドラを優先するため挙動は安定）。
   - 方針: 現行テストは 404 のエラーフォーマットに依存しているため維持でも可。簡素化したい場合は 404 個別ハンドラを削除し、`HTTPException` ハンドラのみに集約可能。

2) ログ `extra` とロギング設定の相性
   - 事象: `app/api/v1/prices.py` の `logger.info("prices served", extra=dict(...))` は、ロガーのフォーマッタが `extra` キーを想定していない場合に `KeyError` を誘発する実装がある。
   - 対策: アプリ標準の `app/core/logging.py` に合わせてフォーマッタを設定するか、`extra` のキーを衝突しにくいプレフィックス（例: `api_`）に統一。

3) Metrics の `IN (:symbols)` とドライバ互換性
   - 事象: SQLAlchemy 2.x の `TextClause.bindparams(expanding=True)` は主要ドライバで動作するが、ローカル実行で SQLite 方言/旧バージョンと組み合わせると `IN ()` の展開で失敗するケースがある。
   - 対策: 本番は PostgreSQL 前提。ローカル簡易検証で SQLite を使う場合は `expanding` 対応を満たす SQLAlchemy バージョンを使用。

4) `get_session` のエンジンライフサイクル
   - 事象: DSN 単位で engine をキャッシュしており、プロセス終了まで保持。テスト大量実行や DSN を切り替えるシナリオで、意図せぬ接続維持が起こり得る。
   - 対策: 問題化する場合のみ、テスト teardown で `engine.dispose()` を呼ぶユーティリティを追加検討。

## 推奨変更（最小差分案）
- 404 ハンドラの簡素化（任意）
  - 対象: `app/api/errors.py`
  - 変更: 404 個別ハンドラを削除し、`HTTPException` ハンドラに集約。
  - 影響: テスト期待フォーマットは `HTTPException` ハンドラで満たせるため維持可能。

例（参考パッチ案・未適用）:
```
diff --git a/app/api/errors.py b/app/api/errors.py
@@
 def init_error_handlers(app: FastAPI) -> None:
     app.add_exception_handler(HTTPException, _http_exception_handler)
     app.add_exception_handler(RequestValidationError, cast(Any, _validation_exception_handler))

-    async def _not_found(request: Request, exc: HTTPException):
-        return _http_exception_handler(request, exc)
-
-    app.add_exception_handler(404, _not_found)
```

- ログ `extra` のキー整理（任意）
  - 対象: `app/api/v1/prices.py`
  - 変更: `extra` のキーに `api_` を付けるなどの衝突回避。ロギング設定が堅牢なら無変更でも可。

## スモーク確認手順（参考）
- アプリ起動（例）:
  - `uvicorn app.main:app --reload`
- ヘルスチェック:
  - `GET /healthz` → `{"status":"ok"}`
- API スモーク:
  - `GET /v1/symbols?active=true`
  - `GET /v1/prices?symbols=AAPL&from=2024-01-01&to=2024-01-31`
  - `GET /v1/metrics?symbols=AAPL&from=2024-01-01&to=2024-01-31`

## テスト（参考）
- 主要カバレッジ:
  - `tests/unit/test_errors.py`（エラー形状の検証: 404/413/422）
  - `tests/unit/test_metrics_api.py`（メトリクス API の整合）
  - `tests/unit/test_symbols_api.py`（クエリパラメータ型/依存性差し替え）
  - `tests/unit/test_limits.py`（行数・シンボル数の上限動作）
  - `tests/unit/test_metrics_sql_text.py`（`TextClause` と `expanding` の使用）

## まとめ
- 現状の `app/api` 実装は仕様・スキーマ・テスト意図に整合しており、即時のクラッシュ要因は見当たらない。
- 運用上の安定性向上として、404 個別ハンドラの簡素化（任意）と、ログ `extra` のキー設計見直し（必要に応じて）を推奨。

