"""Database models for core tables."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Index
from sqlalchemy.dialects import postgresql

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
            "low <= LEAST(open, close)",
            name="ck_prices_low_le_open_close",
        ),
        sa.CheckConstraint(
            "GREATEST(open, close) <= high",
            name="ck_prices_open_close_le_high",
        ),
        sa.CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0",
            name="ck_prices_positive_ohlc",
        ),
        sa.CheckConstraint("volume >= 0", name="ck_prices_volume_nonneg"),
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


class FetchJob(Base):
    """Background data fetch job tracking."""

    __tablename__ = "fetch_jobs"

    job_id = sa.Column(sa.String(50), primary_key=True)
    status = sa.Column(sa.String(20), nullable=False)
    symbols = sa.Column(postgresql.ARRAY(sa.String), nullable=False)
    date_from = sa.Column(sa.Date, nullable=False)
    date_to = sa.Column(sa.Date, nullable=False)
    interval = sa.Column(sa.String(10), nullable=False, default='1d')
    force_refresh = sa.Column(sa.Boolean, nullable=False, default=False)
    priority = sa.Column(sa.String(10), nullable=False, default='normal')
    progress = sa.Column(sa.JSON, nullable=True)
    results = sa.Column(sa.JSON, nullable=True)
    errors = sa.Column(sa.JSON, nullable=True)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    started_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    completed_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    created_by = sa.Column(sa.String(100), nullable=True)
