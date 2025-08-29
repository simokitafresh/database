"""Symbol normalization utilities."""

from __future__ import annotations


def normalize_symbol(symbol: str) -> str:
    """Normalize ticker symbols to Yahoo Finance style.

    - Uppercase the symbol.
    - Convert share-class separator from "." to "-" when the prefix is alphabetic.
    - Preserve exchange suffixes (e.g., ".T").
    """
    normalized = symbol.strip().upper()
    if "." in normalized:
        prefix, suffix = normalized.split(".", 1)
        if prefix.isalpha():
            normalized = f"{prefix}-{suffix}"
    return normalized
