了解しました。指定のリポジトリの app/management 配下を実際に読み込み、静的に点検しました。その結果に基づく「クリティカル／重大寄りの不具合・リスク」と、Codex（コーディング担当）に渡せる極小・検証可能なタスク一覧を用意しました。


---

何を読んだか（根拠）

app/management/cli.py：Typer で add-symbol / verify-symbol を登録。add-symbol は app.management.commands.add_symbol.add_symbol を呼出し、verify-symbol は正規化だけして出力するプレースホルダ。

app/management/commands/add_symbol.py：

db_add_symbol(symbol: str) が DB挿入のスタブ（実装なし）。

add_symbol() は normalize.normalize_symbol() で正規化後、db_add_symbol() を呼び、ValueError を重複として扱う。スタブは例外を投げないため 常に「added …」と成功表示になる。


正規化ロジック app/services/normalize.py とそのユニットテスト（tests/unit/test_normalize.py）は存在し、例：brk.b → BRK-B, 7203.t → 7203.T, 多段ドット保持などが想定どおり。

依存関係に typer==0.16.1 が明示（CLI動作要件は満たす）。

アーキテクチャ設計書では app/management/ に Typer CLI（cli.py）と commands/ 配下の複数コマンドが計画されている。



---

見つかったクリティカル／重大寄りの不具合・リスク

1. スタブにより“成功表示だが無処理”になる動作
db_add_symbol() が実装なし（docstringのみ）→ 例外が出ず、add_symbol() の else: で 必ず「added …」が出力。実際にはDB挿入されず、誤ったオペレーション結果を示す。運用事故リスクが高い。


2. 空入力／正規化後に空文字の取り扱いなし
normalize_symbol(None/""/空白) は "" を返す設計。CLI 側でガードが無いので、空シンボルがDB挿入処理に渡る可能性（現在はスタブゆえ挿入もされず成功表示）。入力バリデーションが必要。


3. commands パッケージの import 堅牢性
from app.management.commands import add_symbol as add_symbol_cmd という形での import。PEP420（namespace package）により __init__.py が無くても動く環境が多い一方、ツールや一部パッケージング環境で解決に失敗することがあるため、app/management/commands/__init__.py を明示配置しておくのが安全。※現行リポジトリに当該ファイルの有無は確認が取り切れなかったため、確実化タスクとして明示作成を推奨。


4. verify-symbol がプレースホルダのまま
現状は正規化のみ実施し "verify …" をエコーするだけ。運用上の検証要件（取得可否・メタ情報確認等）を満たさないため、少なくとも「無効入力のエラー化」「終了コードの明確化」は最低限必要。




---

再現チェック（ローカルでの期待挙動）

> これはコードから論理的に導ける挙動です。実行例は Codex がタスク完了後に自動化テストへ落とし込み可能です。



python -m app.management.cli add-symbol "brk.b"
期待：現在のコードだと 「added BRK-B」 と表示（DB未実装でも成功扱いになってしまう）。

python -m app.management.cli add-symbol "   "
期待：現状は "   " → "" に正規化されるが、エラーにならず成功表示の可能性（要改善）。



---

エラー修正タスクリスト（超小粒・検証可能・単一関心）

> 進捗欄は「未着手 / WIP / Done」などを想定。DoD = Definition of Done（完了判定）。



A. セーフティガードと正しい終了コード

[ ] A-1 | 空入力の即時エラー化
対象: app/management/commands/add_symbol.py
変更: add_symbol() 冒頭で norm == "" を検知し、typer.BadParameter("symbol is empty after normalization") を送出。
テスト: CliRunner().invoke(app, ["add-symbol", "   "]) が exit_code != 0 かつエラーメッセージに empty を含む。
DoD: テスト緑化。

[ ] A-2 | verify-symbol も空入力をエラー化
対象: app/management/cli.py（verify_symbol）
変更: 正規化後 "" なら typer.BadParameter。
テスト: CliRunner().invoke(app, ["verify-symbol", " "]) が非0終了。
DoD: テスト緑化。 

[ ] A-3 | CLI の未実装処理を“明確な失敗”に
対象: app/management/commands/add_symbol.py
変更: スタブの db_add_symbol() を raise NotImplementedError("db_add_symbol is not implemented") に変更。
テスト: CliRunner で add-symbol AAPL 実行時、exit_code != 0 かつ NotImplemented の文言が表示。
DoD: テスト緑化。 

[ ] A-4 | NotImplemented を CLI でユーザーフレンドリに変換
対象: app/management/commands/add_symbol.py
変更: add_symbol() 内で NotImplementedError を捕捉し、typer.secho("DB not configured", err=True)＋raise typer.Exit(2)。
テスト: exit_code == 2・エラーメッセージ表示。
DoD: テスト緑化。


B. import の堅牢化

[ ] B-1 | commands を明示パッケージ化
対象: app/management/commands/__init__.py を新規作成（空で可、__all__ = ["add_symbol"] を置いても良い）。
テスト: python -c "from app.management.commands import add_symbol" が 0 終了。
DoD: CI（lint+test）通過。


C. 重複検知の定義を固定（スタブでもテスト可能に）

[ ] C-1 | 重複を表す例外型の専用化
対象: app/management/commands/add_symbol.py
変更: class SymbolAlreadyExists(ValueError): pass を定義し、重複時はこれを投げる契約にする（DB実装後も共通）。
テスト: monkeypatch で db_add_symbol を raise SymbolAlreadyExists に差替え、CLI出力が "already exists" / exit_code == 0（要件に合わせ 0/非0 は選択）を確認。
DoD: テスト緑化。 

