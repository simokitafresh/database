from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, List, Tuple


def _get(row: Any, key: str):
    try:
        return getattr(row, key)
    except AttributeError:
        return row[key]


def segments_for(
    symbol: str,
    date_from: date,
    date_to: date,
    symbol_changes_rows: Iterable[Any],
) -> List[Tuple[str, date, date]]:
    """Return symbol segments accounting for a single ticker change.

    Parameters
    ----------
    symbol: str
        Requested symbol (either old or new).
    date_from: date
        Start date, inclusive.
    date_to: date
        End date, inclusive.
    symbol_changes_rows: iterable
        Rows/dicts having ``old_symbol``, ``new_symbol`` and ``change_date``.

    Returns
    -------
    list of tuples ``(actual_symbol, seg_from, seg_to)`` covering the
    requested range.  ``change_date`` itself belongs to the new symbol while
    the day before remains the old symbol.
    """
    change_row = None
    for row in symbol_changes_rows:
        old = _get(row, "old_symbol")
        new = _get(row, "new_symbol")
        change = _get(row, "change_date")
        if symbol == old or symbol == new:
            change_row = (old, new, change)
            break

    if not change_row:
        return [(symbol, date_from, date_to)]

    old, new, change_date = change_row

    if date_to < change_date:
        return [(old, date_from, date_to)]

    if date_from >= change_date:
        return [(new, date_from, date_to)]

    pre_end = change_date - timedelta(days=1)
    return [(old, date_from, pre_end), (new, change_date, date_to)]
