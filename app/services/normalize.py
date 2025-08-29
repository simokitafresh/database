"""Symbol normalization utilities."""

from __future__ import annotations

from typing import Optional, Set

_KNOWN_EXCHANGE_SUFFIXES: Set[str] = {
    # Common Yahoo Finance exchange suffixes (uppercase)
    # 1-letter codes
    "T",  # Tokyo
    "L",  # London
    "V",  # TSXV
    "F",  # Frankfurt
    # 2+ letters
    "TO",
    "AX",
    "DE",
    "HK",
    "SW",
    "MI",
    "PA",
    "SA",
    "SZ",
    "SS",
    "TW",
    "TWO",
    "BK",
    "KS",
    "KQ",
    "OL",
    "HE",
    "ST",
    "VI",
    "CO",
    "AS",
    "BR",
    "LS",
    "IS",
    "MX",
    "SI",
    "JK",
    "NZ",
    "JO",
    "MU",
    "BE",
}


def normalize_symbol(symbol: Optional[str]) -> str:
    """Normalize ticker symbols to Yahoo Finance style.

    Rules
    -----
    * Strip surrounding whitespace and uppercase the symbol.
    * If the symbol contains a suffix (``."``):
        - If the suffix is a known exchange code, preserve the ``."``.
        - Else if the suffix is a single alphabetic character, treat it as a
          share class and replace the ``."`` with ``-``.
        - Otherwise, keep the symbol unchanged (e.g., preferred shares with
          multiple dots).
    * If ``symbol`` is ``None`` or empty, return an empty string.
    """

    if not symbol:
        return ""

    s = symbol.strip().upper()
    if not s:
        return ""

    if "." in s:
        head, tail = s.rsplit(".", 1)
        if tail in _KNOWN_EXCHANGE_SUFFIXES:
            return f"{head}.{tail}"
        if len(tail) == 1 and tail.isalpha():
            return f"{head}-{tail}"
        return s

    return s
