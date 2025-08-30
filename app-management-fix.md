# app/management クリティカルエラー調査メモ

## 目的
- `app/management`（Typer ベースの管理 CLI とサブコマンド）における致命的エラーの芽を洗い出し、現状の健全性と改善案を整理する。

## 対象
- 参照ファイル:
  - `app/management/cli.py`
  - `app/management/commands/add_symbol.py`
- 関連テスト:
  - `tests/unit/test_cli_entry.py`
  - `tests/unit/test_cli_add_symbol.py`
  - （運用周辺）`tests/unit/test_docker_entrypoint.py`, `tests/unit/test_docker_compose.py`, `tests/unit/test_render_yaml.py`

## 概要結論
- 現状の CLI 実装はユニットテスト観点で致命的エラーは見当たらず、想定どおり動作（サブコマンド列挙、正規化→DB 追加、重複メッセージ）。
- 一方で、運用/例外系で“致命化”し得るポイントがいくつかあるため、再発防止策を提案する（下記）。

## 調査ログ（要点）
- `app/management/cli.py`
  - `Typer()` アプリ定義。
  - サブコマンド: `add-symbol`（from `commands.add_symbol`）、`verify-symbol`（正規化の動作確認）。
  - `main()` は Typer エントリの薄いラッパー。
- `app/management/commands/add_symbol.py`
  - `normalize_symbol()` を通した後に `db_add_symbol()`（スタブ）を呼ぶ。
  - `ValueError` を重複とみなして `"{SYMBOL} already exists"` を出力。成功時は `"added {SYMBOL}"` を出力。
  - テストは `normalize_symbol` と `db_add_symbol` をモックして、メッセージと呼び出しを検証。

## クリティカル化し得るポイントと対処
1) 例外時の終了コード・出力
   - 事象: `db_add_symbol()` が `ValueError` 以外の例外を送出した場合、現状は未捕捉のためスタックトレースで終了（Typer は非 0 終了）。
   - 影響: 運用 CLI としての UX が悪化（ただし、障害検知の観点では有益）。
   - 方針: 想定外例外は標準エラーに短いメッセージを出力し、非 0 で終了させる（`typer.echo(..., err=True); raise typer.Exit(code=1)`）。テストの期待は現状維持のため、変更は任意。

2) Windows 端末の文字コード
   - 事象: `typer.echo` の出力が CP932 端末で文字化けする可能性。
   - 方針: CLI 側は ASCII のみのメッセージに留める（現状 OK）。必要なら `PYTHONIOENCODING=utf-8` を運用ガイドに追記。

3) 正規化ルールとの一貫性
   - 事象: `normalize_symbol()` は `app/services/normalize.py` に依存。仕様変更時は CLI 表示と DB 登録の整合が崩れ得る。
   - 方針: 正規化の振る舞いが変わる場合、CLI の出力文言（例: `added ...`）が誤解を生まないよう、`source` と `normalized` を併記するオプション追加を検討（任意）。

4) DB 実装への差し替え
   - 事象: `db_add_symbol()` はスタブ。実装置換時に DB 例外（一意制約違反等）を捕捉して `ValueError` にラップしないと、重複時のメッセージが崩れる。
   - 方針: 実装時は一意制約違反（例: `sqlalchemy.exc.IntegrityError` で `UNIQUE(new_symbol)` / `PK(symbol)`）を `ValueError` に変換するアダプタを用意。

5) パッケージ配布時のエントリポイント
   - 事象: 現状の `pyproject.toml` に console_scripts の定義なし。配布後、エグゼキュータ名が無いと実行が煩雑。
   - 方針: 配布を想定するなら `console_scripts`（または Poetry の `scripts`）で `app-cli = app.management.cli:main` を定義（任意）。

## 推奨変更（任意・最小差分案）
1) 想定外例外のユーザフレンドリ処理（任意）
```python
# app/management/commands/add_symbol.py（参考）
def add_symbol(symbol: str) -> None:
    norm = normalize.normalize_symbol(symbol)
    try:
        db_add_symbol(norm)
    except ValueError:
        typer.echo(f"{norm} already exists")
    except Exception as exc:  # 運用向け
        typer.echo(f"failed to add {norm}: {exc}", err=True)
        raise typer.Exit(code=1)
    else:
        typer.echo(f"added {norm}")
```

2) 将来の DB 実装時のアダプタ方針
- 一意制約違反を `ValueError` に正規化する関数を `commands/add_symbol.py` 内または `services` に設置し、CLI ロジックは変えない。

## スモーク確認手順（参考）
- ヘルプ: `python -c "from app.management import cli; print(cli.app())"` ではなく、Typer ランナーで `--help` を確認。
- add-symbol: `CliRunner().invoke(cli.app, ["add-symbol", "aapl"])` が `added AAPL` を含むこと（`db_add_symbol` をスタブ/モック）。
- 重複ケース: `db_add_symbol` が `ValueError` を送出したとき `already exists` が出力されること。

## テスト（参考）
- `tests/unit/test_cli_entry.py`（サブコマンド列挙）
- `tests/unit/test_cli_add_symbol.py`（正規化呼び出し・DB 追加・重複出力）

## まとめ
- 現状の `app/management` は単体テスト観点で致命的エラーなし。
- 運用の頑健性向上として、想定外例外の扱い、DB 一意制約違反の正規化、配布時エントリポイント定義の検討を推奨（いずれも最小差分で適用可能）。

