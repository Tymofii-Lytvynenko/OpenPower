from __future__ import annotations

from collections.abc import Iterable

import polars as pl


def validate_numeric_columns(
    frame: pl.DataFrame,
    table_name: str,
    columns: Iterable[str],
    *,
    nonnegative: Iterable[str] = (),
) -> None:
    """Reject malformed or non-finite economy values before they poison reductions."""
    if frame.is_empty():
        return

    nonnegative_columns = frozenset(nonnegative)
    checks: list[pl.Expr] = []
    checked_columns: list[str] = []
    for column in columns:
        if column not in frame.columns:
            continue
        checked_columns.append(column)
        value = pl.col(column).cast(pl.Float64, strict=False)
        checks.extend(
            (
                (pl.col(column).is_not_null() & value.is_null()).any().alias(f"{column}__invalid"),
                (value.is_not_null() & ~value.is_finite()).any().alias(f"{column}__nonfinite"),
            )
        )
        if column in nonnegative_columns:
            checks.append((value < 0.0).fill_null(False).any().alias(f"{column}__negative"))

    if not checks:
        return

    failures = frame.select(checks).row(0, named=True)
    invalid_columns = [
        column
        for column in checked_columns
        if failures.get(f"{column}__invalid")
        or failures.get(f"{column}__nonfinite")
        or failures.get(f"{column}__negative")
    ]
    if invalid_columns:
        raise ValueError(
            f"{table_name} columns must contain finite numeric values"
            f"{(' and non-negative values' if nonnegative_columns.intersection(invalid_columns) else '')}: "
            f"{', '.join(invalid_columns)}."
        )
