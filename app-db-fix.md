リポジトリの app/db とその周辺を読み込み、クリティカルな不整合・実行時エラー要因を洗い出しました。結論から言うと、DBレイヤはPostgreSQL前提の実装とSQLite設定（Alembic/テスト想定）が混在しており、このままだと実行時に確実に落ちる箇所があります。下に根拠→修正方針→超小粒のタスク一覧（進捗を記入できる表）を提示します。


---

クリティカルな問題（根拠付き）

1. SQLAlchemy 2.0系で create_async_engine(..., future=True) を使用

2.0系では future フラグは前提化されており、予期せぬ引数として扱われる可能性が高い（TypeError）。app/db/engine.py を確認すると future=True が渡されています。



2. アプリはPostgreSQL依存のSQLを多用しているのに、Alembic設定はSQLite

価格API(app/api/v1/prices.py)は INTERVAL '1 day' / EXTRACT(ISODOW ...) / ::date などのPostgreSQL専用構文を直接使っています。さらに get_prices_resolved(sym, from, to) というDB関数に依存しています（この関数がDDLで定義されていないと動きません）。

一方、alembic.ini は sqlalchemy.url = sqlite:///./app.db になっており、SQLiteでマイグレーションする前提です。これでは上記SQLは動きません。

依存関係にも aiosqlite が入っており、テストではSQLiteを想定していると読み取れます。



3. advisory_lock の利用はPostgreSQL前提

価格APIは app.db.utils.advisory_lock(conn, sym) を呼びますが、アドバイザリロックはPostgreSQLの機能です。SQLiteでは未サポートのため、そのまま実行すれば例外になります（utils側でSQLiteをno-opにしていない場合）。



4. models.Price.last_updated の server_default=sa.func.now() はSQLite非互換

SQLiteに now() はありません（PostgreSQLはOK）。SQLiteでマイグレーションするとここで壊れます。



5. Alembicは同期エンジン前提・SQLite URL固定

app/migrations/env.py は同期エンジンを起動し、alembic.ini のURLをそのまま使います。実運用をPostgreSQLでやるならAlembic URLもPostgreSQL（同期ドライバ）に統一すべきです。




> 参考：app/db/base.py と app/db/models.py 自体の宣言はSQLAlchemy 2.0向けで概ね妥当（DeclarativeBase/チェック制約/UNIQUE等）ですが、チェック制約で LEAST/GREATEST を使っている点はDB依存の可能性があります（PostgreSQLはOK、SQLiteはビルド/バージョン依存）。




---

推奨の修正方針

方針A（推奨）: PostgreSQLに統一

アプリ実装がPG前提（SQL/ロック/関数）なので、Alembic・ローカル実行・CIもPostgreSQLで統一。SQLite依存は削るか、テストではDBアクセスをモックする。

影響最小で安定化できます（関数get_prices_resolvedのDDLをversionsに追加する／または関数に依存しないSQLへ置換のどちらかを選択）。





以降のタスクは 方針A（PostgreSQL統一） 前提で作っています。必要なら最後に「B案」差分タスクも載せます。


---

エラー修正タスクリスト（小さく・テスト可能・進捗記入可）

> 記号: ☐TODO / ▶進行中 / ✅完了
Ownerは空欄で、渡す先のLLM/エンジニアが埋められるようにしています。



P0: ビルド/起動を止める致命傷の除去

ID	タイトル	問題/目的	完了条件(DoD)	検証(テスト/実行例)	変更ファイル（目安）	Owner	Status

P0-1	future=True削除	SQLAlchemy 2.0で不正引数	create_engine_and_sessionmakerがcreate_async_engine(database_url)で初期化できる	python - <<'PY'\nfrom app.db.engine import create_engine_and_sessionmaker;print('ok')\nPY が例外なく走る（モックでOK）	app/db/engine.py（future=True削除） 		☐
P0-2	AlembicをPG URLに統一	SQLite設定のままだとPG前提のSQLが全滅	alembic.iniのsqlalchemy.urlがpostgresql+psycopg://...に更新。env.pyで環境変数ALEMBIC_SQLALCHEMY_URLが優先される	ALEMBIC_SQLALCHEMY_URL=postgresql+psycopg://... alembic current が動作	alembic.ini, app/migrations/env.py（URL取得を環境変数優先に） 		☐
P0-3	now()をPG互換に固定	SQLite非互換を排除	server_default=text("now()") などPG向け明示にし、Alembic生成/適用が通る	alembic revision --autogenerate → alembic upgrade head がPGで成功	app/db/models.py（last_updated定義の見直し） 		☐


P1: 価格APIのDB依存関数/SQLの整備

ID	タイトル	問題/目的	完了条件(DoD)	検証(テスト/実行例)	変更ファイル（目安）	Owner	Status

