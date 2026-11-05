from __future__ import annotations

import polars as pl

from modules.base.systems.economy.market_data import _FastMarketContext
from src.shared.state import GameState


class FastMarketEligibilityPolicy:
    @staticmethod
    def select_context(state: GameState) -> _FastMarketContext | None:
        production = state.tables.get("domestic_production")
        countries = state.tables.get("countries")
        ledger = state.tables.get("resource_ledger")
        regional = state.tables.get("regional_production")
        treaty_effects = state.tables.get("treaty_effects")

        if not FastMarketEligibilityPolicy._has_required_tables(
            production, countries, ledger
        ):
            return None
        if not FastMarketEligibilityPolicy._has_unconstrained_market(
            production, regional, treaty_effects
        ):
            return None
        if not FastMarketEligibilityPolicy._has_required_columns(
            production, countries, ledger
        ):
            return None
        key_columns = ("country_id", "game_resource_id")
        production_country_ids = production.get_column("country_id")
        production_resource_ids = production.get_column("game_resource_id")
        country_id_series = countries.get_column("id")
        if not FastMarketEligibilityPolicy._uses_string_keys(
            production, countries
        ):
            return None

        return _FastMarketContext(
            state=state,
            production=production,
            countries=countries,
            ledger=ledger,
            country_id_series=country_id_series,
            production_country_ids=production_country_ids,
            production_resource_ids=production_resource_ids,
            key_columns=key_columns,
        )

    @staticmethod
    def _has_required_tables(
        production: pl.DataFrame | None,
        countries: pl.DataFrame | None,
        ledger: pl.DataFrame | None,
    ) -> bool:
        return production is not None and countries is not None and ledger is not None

    @staticmethod
    def _has_unconstrained_market(
        production: pl.DataFrame,
        regional: pl.DataFrame | None,
        treaty_effects: pl.DataFrame | None,
    ) -> bool:
        return (
            not production.is_empty()
            and (regional is None or regional.is_empty())
            and (treaty_effects is None or treaty_effects.is_empty())
        )

    @staticmethod
    def _has_required_columns(
        production: pl.DataFrame,
        countries: pl.DataFrame,
        ledger: pl.DataFrame,
    ) -> bool:
        return (
            {"country_id", "game_resource_id", "domestic_production"}.issubset(
                production.columns
            )
            and {"country_id", "game_resource_id", "consumption_usd"}.issubset(
                ledger.columns
            )
            and "id" in countries.columns
        )

    @staticmethod
    def _uses_string_keys(
        production: pl.DataFrame,
        countries: pl.DataFrame,
    ) -> bool:
        return (
            countries.schema["id"] == pl.String
            and production.schema["country_id"] == pl.String
            and production.schema["game_resource_id"] == pl.String
        )
