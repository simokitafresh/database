from __future__ import annotations

"""Database models for core tables."""

import sqlalchemy as sa
from sqlalchemy import Index

from .base import Base


class Symbol(Base):
    """Tradable symbols metadata."""

    __tablename__ = "symbols"

    symbol = sa.Column(sa.String, primary_key=True)
    name = sa.Column(sa.String, nullable=True)
    exchange = sa.Column(sa.String, nullable=True)
    currency = sa.Column(sa.String(3), nullable=True)
    is_active = sa.Column(sa.Boolean, nullable=True)
    first_date = sa.Column(sa.Date, nullable=True)
    last_date = sa.Column(sa.Date, nullable=True)


class SymbolChange(Base):
    """Mapping of symbol changes (one hop)."""

    __tablename__ = "symbol_changes"
    __table_args__ = (
        sa.PrimaryKeyConstraint("old_symbol", "change_date"),
        sa.UniqueConstraint("new_symbol"),
        Index("idx_symbol_changes_old", "old_symbol"),
        Index("idx_symbol_changes_new", "new_symbol"),
    )

    old_symbol = sa.Column(sa.String, nullable=False)
    new_symbol = sa.Column(sa.String, nullable=False)
    change_date = sa.Column(sa.Date, nullable=False)
    reason = sa.Column(sa.String, nullable=True)


class Price(Base):
    """Daily adjusted OHLCV prices."""

    __tablename__ = "prices"
    __table_args__ = (
        sa.PrimaryKeyConstraint("symbol", "date"),
        sa.ForeignKeyConstraint(
            ["symbol"], ["symbols.symbol"], onupdate="CASCADE", ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "high >= low AND high >= open AND high >= close AND low <= open AND low <= close",
            name="ck_prices_high_low_range",
        ),
        sa.CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0",
            name="ck_prices_positive",
        ),
    )

    symbol = sa.Column(sa.String, nullable=False)
    date = sa.Column(sa.Date, nullable=False)
    open = sa.Column(sa.Float, nullable=False)
    high = sa.Column(sa.Float, nullable=False)
    low = sa.Column(sa.Float, nullable=False)
    close = sa.Column(sa.Float, nullable=False)
    volume = sa.Column(sa.BigInteger, nullable=False)
    source = sa.Column(sa.String, nullable=False)
    last_updated = sa.Column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