[ ] C-2 | メッセージの一貫性
対象: 同上
変更: "added {norm}" / "{norm} already exists" を固定し、テストで文言一致を検証。
テスト: CliRunner で期待メッセージ一致。
DoD: テスト緑化。 


D. 最低限の CLI ユーザビリティ

[ ] D-1 | Typer(no_args_is_help=True)
対象: app/management/cli.py
変更: app = typer.Typer(no_args_is_help=True)。
テスト: CliRunner().invoke(app, []) でヘルプが表示。
DoD: テスト緑化。 

[ ] D-2 | verify-symbol の終了コード定義
対象: app/management/cli.py
変更: 正常時 0、異常時（空・無効フォーマット） 2 を返すよう typer.Exit を使用。
テスト: 正常／異常ケースの終了コード。
DoD: テスト緑化。


E. テスト追加（ネットワーク・DB不要）

[ ] E-1 | tests/unit/test_add_symbol_cli.py 新規
内容:

正規化（brk.b → BRK-B）が CLI 経由でも反映されるか。

空入力で BadParameter になるか。

db_add_symbol をモンキーパッチして（成功／重複／未実装）各メッセージと終了コードを検証。
DoD: 新規テストが緑。


[ ] E-2 | tests/unit/test_verify_symbol_cli.py 新規
内容: 正常入力の整形表示、空入力時のエラー、終了コード。
DoD: 緑化。

[ ] E-3 | tests/unit/test_commands_import.py 新規
内容: from app.management.commands import add_symbol が import 可能であること。
DoD: 緑化。


F. 将来タスク（DB 実装と接続／今回は雛形まで）

[ ] F-1 | db_add_symbol の最小実装（SQLAlchemy または asyncpg）
対象: app/management/commands/add_symbol.py
内容: DATABASE_URL を読み、INSERT INTO symbols … を実行。UNIQUE 違反時は SymbolAlreadyExists に変換。ユニットテストは DB を モック し、結合テストでのみ実 DB を使用（既存ポリシー準拠）。
DoD: ユニットはモックで緑、結合は docker-compose の PostgreSQL で緑。
（設計書・依存関係は既に整備済み：FastAPI/SQLAlchemy/asyncpg 等）



---

補足メモ

依存関係は満たされています：typer==0.16.1 が requirements.txt に固定されています。CLI の起動自体は可能です。

正規化の前提はユニットで担保済み：normalize_symbol() の仕様（1文字サフィックス→ハイフン、取引所サフィックスはドットのまま、多段ドット保持）はテストで確認できます。CLI 側でもこの仕様を前提に小さな E2E 相当のユニットを積み増すだけで十分です。

commands の __init__.py：環境依存の import 不安定さを避ける 予防保全 です（作成は 0 バイトで可）。



---

タスク一覧（貼り付け用・進捗記入可）

ID	タスク	ファイル	進捗	検証方法（DoD）

A-1	正規化後に空なら BadParameter を送出	app/management/commands/add_symbol.py	[ ]	CliRunner add-symbol "   " が非0
A-2	verify-symbol も空を BadParameter	app/management/cli.py	[ ]	CliRunner verify-symbol " " 非0
A-3	db_add_symbol() を NotImplementedError に（現状の誤成功を防止）	app/management/commands/add_symbol.py	[ ]	CliRunner add-symbol AAPL 非0＆文言
A-4	NotImplementedError を捕捉し Exit(2)	app/management/commands/add_symbol.py	[ ]	終了コード 2
B-1	app/management/commands/__init__.py を作成	app/management/commands/__init__.py	[ ]	python -c "from app.management.commands import add_symbol" 0終了
C-1	SymbolAlreadyExists 例外型の導入	app/management/commands/add_symbol.py	[ ]	モンキーパッチで重複時のメッセージ・終了コード検証
C-2	出力文言の固定（added / already exists）	同上	[ ]	文字列一致テスト
D-1	Typer(no_args_is_help=True)	app/management/cli.py	[ ]	引数なしでヘルプ表示
D-2	verify-symbol の終了コード定義	app/management/cli.py	[ ]	正常0／異常2を確認
E-1	tests/unit/test_add_symbol_cli.py 追加	tests/unit/test_add_symbol_cli.py	[ ]	新規テスト緑
E-2	tests/unit/test_verify_symbol_cli.py 追加	tests/unit/test_verify_symbol_cli.py	[ ]	新規テスト緑
E-3	tests/unit/test_commands_import.py 追加	tests/unit/test_commands_import.py	[ ]	新規テスト緑
F-1	db_add_symbol の最小DB実装（UNIQUE→SymbolAlreadyExists に変換）	app/management/commands/add_symbol.py	[ ]	ユニット（モック）緑＋結合テスト緑



---

必要なら、このタスクリストをそのまま Codex に渡してください。
修正後は以下の簡易回帰で確認できます：

pytest -q tests/unit/test_normalize.py::test_normalize_stock_class_to_hyphen（既存）と新規 CLI テスト群の緑化。

python -m app.management.cli --help（引数なしでヘルプ）。

python -m app.management.cli add-symbol "brk.b"（DB未実装なら Exit(2) で明示的エラー、実装後は成功メッセージ）。



---

