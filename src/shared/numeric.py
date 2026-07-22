from __future__ import annotations

import math
from typing import Iterable

import polars as pl


def stable_sum(value: str | pl.Expr) -> pl.Expr:
    """Build a reproducible floating-point group reduction.

    Polars may combine floating-point partitions in scheduler-dependent order.
    ``math.fsum`` computes one high-precision result from the complete group,
    which keeps replays bit-identical without forcing all Polars work to one
    thread.
    """

    expression = pl.col(value) if isinstance(value, str) else value
    return expression.implode().map_elements(
        _sum_series,
        return_dtype=pl.Float64,
    )


def stable_total(values: Iterable[float | int | None]) -> float:
    """Return a reproducible scalar total for simulation state calculations."""

    return math.fsum(float(value) for value in values if value is not None)


def _sum_series(values: pl.Series) -> float:
    return stable_total(values)
