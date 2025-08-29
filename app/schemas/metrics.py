from __future__ import annotations

from pydantic import BaseModel


class MetricsOut(BaseModel):
    """Output schema for computed metrics."""

    symbol: str
    cagr: float
    stdev: float
    max_drawdown: float
    n_days: int


__all__ = ["MetricsOut"]
