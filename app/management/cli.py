from __future__ import annotations

import typer

from app.management.commands import add_symbol as add_symbol_cmd
from app.services import normalize

app = typer.Typer()


app.command("add-symbol")(add_symbol_cmd.add_symbol)


@app.command("verify-symbol")
def verify_symbol(symbol: str) -> None:
    """Placeholder command to verify a symbol."""
    norm = normalize.normalize_symbol(symbol)
    typer.echo(f"verify {norm}")


def main() -> None:  # pragma: no cover - entrypoint wrapper
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
