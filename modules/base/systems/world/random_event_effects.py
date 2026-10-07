"""Shared read-only queries for time-bounded random-event effects."""

from __future__ import annotations

from collections.abc import Iterable

import polars as pl

from src.shared.numeric import stable_sum


def aggregate_active_effects(
    effects: pl.DataFrame | None,
    now_minute: int,
    *,
    categories: Iterable[str] | None = None,
    subject_type: str | None = None,
) -> dict[tuple[str, str, str], float]:
    """Sum active magnitudes by subject and category using stable reductions."""
    required = {
        "category",
        "subject_type",
        "subject_id",
        "magnitude",
        "starts_at_minute",
        "expires_at_minute",
        "status",
    }
    if effects is None or effects.is_empty() or not required.issubset(effects.columns):
        return {}

    active = effects.filter(
        pl.col("status").is_in(["pending", "active"])
        & (pl.col("starts_at_minute") <= int(now_minute))
        & (pl.col("expires_at_minute") > int(now_minute))
    )
    if categories is not None:
        category_values = tuple(sorted({str(value) for value in categories}))
        if not category_values:
            return {}
        active = active.filter(pl.col("category").is_in(category_values))
    if subject_type is not None:
        active = active.filter(pl.col("subject_type") == str(subject_type))
    if active.is_empty():
        return {}

    grouped = (
        active.with_columns(
            pl.col("magnitude").cast(pl.Float64, strict=False).alias("_magnitude")
        )
        .filter(pl.col("_magnitude").is_finite())
        .group_by(["subject_type", "subject_id", "category"], maintain_order=True)
        .agg(stable_sum("_magnitude").alias("magnitude"))
        .sort(["subject_type", "subject_id", "category"])
    )
    return {
        (
            str(row["subject_type"] or ""),
            str(row["subject_id"] or ""),
            str(row["category"] or ""),
        ): float(row["magnitude"])
        for row in grouped.iter_rows(named=True)
    }
