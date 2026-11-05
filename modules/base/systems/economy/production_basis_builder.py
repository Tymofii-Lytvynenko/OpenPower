from typing import Any, Callable

import polars as pl

from modules.base.systems.politics.political_effect_policy import (
    aggregate_political_effects_by_type,
    bounded_modifier,
)
from src.shared.state import GameState


class ProductionBasisBuilder:
    """Build the effective production frame from infrastructure and policy inputs."""

    def __init__(
        self,
        effect_aggregator: Callable[..., dict[tuple[str, str, str], float]] = aggregate_political_effects_by_type,
        modifier_bounder: Callable[[float], float] = bounded_modifier,
    ) -> None:
        self._effect_aggregator = effect_aggregator
        self._modifier_bounder = modifier_bounder

    def build(
        self,
        state: GameState,
        countries_lf: pl.LazyFrame,
        country_schema: set[str],
        prod_table: pl.DataFrame,
    ) -> pl.LazyFrame:
        production_basis = self._with_infrastructure(
            prod_table.lazy(),
            countries_lf,
            country_schema,
            state,
        )
        return self._with_political_modifiers(
            production_basis,
            countries_lf,
            country_schema,
            state,
        )

    @staticmethod
    def _with_infrastructure(
        production_basis: pl.LazyFrame,
        countries_lf: pl.LazyFrame,
        country_schema: set[str],
        state: GameState,
    ) -> pl.LazyFrame:
        infrastructure = state.tables.get("regional_infrastructure")
        if infrastructure is None or infrastructure.is_empty():
            return production_basis.with_columns(
                pl.col("domestic_production").alias("_effective_production")
            )
        if "industrial_access_index" not in country_schema:
            return production_basis.with_columns(
                pl.col("domestic_production").alias("_effective_production")
            )
        industrial_access = countries_lf.select(
            pl.col("id"),
            pl.col("industrial_access_index").clip(0.0, 1.0).alias("_industrial_access"),
        )
        return production_basis.join(
            industrial_access,
            left_on="country_id",
            right_on="id",
            how="left",
        ).with_columns(
            # Infrastructure limits throughput but does not switch an established economy off.
            (
                pl.col("domestic_production")
                * (0.75 + 0.25 * pl.col("_industrial_access").fill_null(1.0))
            ).alias("_effective_production")
        )

    def _with_political_modifiers(
        self,
        production_basis: pl.LazyFrame,
        countries_lf: pl.LazyFrame,
        country_schema: set[str],
        state: GameState,
    ) -> pl.LazyFrame:
        political_rows = self._political_modifier_rows(state)
        has_country_modifier = "economic_production_modifier" in country_schema
        if not has_country_modifier and not political_rows:
            return production_basis

        production_modifier = (
            pl.col("economic_production_modifier").fill_null(1.0).clip(0.5, 1.0)
            if has_country_modifier
            else pl.lit(1.0)
        )
        production_modifiers = countries_lf.select(
            pl.col("id").alias("_modifier_country_id"),
            production_modifier.alias("_economic_production_modifier"),
        )
        if political_rows:
            production_modifiers = production_modifiers.join(
                pl.DataFrame(political_rows).lazy(),
                on="_modifier_country_id",
                how="left",
            ).with_columns(
                pl.col("_political_production_modifier").fill_null(1.0),
                pl.col("_political_labor_modifier").fill_null(1.0),
            )
        else:
            production_modifiers = production_modifiers.with_columns(
                pl.lit(1.0).alias("_political_production_modifier"),
                pl.lit(1.0).alias("_political_labor_modifier"),
            )
        return production_basis.join(
            production_modifiers,
            left_on="country_id",
            right_on="_modifier_country_id",
            how="left",
        ).with_columns(
            (
                pl.col("_effective_production")
                * pl.col("_economic_production_modifier").fill_null(1.0)
                * pl.col("_political_production_modifier").fill_null(1.0)
                * pl.col("_political_labor_modifier").fill_null(1.0)
            ).alias("_effective_production")
        )

    def _political_modifier_rows(self, state: GameState) -> list[dict[str, Any]]:
        political_effects = state.tables.get("political_effects")
        if political_effects is None or political_effects.is_empty():
            return []
        political_outputs = self._effect_aggregator(
            political_effects,
            int(state.time.total_minutes),
            selectors={
                ("economy", "production_modifier"),
                ("labor", "labor_supply_modifier"),
            },
        )
        production = {
            country_id: value
            for (country_id, domain, effect), value in political_outputs.items()
            if (domain, effect) == ("economy", "production_modifier")
        }
        labor = {
            country_id: value
            for (country_id, domain, effect), value in political_outputs.items()
            if (domain, effect) == ("labor", "labor_supply_modifier")
        }
        return [
            {
                "_modifier_country_id": country_id,
                "_political_production_modifier": self._modifier_bounder(
                    production.get(country_id, 0.0)
                ),
                "_political_labor_modifier": self._modifier_bounder(
                    labor.get(country_id, 0.0)
                ),
            }
            for country_id in sorted(set(production) | set(labor))
        ]
