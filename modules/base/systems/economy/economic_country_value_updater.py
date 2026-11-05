from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import polars as pl


@dataclass(frozen=True)
class SetCountryValue:
    value: Any


@dataclass(frozen=True)
class AddCountryValue:
    amount: float


CountryValueChange = SetCountryValue | AddCountryValue


class EconomicCountryValueUpdater(Protocol):
    def apply(
        self,
        frame: pl.DataFrame,
        country_id: str,
        changes: Mapping[str, CountryValueChange],
    ) -> pl.DataFrame | None: ...


class DeterministicEconomicCountryValueUpdater:
    """Build a country-row update without reading or writing simulation state."""

    def apply(
        self,
        frame: pl.DataFrame,
        country_id: str,
        changes: Mapping[str, CountryValueChange],
    ) -> pl.DataFrame | None:
        target = pl.col("id") == str(country_id)
        expressions: list[pl.Expr] = []
        for column, change in changes.items():
            if column not in frame.columns:
                continue
            if isinstance(change, AddCountryValue):
                expression = pl.col(column).fill_null(0.0) + float(change.amount)
            else:
                expression = pl.lit(change.value, dtype=frame.schema[column])
            expressions.append(
                pl.when(target)
                .then(expression)
                .otherwise(pl.col(column))
                .alias(column)
            )

        return frame.with_columns(expressions) if expressions else None
