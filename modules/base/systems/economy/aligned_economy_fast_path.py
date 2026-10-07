from __future__ import annotations

from typing import NamedTuple

import numpy as np
import polars as pl

from src.shared.economy_meta import RESOURCE_MAPPING
from src.shared.numeric import stable_nonnegative_row_totals


_RESOURCE_ORDER = tuple(sorted(RESOURCE_MAPPING))
_RESOURCE_LEDGER_METADATA = pl.DataFrame(
    [
        {
            "game_resource_id": resource_id,
            "category": values["category"],
            "unit_str": values["unit"],
        }
        for resource_id, values in RESOURCE_MAPPING.items()
    ]
).sort("game_resource_id")
_NUMERIC_TYPES = frozenset(
    {
        pl.Float32,
        pl.Float64,
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
    }
)


class AlignedEconomyLayoutCache(NamedTuple):
    country_ids: pl.Series
    production_country_ids: pl.Series
    production_resource_ids: pl.Series
    ledger_metadata: pl.DataFrame
    population_ids: pl.Series
    population_row_indices: np.ndarray


class AlignedEconomyTables(NamedTuple):
    countries: pl.DataFrame
    production: pl.DataFrame
    layout_cache: AlignedEconomyLayoutCache


def update_aligned_economy_tables(
    countries: pl.DataFrame,
    production: pl.DataFrame,
    population: pl.DataFrame,
    fraction: float,
    layout_cache: AlignedEconomyLayoutCache | None,
) -> AlignedEconomyTables | None:
    """Update a canonical, effect-free economy using dense country/resource vectors."""
    if (
        "id" not in countries.columns
        or "money_reserves" not in countries.columns
        or not {"country_id", "game_resource_id", "domestic_production"}.issubset(
            production.columns
        )
        or not {"country_id", "population"}.issubset(population.columns)
    ):
        return None

    country_ids = countries.get_column("id")
    production_country_ids = production.get_column("country_id")
    production_resource_ids = production.get_column("game_resource_id")
    population_ids = population.get_column("country_id")
    population_column = population.get_column("population")
    if (
        countries.schema["id"] != pl.String
        or production.schema["country_id"] != pl.String
        or production.schema["game_resource_id"] != pl.String
        or population_ids.dtype != pl.String
        or population_column.dtype not in _NUMERIC_TYPES
        or population_ids.null_count() > 0
    ):
        return None

    cache_hit = (
        layout_cache is not None
        and layout_cache.country_ids.equals(country_ids)
        and layout_cache.production_country_ids.equals(production_country_ids)
        and layout_cache.production_resource_ids.equals(production_resource_ids)
        and layout_cache.population_ids.equals(population_ids)
    )
    if not cache_hit:
        country_values = country_ids.to_list()
        if (
            country_ids.null_count() > 0
            or not country_ids.is_sorted()
            or len(set(country_values)) != countries.height
        ):
            return None
        expected_keys = countries.select(pl.col("id").alias("country_id")).join(
            pl.DataFrame({"game_resource_id": _RESOURCE_ORDER}),
            how="cross",
        )
        if (
            production.height != countries.height * len(_RESOURCE_ORDER)
            or not expected_keys.get_column("country_id").equals(production_country_ids)
            or not expected_keys.get_column("game_resource_id").equals(
                production_resource_ids
            )
        ):
            return None
        ledger_metadata = pl.DataFrame({"country_id": country_ids}).join(
            _RESOURCE_LEDGER_METADATA,
            how="cross",
        )
        if (
            not ledger_metadata.get_column("country_id").equals(
                production_country_ids
            )
            or not ledger_metadata.get_column("game_resource_id").equals(
                production_resource_ids
            )
        ):
            return None
    else:
        ledger_metadata = layout_cache.ledger_metadata

    if cache_hit:
        population_row_indices = layout_cache.population_row_indices
    else:
        population_id_values = population_ids.to_list()
        if len(set(population_id_values)) != len(population_id_values):
            return None
        population_index_by_country = {
            country_id: index
            for index, country_id in enumerate(population_id_values)
        }
        population_row_indices = np.fromiter(
            (population_index_by_country.get(country_id, -1) for country_id in country_values),
            dtype=np.intp,
            count=countries.height,
        )

    # Cache only identifier alignment; population values can change between ticks.
    population_values = (
        population_column.cast(pl.Float64, strict=False)
        .fill_null(0.0)
        .to_numpy()
    )
    aligned_population = np.zeros(countries.height, dtype=np.float64)
    has_population = population_row_indices >= 0
    aligned_population[has_population] = population_values[
        population_row_indices[has_population]
    ]

    def numeric_values(
        frame: pl.DataFrame,
        column: str,
        default: float | None = None,
    ) -> np.ndarray | None:
        if column not in frame.columns:
            return None if default is None else np.full(frame.height, default)
        series = frame.get_column(column)
        if series.dtype not in _NUMERIC_TYPES:
            return None
        if series.null_count():
            if default is None:
                return None
            series = series.fill_null(default)
        return series.cast(pl.Float64, strict=False).to_numpy()

    production_values = numeric_values(production, "domestic_production", 0.0)
    reserves = numeric_values(countries, "money_reserves")
    internal_tax_rates = numeric_values(countries, "internal_tax_rate", 0.20)
    growth_rates = numeric_values(countries, "industrial_growth_rate", 0.025)
    if (
        production_values is None
        or reserves is None
        or internal_tax_rates is None
        or growth_rates is None
    ):
        return None

    resource_count = len(_RESOURCE_ORDER)
    production_matrix = production_values.reshape(countries.height, resource_count)
    country_gdp = stable_nonnegative_row_totals(production_matrix)
    country_production_income = stable_nonnegative_row_totals(
        production_matrix * fraction
    )
    per_capita_gdp = np.divide(
        country_gdp,
        aligned_population,
        out=np.zeros(countries.height, dtype=np.float64),
        where=aligned_population > 0.0,
    )

    country_updates = [
        pl.Series("gdp", country_gdp),
        pl.Series("gdp_per_capita", per_capita_gdp),
        pl.Series(
            "money_reserves",
            reserves + country_production_income * internal_tax_rates,
        ),
    ]
    if "internal_tax_rate" not in countries.columns:
        country_updates.append(
            pl.Series("internal_tax_rate", [0.20] * countries.height)
        )
    if "industrial_growth_rate" not in countries.columns:
        country_updates.append(
            pl.Series("industrial_growth_rate", [0.025] * countries.height)
        )
    if "economic_health" not in countries.columns:
        country_updates.append(pl.Series("economic_health", [1.0] * countries.height))
    updated_countries = countries.with_columns(country_updates)

    production_growth = production_values * (
        1.0 + np.repeat(growth_rates, resource_count) * fraction
    )
    updated_production = production.with_columns(
        pl.Series("domestic_production", production_growth)
    )

    new_cache = layout_cache if cache_hit else AlignedEconomyLayoutCache(
        country_ids,
        production_country_ids,
        production_resource_ids,
        ledger_metadata,
        population_ids,
        population_row_indices,
    )
    return AlignedEconomyTables(updated_countries, updated_production, new_cache)