P1-1	get_prices_resolvedをDBに実装	APIがDB関数へ依存	AlembicのversionsでPG用DDL追加（CREATE FUNCTION get_prices_resolved(sym text, from date, to date) RETURNS TABLE(...)）。戻り列はAPIのSELECTに一致（symbol,date,open,high,low,close,volume,source,last_updated,source_symbol）	SELECT * FROM get_prices_resolved('AAPL','2024-01-01','2024-01-31') LIMIT 1; がPGで成功	app/migrations/versions/<timestamp>_add_get_prices_resolved.py（op.execute()でDDL） / 必要ならapp/migrationsにSQLファイルを同梱		☐
P1-2	代替案: 関数呼び出しをSQL/アプリ合成に置換	関数作成が困難な場合	get_prices_resolved呼び出しをやめ、アプリ側でresolver.segments_forの結果からUNION ALLのSELECTを生成し、source_symbol列を追加して返す	GET /v1/prices のE2Eモックテストがグリーン	app/api/v1/prices.py（関数呼び出し部の置換） 		☐
P1-3	advisory_lockをPG向けに確定	SQLite想定を排除	utils.advisory_lockがPGでpg_advisory_lock/hashtext等を呼ぶ（connがPG以外ならno-op）	ユニットテストでdialect.name!='postgresql'時は何もしないことを確認	app/db/utils.py（存在しない場合は新規）/ 既存なら方言分岐		☐
P1-4	ギャップ検出SQLの再確認	PG専用構文	INTERVAL/EXTRACT(ISODOW ...)/::date を用いたギャップ検出クエリがPGで動くことを結合テスト（またはsession.executeのスタブ）で確認	pytestでsession.executeモック→想定のmissing_from計算経路が通る	app/api/v1/prices.py（現状維持だがテスト整備） 		☐


P2: 依存と設定の一貫性

ID	タイトル	問題/目的	完了条件(DoD)	検証	変更ファイル	Owner	Status

P2-1	requirements.txt の整理	SQLite依存の混乱	PG統一後も必要ならaiosqliteを残す理由をREADMEに明記。不要なら削除	pip install -r requirements.txt 成功 / README更新	requirements.txt, README.md 		☐
P2-2	設定の単一点管理	AlembicとアプリURLの乖離	ALEMBIC_SQLALCHEMY_URLを優先→未設定ならapp.core.config.settings.DATABASE_URLから派生（同期ドライバに変換）	print(config.get_main_option("sqlalchemy.url")) がPG URLを指す	app/migrations/env.py, app/core/config.py（必要ならコメント追加） 		☐


P3: 起動検証・静的検査

ID	タイトル	目的	完了条件	検証	Owner	Status

P3-1	起動時Import検査	依存モジュールの欠落検知	python -c "import app.main; print('OK')" が通る	例外なし		☐
P3-2	価格APIのハッピーパス（モック）	DB/ネットワークをモックしてAPI面の整合確認	GET /v1/prices の単体テストがグリーン（シンボル数上限、日付順、行数上限バリデーションを含む）	pytest（外部通信なし）		☐
P3-3	モデルのマイグレーション往復	DDLの完全性担保	alembic upgrade head && alembic downgrade base がPGで往復可能	ローカル/CIで実行		☐



---

実装のヒント（コーディング担当用メモ）

P0-1:

# app/db/engine.py
engine = create_async_engine(database_url)  # future=True を削除
session_factory = async_sessionmaker(engine, expire_on_commit=False)

（ユニットは create_async_engine をmocker.patchして引数検証）

P0-2 / P2-2: app/migrations/env.py でURL解決を環境変数優先 → なければ同期ドライバに変換（例：postgresql+asyncpg → postgresql+psycopg）。

P1-1: get_prices_resolved のDDLは 戻り列をAPIのSELECTと一致させてください（symbol,date,open,high,low,close,volume,source,last_updated,source_symbol）。source_symbol は要求シンボルをそのまま返す/もしくはsymbol_changesから導出。**関数を作らない選択（P1-2）**なら、resolver.segments_for の結果からPythonでUNION ALLを組み立てて source_symbol を付加。

P1-3: advisory_lock は conn.dialect.name を見て、postgresql 以外は async def advisory_lock(...): return contextlib.asynccontextmanager(lambda: (yield)) 的なno-opに。呼び元のawait advisory_lock(conn, sym)がawaitableである点に注意。

P0-3: server_default はPG前提なら text("now()") でOK。SQLiteサポートを残したい場合は text("CURRENT_TIMESTAMP") にするなど方言分岐が必要です。



---


---

参考として読んだ箇所（根拠リンク）

create_async_engine(..., future=True) の存在（要削除）。

prices.py のPG専用SQL/get_prices_resolved/advisory_lock 依存。

alembic.ini が SQLite に固定。

依存関係：SQLAlchemy 2.0.29 / aiosqlite を含む。

モデルの server_default=sa.func.now()。

Alembic env.py が同期エンジン＆ini直読み。



---

