

---

実行順の目安

1. A（CORS 起動エラー修正）


2. B（/v1/metrics の text() 化と配列バインド安定化）


3. C（UPSERT のパラメータ形状＋text() 化）


4. D（回帰テスト群／型・Lint）




---

タスク一覧

A. CORS 起動エラーの修正（app/main.py）

ID	タスク	変更ファイル	実装ステップ	受け入れ条件（テスト観点）	進捗

A-1	CORS ミドルウェア登録の呼び出し方を修正	app/main.py	1) cors = create_cors_middleware(settings) の戻り値 (cls, kw) を受け取る  2) app.add_middleware(cls, **kw) として登録する	起動時に例外が発生しない（uvicorn app.main:app --reload / テストで from app.main import app が成功）	☑
A-2	CORS の基本動作ユニットテストを追加	tests/unit/test_cors.py（新規）	1) FastAPI() をテスト用に生成  2) create_cors_middleware({"allow_origins":"*"}) 相当の kwargs を当てて app.add_middleware  3) TestClient で /healthz に Origin 付きでアクセス	レスポンスヘッダに access-control-allow-origin が存在し、資格情報不要（allow_credentials=False の想定）	☑



---

B. /v1/metrics：SQLAlchemy 2.x の text() 必須化＋配列バインド安定化

ID	タスク	変更ファイル	実装ステップ	受け入れ条件（テスト観点）	進捗

B-1	AsyncSession.execute() の第1引数を sqlalchemy.text() に置き換え	app/api/v1/metrics.py	1) from sqlalchemy import text を追加  2) 文字列 SQL を text("...") に包む	依存解決で注入した偽セッション（スタブ）の execute(query, params) において、isinstance(query, TextClause)==True を検証するユニットテストが通る	☑
B-2	ANY(:symbols) を IN :symbols＋bindparam(expanding=True) に変更（安定策）	app/api/v1/metrics.py	1) from sqlalchemy import bindparam  2) text("... WHERE symbol IN :symbols ...").bindparams(bindparam("symbols", expanding=True))  3) パラメータは tuple(symbol_list) で渡す	スタブ execute に渡る params["symbols"] が タプルで、長さが入力シンボル数と一致することを検証	☑
B-3	依存差し替え可能なユニットテストを追加（DB不要）	tests/unit/test_metrics_sql_text.py（新規）	1) FastAPI の dependency_overrides で get_session を非同期スタブに差し替え 2) GET /v1/metrics?symbols=AAPL&from=2024-01-01&to=2024-01-31 を呼び、スタブが TextClause を受けたこと・symbols パラメータが expanding になっていることを assert	当該テストが DB・外部通信無しで成功	☑



---

C. /v1/prices：UPSERT 実行のパラメータ形状＆text() 化

ID	タスク	変更ファイル	実装ステップ	受け入れ条件（テスト観点）	進捗

C-1	df_to_rows の戻り値を「タプル配列」→「辞書配列」に変更	app/services/upsert.py	1) 返却型を List[dict] に変更 2) 各行を { "symbol": ..., "date": ..., "open": ..., ... } 形式で構築 3) NaN 行は continue で除外	ユニットテスト test_df_to_rows_returns_dicts：返却が list[dict] で、キー集合が {"symbol","date","open","high","low","close","volume","source"} に一致	☑
C-2	UPSERT 実行時に text() を使用	app/api/v1/prices.py	1) from sqlalchemy import text を追加 2) sql = text(upsert.upsert_prices_sql()) 3) await session.execute(sql, rows)（辞書配列で executemany）	スタブ execute(query, rows) にて isinstance(query, TextClause)==True、かつ isinstance(rows, list) で 最初の要素が dict であることを検証	☑
C-3	df_to_rows の NaN スキップをテスト	tests/unit/test_upsert_df_to_rows.py（新規）	1) pandas.DataFrame に一部 NaN を含む行を用意 2) df_to_rows() を実行 3) NaN 行が除外されていることを len と中身で検証	テストが成功	☑
C-4	/v1/prices の UPSERT 経路ユニットテスト（依存差し替え）	tests/unit/test_prices_upsert_call.py（新規）	1) get_session を偽セッションに、services.fetcher.fetch を固定 DataFrame を返すスタブに差し替え 2) upsert.upsert_prices_sql を固定 SQL に差し替え 3) GET /v1/prices?... を呼ぶ 4) スタブ execute が TextClause＋辞書配列で呼ばれたことを検証	DB・外部通信無しでテストが成功	☑



---

D. 回帰テスト・型・Lint

ID	タスク	変更ファイル	実装ステップ	受け入れ条件（テスト観点）	進捗

D-1	既存 E2E のスモーク（/healthz, /v1/symbols の最低限）	tests/e2e/test_smoke.py（新規 or 既存補強）	1) TestClient(app) で /healthz 200 を確認 2) /v1/symbols は依存差し替えで DB 必須を避けるか、モックセッションで 200/空配列を返す	いずれも 200 が返る	☑
D-2	Row 上限・シンボル上限の単体テスト（依存差し替え）	tests/unit/test_limits.py（新規）	1) API_MAX_ROWS をテスト用に極小へ monkeypatch 2) /v1/prices で「行数超過」を人工的に発生させ、HTTP 413 を検証 3) /v1/prices でシンボル数上限超過により HTTP 422 を検証	指定の HTTP ステータスとエラーボディを検証	☑
D-3	mypy/ruff/black の通過（型補強・noqa最小）	変更が必要なソース全般	1) List[Dict[str, Any]] 等の型補強 2) 必要最小限の # type: ignore[... ] 3) import 並び替え・format 修正	ruff check .、black --check .、mypy app（警告は既存方針に従う）をローカルor CI で通過	☑



---

実装メモ（他 LLM へのヒント）

依存差し替え（FastAPI）：app.dependency_overrides[get_session] = fake_session_dep を使う。fake_session_dep は async def で yield FakeAsyncSession()。

FakeAsyncSession：async def execute(self, query, params=None): self.calls.append((query, params)); return FakeResult() の最小形でよい。scalars()/fetchall() を返すならダミー実装を付与。

TextClause 判定：from sqlalchemy.sql.elements import TextClause を使い isinstance(query, TextClause)。

pandas 依存：df_to_rows テストでは pd.DataFrame({"open":[...], ...}, index=pd.to_datetime([...])) を用意。NaN は numpy.nan。

ネットワーク遮断：services.fetcher.fetch を monkeypatch でスタブ化（DataFrame を返す）。

外部 DB 不要：全テストはスタブ/モックで完結させる（実 DB に依らない）。



---

進捗トラッカー（運用用）

> 下表は進捗を書き込みやすいように簡略版です（必要に応じてコピーして利用）。



ID	担当	着手	完了	PR #	備考

A-1					
A-2					
B-1					
B-2					
B-3					
C-1					
C-2					
C-3					
C-4					
D-1					
D-2					
D-3					



---

受け入れの最終チェック（全体）

[ ] A：CORS 修正後、import app.main が例外を投げない

[ ] B：/v1/metrics が TextClause で execute し、IN :symbols expanding で安定

[ ] C：UPSERT が TextClause + 辞書配列で executemany になり、NaN 行をスキップ

[ ] D：スモーク／上限制御／型・Lint が全て通過


このリストをそのまま「コーディング担当 LLM」へ渡せば、小さく安全な差分でクリティカルな実行時エラーを潰しつつ、ユニットテストで回帰を防止できます。

