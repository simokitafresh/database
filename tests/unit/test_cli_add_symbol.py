from typer.testing import CliRunner

from app.management import cli


def test_add_symbol_calls_normalize_and_inserts(mocker):
    runner = CliRunner()
    norm = mocker.patch(
        "app.management.commands.add_symbol.normalize.normalize_symbol", return_value="AAA"
    )
    db = mocker.patch("app.management.commands.add_symbol.db_add_symbol")

    result = runner.invoke(cli.app, ["add-symbol", "aaa"])
    assert result.exit_code == 0
    norm.assert_called_once_with("aaa")
    db.assert_called_once_with("AAA")
    assert "added AAA" in result.stdout


def test_add_symbol_duplicate(mocker):
    runner = CliRunner()
    mocker.patch(
        "app.management.commands.add_symbol.normalize.normalize_symbol", return_value="AAA"
    )
    mocker.patch(
        "app.management.commands.add_symbol.db_add_symbol", side_effect=ValueError
    )

    result = runner.invoke(cli.app, ["add-symbol", "AAA"])
    assert result.exit_code == 0
    assert "AAA already exists" in result.stdout
