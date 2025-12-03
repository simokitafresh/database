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
    has_full_history = sa.Column(sa.Boolean, nullable=False, server_default=sa.false())
    first_date = sa.Column(sa.Date, nullable=True)
    last_date = sa.Column(sa.Date, nullable=True)
    created_at = sa.Column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


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


class EconomicIndicator(Base):
    """Economic indicators data (e.g. FRED data)."""

    __tablename__ = "economic_indicators"
    __table_args__ = (
        sa.PrimaryKeyConstraint("symbol", "date"),
    )

    symbol = sa.Column(sa.String, nullable=False)
    date = sa.Column(sa.Date, nullable=False)
    value = sa.Column(sa.Float, nullable=True)
    last_updated = sa.Column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class CorporateEvent(Base):
    """Corporate actions and price adjustment events."""

    __tablename__ = "corporate_events"
    __table_args__ = (
        sa.UniqueConstraint("symbol", "event_date", "event_type", name="uq_corp_event"),
        sa.ForeignKeyConstraint(
            ["symbol"], ["symbols.symbol"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "event_type IN ('stock_split', 'reverse_split', 'dividend', 'special_dividend', 'capital_gain', 'spinoff', 'unknown')",
            name="ck_corp_event_type",
        ),
        sa.CheckConstraint(
            "status IN ('detected', 'confirmed', 'fixing', 'fixed', 'ignored', 'failed')",
            name="ck_corp_event_status",
        ),
        sa.CheckConstraint(
            "severity IN ('critical', 'high', 'normal', 'low')",
            name="ck_corp_event_severity",
        ),
        Index("idx_corp_events_symbol", "symbol"),
        Index("idx_corp_events_date", sa.text("event_date DESC")),
        Index("idx_corp_events_type", "event_type"),
        Index("idx_corp_events_status", "status", postgresql_where=sa.text("status != 'fixed'")),
        Index("idx_corp_events_detected", sa.text("detected_at DESC")),
    )

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    
    # Event Identification
    symbol = sa.Column(sa.String(20), nullable=False)
    event_date = sa.Column(sa.Date, nullable=False)
    event_type = sa.Column(sa.String(30), nullable=False)
    
    # Event Details
    ratio = sa.Column(sa.Numeric(10, 6), nullable=True)
    amount = sa.Column(sa.Numeric(12, 4), nullable=True)
    currency = sa.Column(sa.String(3), nullable=True, default='USD')
    ex_date = sa.Column(sa.Date, nullable=True)
    
    # Detection Info
    detected_at = sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    detection_method = sa.Column(sa.String(20), nullable=True, default='auto')
    db_price_at_detection = sa.Column(sa.Numeric(12, 4), nullable=True)
    yf_price_at_detection = sa.Column(sa.Numeric(12, 4), nullable=True)
    pct_difference = sa.Column(sa.Numeric(8, 6), nullable=True)
    severity = sa.Column(sa.String(10), nullable=True)
    
    # Fix Info
    status = sa.Column(sa.String(20), nullable=True, default='detected')
    fixed_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    fix_job_id = sa.Column(sa.String(50), nullable=True)
    rows_deleted = sa.Column(sa.Integer, nullable=True)
    rows_refetched = sa.Column(sa.Integer, nullable=True)
    
    # Metadata
    source_data = sa.Column(postgresql.JSONB, nullable=True)
    notes = sa.Column(sa.Text, nullable=True)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())
