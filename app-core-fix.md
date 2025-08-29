以下は app/core を中心に実際のソースを読み込んでのデバッグ結果 と、“とにかく小さく・テスト可能・単一関心” な修正タスク一覧です。
（閲覧した主なファイル：app/core/config.py、app/core/cors.py、app/core/middleware.py、app/main.py、requirements.txt、Makefile）


---

🔎 クリティカルな不具合

1) CORS ミドルウェアの登録方法が誤っている（アプリ起動時に TypeError）

症状: app/main.py で CORS ミドルウェアを追加する際に app.add_middleware(*cors) としており、辞書を位置引数として渡してしまうため FastAPI/Starlette の add_middleware シグネチャと一致せず、起動時に TypeError を引き起こします。create_cors_middleware の返り値は (MiddlewareClass, kwargs_dict) なので、**kwargs 展開が必要です。根拠コード：main.py 内で create_cors_middleware(settings) の戻り値をそのまま * 展開して渡している実装。

影響: FastAPI アプリが正常起動できない（uvicorn app.main:app で起動時例外）。

正しい呼び出し例:

Middleware, options = create_cors_middleware(settings)
app.add_middleware(Middleware, **options)

（create_cors_middleware が None の場合は追加しない）



---

🧩 参考：確認できた設計・前提

設定は Pydantic v2 系（pydantic-settings v2）で実装。Settings.model_config = SettingsConfigDict(...) など v2 構文。

CORS 設定は "*" を含む場合に allow_origin_regex を使い、allow_credentials=False に落とすなど、Starlette の制約に沿った堅実な実装。返り値は (CORSMiddleware, kwargs)。

リクエスト ID ミドルウェアは ContextVar で ID を保持し、レスポンスヘッダ X-Request-ID を付与。

依存関係とツール:

fastapi==0.111.0, uvicorn==0.29.0, sqlalchemy[asyncio]==2.0.29, pytest==8.2.0 など。

Makefile に format: black . があるが、requirements.txt に black 記載なし（フォーマット用ターゲット実行でコケる可能性）。




---

🛠 最小修正パッチ（人間可読の差分）

> 対象: app/main.py（ミドルウェア登録の修正）



- cors = create_cors_middleware(settings)
- if cors:
-     app.add_middleware(*cors)
+ cors = create_cors_middleware(settings)
+ if cors:
+     Middleware, options = cors
+     app.add_middleware(Middleware, **options)


---

✅ 再現と検証の手順（ローカル）

> バイナリ生成は不要。既存の Makefile と pytest を使用。



1. 依存を入れる

make install

（補足：make format を使う場合は black が未インストールのため失敗する可能性あり。後述のタスクで対応）


2. 事前に不具合の再現（修正前に実行すると起動時に TypeError が出るはず）

python -m uvicorn app.main:app


3. 上記パッチ適用後、再度起動確認

python -m uvicorn app.main:app

→ 起動成功（ログにエラーが出ず、アプリが待受状態になること）。


4. CORS の最低限動作確認（例：CORS_ALLOW_ORIGINS="*" で起動し、任意の Origin からプリフライト / 通常リクエストが通る）




---

📋 エラー修正タスクリスト（小さく・テスト可能・単一関心）

> 進捗欄は更新可能（Not started / In progress / Done）。
他の LLM は コーディングのみ を担当する前提です。



ID	範囲	タスク（1 行動）	完了の定義（DoD）	検証方法	進捗

