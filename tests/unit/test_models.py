from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db import models


def compile_ddl(table: sa.Table) -> str:
    return str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_prices_table_ddl_contains_constraints():
    ddl = compile_ddl(models.Price.__table__)
    assert "PRIMARY KEY (symbol, date)" in ddl
    assert "FOREIGN KEY" in ddl and "REFERENCES symbols (symbol)" in ddl
    assert "ON UPDATE CASCADE" in ddl and "ON DELETE RESTRICT" in ddl
    assert "CHECK (low <= LEAST(open, close))" in ddl
    assert "CHECK (GREATEST(open, close) <= high)" in ddl
    assert "CHECK (open > 0 AND high > 0 AND low > 0 AND close > 0)" in ddl
    assert "CHECK (volume >= 0)" in ddl
    assert isinstance(models.Price.__table__.c.volume.type, sa.BigInteger)
    assert models.Price.__table__.c.last_updated.type.timezone is True


def test_symbol_changes_constraints():
    ddl = compile_ddl(models.SymbolChange.__table__)
    assert "UNIQUE (new_symbol)" in ddl
    assert "PRIMARY KEY (old_symbol, change_date)" in ddl
