from __future__ import annotations

import math
from typing import Iterable, Mapping

import numpy as np
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


def stable_group_sum(
    frame: pl.DataFrame,
    group_columns: list[str] | tuple[str, ...],
    value_column: str,
    output_column: str,
) -> pl.DataFrame:
    """Sum one column per group with reproducible floating-point arithmetic."""
    return stable_group_sums(
        frame,
        group_columns,
        {value_column: output_column},
    )


def stable_group_sums(
    frame: pl.DataFrame,
    group_columns: list[str] | tuple[str, ...],
    value_columns: Mapping[str, str],
) -> pl.DataFrame:
    """Sum several columns per key while batching Python's exact reductions.

    Polars performs the grouping and list materialization; ``math.fsum`` then
    reduces each compact group in Python. This avoids a Python UDF invocation
    from inside Polars for every group and keeps deterministic monetary totals.
    """
    columns = tuple(group_columns)
    schema = {
        **{column: frame.schema[column] for column in columns},
        **{output: pl.Float64 for output in value_columns.values()},
    }
    if frame.is_empty():
        return pl.DataFrame(schema=schema)

    has_duplicates = frame.select(
        pl.struct(columns).is_duplicated().any()
    ).item()
    if not has_duplicates:
        return frame.select(
            *columns,
            *(
                pl.col(source)
                .cast(pl.Float64, strict=False)
                .alias(output)
                for source, output in value_columns.items()
            ),
        )

    pairs = tuple(value_columns.items())
    temporary_columns = tuple(
        f"__stable_sum_values_{index}" for index in range(len(pairs))
    )
    grouped = frame.group_by(list(columns)).agg(
        *(
            pl.col(source)
            .cast(pl.Float64, strict=False)
            .alias(temporary_column)
            for (source, _), temporary_column in zip(
                pairs, temporary_columns, strict=True
            )
        )
    )
    result_columns = {column: [] for column in schema}
    group_indices = tuple(grouped.columns.index(column) for column in columns)
    value_indices = tuple(
        grouped.columns.index(column) for column in temporary_columns
    )
    # Positional rows avoid allocating one dictionary for every hot-path group.
    for group in grouped.iter_rows(named=False):
        for column, index in zip(columns, group_indices, strict=True):
            result_columns[column].append(group[index])
        for (_, output), index in zip(pairs, value_indices, strict=True):
            values = group[index]
            if len(values) == 1:
                value = values[0]
                # A one-value sum is exact already; avoid materializing an fsum iterator.
                total = 0.0 if value is None else value
            else:
                total = math.fsum(values) if None not in values else stable_total(values)
            result_columns[output].append(total)
    return pl.DataFrame(result_columns, schema=schema, strict=False)


def stable_total(values: Iterable[float | int | None]) -> float:
    """Return a reproducible scalar total for simulation state calculations."""

    return math.fsum(float(value) for value in values if value is not None)


def stable_nonnegative_row_totals(values: np.ndarray) -> np.ndarray:
    """Reduce dense nonnegative rows deterministically, retaining fsum for edge cases."""
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError("Expected a two-dimensional matrix of row values.")
    if np.isfinite(matrix).all() and not (matrix < 0.0).any():
        # A fixed NumPy reduction is deterministic here and avoids Python work per cell.
        return matrix.sum(axis=1, dtype=np.float64)
    return np.fromiter(
        (stable_total(row) for row in matrix),
        dtype=np.float64,
        count=matrix.shape[0],
    )


def _sum_series(values: pl.Series) -> float:
    return stable_total(values)
