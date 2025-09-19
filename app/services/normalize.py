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
    
    現在の仕様:
    - BRK.B → BRK-B (クラス株変換)
    - 取引所サフィックス (.TO等) は維持
    
    追加仕様:
    - ^VIX等の指数シンボルはそのまま維持
    """
    if not symbol:
        return ""
    
    s = symbol.strip().upper()
    if not s:
        return ""
    
    # 新規追加: 特殊シンボル（^で始まる指数）はそのまま維持
    if s.startswith("^"):
        return s
    
    # 既存のロジック（ドット処理）
    if "." in s:
        head, tail = s.rsplit(".", 1)
        if tail in _KNOWN_EXCHANGE_SUFFIXES:
            return f"{head}.{tail}"
        if len(tail) == 1 and tail.isalpha():
            return f"{head}-{tail}"
        return s
    
    return s