T1	app/main.py	app.add_middleware(*cors) を キーワード展開 に変更（Middleware, options = cors; app.add_middleware(Middleware, **options)）	アプリが起動し、TypeError が出ない	python -m uvicorn app.main:app が正常起動する	☐
T2	tests/	起動健全性テストを追加：from app.main import app → TestClient(app) を開いて 404 でも良いので 1 リクエストが成功する	CI/ローカルでテストが緑	pytest -q がパスする（新規テスト名例：test_app_starts）	☐
T3	app/core/cors.py	create_cors_middleware の ユニットテスト（3 ケース：①空文字→None、②*→allow_origin_regex & allow_credentials=False、③複数 Origin→allow_origins & allow_credentials=True）	3 ケースの期待が満たされる	追加テスト tests/test_core_cors.py がパス	☐
T4	app/core/middleware.py	RequestIDMiddleware の ユニット/薄い結合テスト（ヘッダ付与・ContextVar 取得）	① レスポンスに X-Request-ID が付く ② get_request_id() が値を返す	tests/test_request_id_middleware.py がパス	☐
T5	app/core/config.py	Settings の 環境変数上書きテスト（例：CORS_ALLOW_ORIGINS="*" を読み込める）	期待値で Settings().CORS_ALLOW_ORIGINS が得られる	monkeypatch で環境を差し替えるテストがパス	☐
T6	Makefile + 依存	format ターゲットの 実行可能化：requirements.txt に black を追加 または pipx run black . に変更	make format が素の環境で成功	make format の実行結果が 0 戻り値	☐
T7	ルート	ドキュメント更新：README に起動手順（CORS 設定のヒント含む）を明記	README 更新が差分に含まれる	仮想環境新規構築→README 手順で起動成功	☐


> 注: T2–T5 は すべて小さく・独立 に動くように作っています。テストはネットワーク通信不要（依存に pytest-asyncio 等あり）。




---

🧪 追加のテスト雛形（他 LLM 向けの最小コード指針）

> バイナリを作らない 前提で、テストファイルだけ追加。テストはモックと FastAPI TestClient を使用。



tests/test_app_starts.py（T2）

Arrange: from app.main import app; from fastapi.testclient import TestClient

Act: with TestClient(app) as c: r = c.get("/__nonexistent__")

Assert: r.status_code in (404, 200) → アプリが起動すれば OK


tests/test_core_cors.py（T3）

Case1: CORS_ALLOW_ORIGINS="" → create_cors_middleware(settings) は None

Case2: "*" → 戻り値が (CORSMiddleware, {"allow_origin_regex": ".*", "allow_credentials": False, ...})

Case3: "https://a.example, https://b.example" → allow_origins == ["https://a.example","https://b.example"], allow_credentials=True


tests/test_request_id_middleware.py（T4）

小さな FastAPI アプリをローカルに立てて RequestIDMiddleware を追加

リクエスト送信→レスポンスヘッダに X-Request-ID が付与されること

ルート関数内で get_request_id() が None 以外を返すこと


tests/test_settings_env.py（T5）

monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*") → Settings().CORS_ALLOW_ORIGINS == "*"




---

（任意）品質改善の小粒タスク

ID	範囲	タスク	目的	進捗

Q1	app/core/middleware.py	型注釈を Callable[[Request], Response] から RequestResponseEndpoint に	Starlette の実型に揃えて MyPy での誤検知を減らす	☐
Q2	ルート	pre-commit 導入（black/ruff/pytest の簡易フック）	自動整形＆簡易静的解析	☐



---

参照したファイル（証跡）

app/main.py（CORS 追加箇所の不具合）

app/core/cors.py（返り値が (MiddlewareClass, kwargs) であること）

app/core/middleware.py（Request ID 実装）

app/core/config.py（Pydantic v2 系設定）

requirements.txt（利用ライブラリ）

Makefile（format: black . と依存不整合）


> 備考: GitHub のディレクトリ表示が環境上で一部エラーになったため（“Uh oh!” 表示）、ファイルは .../raw/... で直接読み取りました。上記の証跡は実際に取得できたファイルに限定しています。他の app/core/* ファイル（例：exceptions.py 等）は本環境からは確認できませんでしたが、今回のクリティカル修正には影響しません。




---

まとめ

クリティカルな起動阻害要因は CORS ミドルウェアの登録方法の誤りです。**kwargs 展開で修正可能。

併せて、小粒なユニットテストを追加し起動健全性を担保、Makefile の体験不整合（black 未導入）も直すと開発体験が改善されます。


