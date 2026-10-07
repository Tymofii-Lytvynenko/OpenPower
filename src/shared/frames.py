from __future__ import annotations

from collections.abc import Sequence

import polars as pl


def ensure_sorted(frame: pl.DataFrame, columns: Sequence[str]) -> pl.DataFrame:
    """Return canonical key order without repeating a sort already guaranteed upstream."""

    keys = tuple(columns)
    order_key = frame.select(pl.struct(keys)).to_series()
    return frame if order_key.is_sorted() else frame.sort(keys)
