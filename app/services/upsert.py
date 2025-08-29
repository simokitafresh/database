from __future__ import annotations

from typing import List, Tuple

import pandas as pd


def df_to_rows(df: pd.DataFrame, *, symbol: str, source: str) -> List[Tuple]:
    """Convert a price DataFrame into rows for bulk upsert.

    Rows containing NaN values are skipped. Dates are converted to ``date`` and
    numeric fields are cast to appropriate Python types for insertion.
    """

    rows: List[Tuple] = []
    for date, row in df.iterrows():
        if row.isna().any():
            continue
        rows.append(
            (
                symbol,
                date.date(),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                int(row["volume"]),
                source,
            )
        )
    return rows


def upsert_prices_sql() -> str:
    """Return SQL statement for upserting price rows."""

    return (
        "INSERT INTO prices (symbol, date, open, high, low, close, volume, source) "
        "VALUES (:symbol, :date, :open, :high, :low, :close, :volume, :source) "
        "ON CONFLICT (symbol, date) DO UPDATE SET "
        "open = EXCLUDED.open, "
        "high = EXCLUDED.high, "
        "low = EXCLUDED.low, "
        "close = EXCLUDED.close, "
        "volume = EXCLUDED.volume, "
        "source = EXCLUDED.source, "
        "last_updated = now();"
    )


__all__ = ["df_to_rows", "upsert_prices_sql"]
