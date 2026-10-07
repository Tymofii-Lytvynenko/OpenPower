from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any, NamedTuple

import numpy as np
import polars as pl

from src.shared.numeric import stable_total


_INITIAL_COLUMNS = frozenset(
    {
        "country_id",
        "population",
        "poverty_rate",
        "human_dev",
        "gdp_per_capita",
        "real_income_index",
        "economic_trade_modifier",
        "total_gdp",
        "wealth_index",
        "solvent_population",
        "total_consumption_pool",
    }
)
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


class _ConsumptionLayout(NamedTuple):
    country_ids: pl.Series
    population_ids: pl.Series
    resource_order: tuple[str, ...]
    selected_ids: tuple[str, ...]
    country_row_indices: np.ndarray
    population_row_indices: np.ndarray
    sorted_resource_indices: np.ndarray
    key_grid: pl.DataFrame


class ConsumptionLayoutCache:
    """Cache immutable identifier alignment while reading current numeric values."""

    def __init__(self) -> None:
        self.layout: _ConsumptionLayout | None = None


def calculate_formulaic_consumption(
    countries: pl.DataFrame,
    population: pl.DataFrame,
    formulas: Mapping[str, Mapping[str, Any]],
    resource_order: Sequence[str],
    layout_cache: ConsumptionLayoutCache | None = None,
) -> pl.DataFrame | None:
    """Build the standard demand matrix from compact country vectors.

    Irregular identifiers or schemas return ``None`` so the authoritative
    Polars implementation can retain its broader compatibility behavior.
    """
    if "id" not in countries.columns or not {"country_id", "population"}.issubset(population.columns):
        return None

    country_ids = countries.get_column("id")
    population_ids = population.get_column("country_id")
    ordered_resources = tuple(resource_order)
    if country_ids.dtype != pl.String or population_ids.dtype != pl.String:
        return None

    cache = layout_cache if layout_cache is not None else ConsumptionLayoutCache()
    layout = cache.layout
    if not (
        layout is not None
        and layout.resource_order == ordered_resources
        and layout.country_ids.equals(country_ids)
        and layout.population_ids.equals(population_ids)
    ):
        layout = _build_layout(country_ids, population_ids, ordered_resources)
        if layout is None:
            return None
        cache.layout = layout

    population_column = population.get_column("population")
    numeric_population = population_column.cast(pl.Float64, strict=False)
    if (
        population_column.dtype not in _NUMERIC_TYPES
        and (population_column.is_not_null() & numeric_population.is_null()).any()
    ):
        return None
    population_values_all = numeric_population.fill_null(0.0).to_numpy()
    if not np.isfinite(population_values_all).all() or (population_values_all < 0.0).any():
        return None
    population_values = population_values_all[layout.population_row_indices]

    def metric(
        column: str,
        default: float,
        *,
        nonnegative: bool = False,
    ) -> np.ndarray | None:
        if column not in countries.columns:
            return np.full(len(layout.selected_ids), default, dtype=np.float64)
        source = countries.get_column(column)
        values = source.cast(pl.Float64, strict=False)
        if (
            source.dtype not in _NUMERIC_TYPES
            and (source.is_not_null() & values.is_null()).any()
        ):
            return None
        array = values.fill_null(default).to_numpy()
        if not np.isfinite(array).all() or (nonnegative and (array < 0.0).any()):
            return None
        return array[layout.country_row_indices]

    poverty = metric("poverty_rate", 0.0)
    if poverty is None:
        return None
    human_development = metric("human_dev", 0.5)
    if human_development is None:
        return None
    gdp_per_capita = metric("gdp_per_capita", 1000.0, nonnegative=True)
    if gdp_per_capita is None:
        return None
    real_income = metric("real_income_index", 1.0)
    if real_income is None:
        return None
    trade_modifier = metric("economic_trade_modifier", 1.0)
    if trade_modifier is None:
        return None
    real_income = np.clip(real_income, 0.0, 2.0)
    trade_modifier = np.clip(trade_modifier, 0.5, 1.0)
    if "gdp" in countries.columns:
        source_gdp = countries.get_column("gdp")
        gdp_series = source_gdp.cast(pl.Float64, strict=False)
        if (
            source_gdp.dtype not in _NUMERIC_TYPES
            and (source_gdp.is_not_null() & gdp_series.is_null()).any()
        ):
            return None
        gdp_null_mask = gdp_series.is_null().to_numpy()
        raw_gdp_values = gdp_series.to_numpy()
        known_gdp = raw_gdp_values[~gdp_null_mask]
        if not np.isfinite(known_gdp).all() or (known_gdp < 0.0).any():
            return None
        if gdp_null_mask.any():
            raw_gdp = (
                gdp_series.fill_null(float("nan"))
                .to_numpy()[layout.country_row_indices]
            )
            total_gdp = np.where(
                np.isnan(raw_gdp),
                gdp_per_capita * population_values,
                raw_gdp,
            )
        else:
            raw_gdp = (
                gdp_series.fill_null(0.0)
                .to_numpy()[layout.country_row_indices]
            )
            total_gdp = raw_gdp
    else:
        total_gdp = gdp_per_capita * population_values

    if not layout.selected_ids:
        return pl.DataFrame(
            schema={
                "country_id": pl.Utf8,
                "game_resource_id": pl.Utf8,
                "consumption_usd": pl.Float64,
            }
        )

    global_average_gdp_per_capita = max(
        stable_total(total_gdp) / max(float(population_values.sum()), 1.0),
        100.0,
    )
    wealth_index = np.clip(
        gdp_per_capita / global_average_gdp_per_capita,
        0.05,
        10.0,
    )
    solvent_population = population_values * (1.0 - poverty) * human_development
    consumption_pool = (
        total_gdp
        * (0.50 + 0.40 / (1.0 + wealth_index))
        * real_income
        * trade_modifier
    )

    formula_signature = _formula_signature(formulas, ordered_resources)
    formula_plan = _compile_formula_plan(ordered_resources, formula_signature)
    powers = {
        elasticity: np.power(wealth_index, elasticity)
        for elasticity in {entry[4] for entry in formula_plan}
    }
    resource_indices = {
        resource_id: index for index, resource_id in enumerate(ordered_resources)
    }
    computed: dict[str, np.ndarray] = {}
    raw_matrix = np.empty(
        (len(layout.selected_ids), len(ordered_resources)),
        dtype=np.float64,
    )
    for resource_id, solvent_base, general_base, multiplier, elasticity, dependencies in formula_plan:
        demand = (
            solvent_population * solvent_base * powers[elasticity]
            + population_values * general_base
        ) * multiplier
        for dependency, coefficient in dependencies:
            if dependency in computed:
                demand = demand + computed[dependency] * coefficient
        computed[resource_id] = demand
        raw_matrix[:, resource_indices[resource_id]] = demand

    total_raw_demand = raw_matrix.sum(axis=1)
    normalization = np.divide(
        consumption_pool,
        total_raw_demand,
        out=np.zeros_like(consumption_pool),
        where=total_raw_demand > 0.0,
    )
    normalized = raw_matrix * normalization[:, None]
    consumption = normalized[:, layout.sorted_resource_indices].reshape(-1)
    return layout.key_grid.with_columns(pl.Series("consumption_usd", consumption))


