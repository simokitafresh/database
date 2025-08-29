from typer.testing import CliRunner

from app.management import cli


def test_cli_lists_subcommands():
    runner = CliRunner()
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "add-symbol" in result.stdout
    assert "verify-symbol" in result.stdout
