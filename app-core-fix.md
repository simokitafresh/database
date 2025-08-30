# app/core クリティカルエラー調査メモ

## 目的
- `app/core`（設定・CORS・ロギング・リクエストID）における致命的エラーの芽を洗い出し、現状の健全性と改善案を整理する。

## 対象
- 参照ファイル:
  - `app/core/config.py`
  - `app/core/cors.py`
  - `app/core/logging.py`
  - `app/core/middleware.py`
- 関連ユニットテスト:
  - `tests/unit/test_config.py`
  - `tests/unit/test_cors.py`
  - `tests/unit/test_logging.py`
  - `tests/unit/test_middleware.py`

## 概要結論
- 現状の実装は、単体テスト観点でクラッシュ・不整合は見当たらない（import/起動/基本動作はOK）。
- ただし運用時に致命化し得る「ハマり所」がいくつかあり、改善余地あり（下記に列挙）。

## 詳細調査ログ（要点）

### 1) 設定: `app/core/config.py`
- `pydantic_settings.BaseSettings` を使用。`.env`（UTF-8）を読み込み。主要キーはテスト期待と整合。
- 既定値が定義されており、環境変数未設定でも起動不能にはならない。
- 注意点（潜在的リスク）:
  - ランタイムの Pydantic / pydantic-settings バージョン不一致で import/動作が壊れる可能性（例: v1 系）。CI/本番でのバージョン固定が望ましい。
  - Windows で `.env` が CP932 等の場合、非 ASCII の値が含まれると文字化け。`env_file_encoding="utf-8"` 前提を守る。

### 2) CORS: `app/core/cors.py`
- `CORS_ALLOW_ORIGINS` 未設定時はミドルウェア無効。`*` 指定時は `allow_origin_regex='.*'` に切替、かつ `allow_credentials=False`。Starlette の制約に準拠。
- 複数オリジンの CSV もトリム済みで処理。`X-Request-ID` を `expose_headers` 渡し。
- 注意点（潜在的リスク）:
  - `*` と個別オリジンの混在時も `regex + credentials=False` にフォールバックする仕様。要件次第では明示のリジェクトに変更も検討可。

### 3) ロギング: `app/core/logging.py`
- `configure_logging()` は root logger のハンドラをクリアして JSON フォーマッタを 1 本設定（`level/name/message`）。
- テストはこの前提で JSON 出力を検証。動作問題なし。
- 注意点（潜在的リスク）:
  - Uvicorn/Gunicorn 等の既定ハンドラを上書きするため、実行順に依存（先に Uvicorn が構築 → 本関数がクリア など）。導入箇所は慎重に（アプリ起動初期 or 明示的フラグ制御）。
  - `logger.info(..., extra={...})` を使うコード（例: API 層）と組合せる際、フォーマッタによっては `KeyError` を誘発する実装があるため、JSON フォーマッタと `extra` キー設計の整合が必要。

### 4) ミドルウェア: `app/core/middleware.py`
- `RequestIDMiddleware` は `BaseHTTPMiddleware` で `X-Request-ID` を付与し、`contextvars` に保存。ユニットテストの想定どおり正常系でヘッダとログに反映。
- 注意点（潜在的リスク）:
  - `call_next(request)` 内で未捕捉例外が発生した場合、現在の実装ではレスポンスヘッダ付与処理に到達しないため、エラーレスポンスに `X-Request-ID` が付かない可能性。
    - 発生条件: 例外がアプリ側で捕捉されず、本ミドルウェアから例外がそのまま伝播する場合。
    - 影響: 障害時のトレース性が低下（“致命的運用上の痛点”）。

## 推奨変更（最小差分案・任意）

1) エラーレスポンスにも Request-ID を付与する
- ASGI レベルで `send` をラップし、`http.response.start` イベントにヘッダを追加する実装に切替えると、例外時も確実にヘッダを注入可能。
- 参考パッチ案（方針サンプル・未適用）:
```
class RequestIDASGIMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = None
        def _set_rid(msg):
            nonlocal rid
            if rid is None:
                rid = scope.get("headers", [])
            # 実際には scope/headers から X-Request-ID を抽出 or 生成し保持

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                # (b"x-request-id", value) を追加
            await send(message)

        await self.app(scope, receive, send_wrapper)
```
- あるいは `BaseHTTPMiddleware` 継続利用なら、`try/except` で例外時に暫定レスポンスを作らず re-raise しつつ、`Response` オブジェクトに依存せずヘッダ設定するのは困難。ASGI 実装が堅牢。

2) ロギング初期化の導入ポイントを明確化
- `app/main.py` 側で `configure_logging(settings.LOG_LEVEL)` を呼ぶ場合、Uvicorn のロガー初期化順との競合に注意。確実性が必要なら:
  - 環境変数（例: `JSON_LOGGING=true`）で切替える。
  - CLI/エントリポイントで起動前に一度だけ設定。

3) CORS の運用ガード
- `CORS_ALLOW_ORIGINS` に `*` を含む設定は、社内検証環境のみ許可とする運用ルールを明文化。必要なら値検証を追加し、`APP_ENV == 'production'` で `*` を拒否する等の安全策を導入可能。

4) 設定のバージョン互換
- ランタイムの Pydantic 周辺バージョン固定（`pydantic>=2` と `pydantic-settings>=2` の組）を推奨。CI で import 確認を含める。

## スモーク確認手順（参考）
- アプリ起動: `uvicorn app.main:app --reload`
- ヘルス: `GET /healthz` → `{"status":"ok"}`
- CORS: `CORS_ALLOW_ORIGINS=*` のとき、Origin 付きリクエストで `access-control-allow-origin` が反映、かつ `allow-credentials` が付与されないこと。
- Request-ID: 正常系リクエストでレスポンスヘッダ `X-Request-ID` が付与され、エンドポイント内で `get_request_id()` が参照できること。
  - 改善後（ASGI 実装へ置換）の場合、例外系レスポンスでも `X-Request-ID` が付与されること。

## テスト（参考）
- 既存: `test_config.py`, `test_cors.py`, `test_logging.py`, `test_middleware.py` は現状パス。
- 追加推奨（改善後）:
  - 例外発生時にも `X-Request-ID` がレスポンスに付与されることを検証するユニットテスト。

## まとめ
- 現状の `app/core` は単体テスト観点で致命的エラーなし。
- 運用時のトレーサビリティ確保のため、Request-ID の例外時付与（ASGI 実装への切替）と、ロギング初期化の導入ポイントのルール化を推奨。