def _build_layout(
    country_ids: pl.Series,
    population_ids: pl.Series,
    resource_order: tuple[str, ...],
) -> _ConsumptionLayout | None:
    if country_ids.null_count() > 0 or population_ids.null_count() > 0:
        return None

    country_values = country_ids.to_list()
    population_values = population_ids.to_list()
    if (
        any(not isinstance(country_id, str) for country_id in country_values)
        or any(not isinstance(country_id, str) for country_id in population_values)
        or len(set(country_values)) != len(country_values)
        or len(set(population_values)) != len(population_values)
    ):
        return None

    country_index = {
        country_id: index for index, country_id in enumerate(country_values)
    }
    population_index = {
        country_id: index for index, country_id in enumerate(population_values)
    }
    selected_ids = tuple(sorted(country_index.keys() & population_index.keys()))
    country_row_indices = np.fromiter(
        (country_index[country_id] for country_id in selected_ids),
        dtype=np.intp,
        count=len(selected_ids),
    )
    population_row_indices = np.fromiter(
        (population_index[country_id] for country_id in selected_ids),
        dtype=np.intp,
        count=len(selected_ids),
    )
    sorted_resource_indices = np.asarray(
        sorted(range(len(resource_order)), key=resource_order.__getitem__),
        dtype=np.intp,
    )
    sorted_resource_ids = [resource_order[index] for index in sorted_resource_indices]
    key_grid = pl.DataFrame({"country_id": selected_ids}).join(
        pl.DataFrame({"game_resource_id": sorted_resource_ids}),
        how="cross",
    )
    return _ConsumptionLayout(
        country_ids,
        population_ids,
        resource_order,
        selected_ids,
        country_row_indices,
        population_row_indices,
        sorted_resource_indices,
        key_grid,
    )


def _formula_signature(
    formulas: Mapping[str, Mapping[str, Any]],
    resource_order: tuple[str, ...],
) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            resource_id,
            float(formulas[resource_id]["solvent_base_consumption"]),
            float(formulas[resource_id]["general_base_consumption"]),
            float(formulas[resource_id]["output_multiplier"]),
            float(formulas[resource_id].get("income_elasticity", 1.0)),
            tuple(
                (dependency, float(coefficient))
                for dependency, coefficient in formulas[resource_id]
                .get("resource_dependencies", {})
                .items()
            ),
        )
        for resource_id in resource_order
    )


@lru_cache(maxsize=16)
def _compile_formula_plan(
    resource_order: tuple[str, ...],
    formula_signature: tuple[tuple[Any, ...], ...],
) -> tuple[tuple[Any, ...], ...]:
    formulas = {entry[0]: entry for entry in formula_signature}
    pending = list(resource_order)
    computed: set[str] = set()
    plan: list[tuple[Any, ...]] = []
    while pending:
        ready = [
            resource_id
            for resource_id in pending
            if all(
                dependency in computed
                or dependency in _INITIAL_COLUMNS
                or dependency not in formulas
                for dependency, _ in formulas[resource_id][5]
            )
        ]
        if not ready:
            raise ValueError(
                f"Cyclic resource demand dependencies: {', '.join(pending)}"
            )
        for resource_id in ready:
            plan.append(formulas[resource_id])
            computed.add(resource_id)
        pending = [resource_id for resource_id in pending if resource_id not in computed]
    return tuple(plan)
