from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import polars as pl

from modules.base.systems.economy.market_data import (
    _FastMarketContext,
    _FastMarketLayout,
    _MarketIndexCache,
    _PreparedFastMarketOutput,
    _resource_market_metadata,
)


class MarketIndexLayoutResolver:
    def __init__(self) -> None:
        self._market_index_cache: _MarketIndexCache | None = None

    @property
    def market_index_cache(self) -> _MarketIndexCache | None:
        return self._market_index_cache

    @market_index_cache.setter
    def market_index_cache(self, value: _MarketIndexCache | None) -> None:
        self._market_index_cache = value

    def remember_layout(
        self,
        layout: _FastMarketLayout,
        prepared: _PreparedFastMarketOutput,
    ) -> None:
        if layout.cache_hit:
            return
        context = layout.context
        self._market_index_cache = _MarketIndexCache(
            context.country_id_series,
            prepared.market_output.get_column("country_id"),
            prepared.market_output.get_column("game_resource_id"),
            layout.physics_entries,
            prepared.cached_country_indices,
            prepared.cached_resource_indices,
            True,
            layout.country_ids_precede_world,
        )

    def resolve(
        self,
        context: _FastMarketContext,
        resource_physics: Mapping[str, Mapping[str, bool | float]],
    ) -> _FastMarketLayout | None:
        physics_entries = self._physics_entries(resource_physics)
        cached_indices = self._market_index_cache
        cache_hit = self._cache_matches(context, physics_entries, cached_indices)

        # Ledger and stockpiles have independent lifecycles, so validate their row alignment each tick.
        if not self._ledger_is_aligned(context):
            return None
        stockpiles = context.state.tables.get("stockpiles")
        if not self._stockpiles_are_aligned(context, stockpiles):
            return None
        if not self._keys_are_well_formed(context, cache_hit):
            return None
        keys_are_sorted, country_ids_precede_world = self._ordering_properties(
            context, cache_hit, cached_indices
        )
        if not self._numeric_schema_is_supported(context, stockpiles):
            return None

        (
            resource_indices_by_id,
            decay_rates_by_resource,
            storable_by_resource,
        ) = _resource_market_metadata(physics_entries)
        indices = self._resolve_indices(
            context,
            cached_indices,
            cache_hit,
            resource_indices_by_id,
        )
        if indices is None:
            return None
        country_indices, resource_indices = indices
        if not self._indices_are_valid(country_indices, resource_indices):
            return None

        return _FastMarketLayout(
            context=context,
            stockpiles=stockpiles,
            physics_entries=physics_entries,
            country_indices=country_indices,
            resource_indices=resource_indices,
            decay_rates_by_resource=decay_rates_by_resource,
            storable_by_resource=storable_by_resource,
            cache_hit=cache_hit,
            keys_are_sorted=keys_are_sorted,
            country_ids_precede_world=country_ids_precede_world,
        )

    @staticmethod
    def _physics_entries(
        resource_physics: Mapping[str, Mapping[str, bool | float]],
    ) -> tuple[tuple[str, bool, float], ...]:
        return tuple(
            (resource_id, bool(values["is_storable"]), float(values["decay_rate"]))
            for resource_id, values in resource_physics.items()
        )

    @staticmethod
    def _cache_matches(
        context: _FastMarketContext,
        physics_entries: tuple[tuple[str, bool, float], ...],
        cached_indices: _MarketIndexCache | None,
    ) -> bool:
        return (
            cached_indices is not None
            and cached_indices.country_ids.equals(context.country_id_series)
            and cached_indices.production_country_ids.equals(context.production_country_ids)
            and cached_indices.production_resource_ids.equals(context.production_resource_ids)
            and cached_indices.physics_entries == physics_entries
        )

    @staticmethod
    def _ledger_is_aligned(context: _FastMarketContext) -> bool:
        return (
            context.production_country_ids.equals(context.ledger.get_column("country_id"))
            and context.production_resource_ids.equals(context.ledger.get_column("game_resource_id"))
        )

    @staticmethod
    def _stockpiles_are_aligned(
        context: _FastMarketContext,
        stockpiles: pl.DataFrame | None,
    ) -> bool:
        if stockpiles is None:
            return True
        required_columns = {"country_id", "game_resource_id", "stock_amount"}
        return (
            required_columns.issubset(stockpiles.columns)
            and context.production_country_ids.equals(stockpiles.get_column("country_id"))
            and context.production_resource_ids.equals(stockpiles.get_column("game_resource_id"))
        )

    @staticmethod
    def _keys_are_well_formed(context: _FastMarketContext, cache_hit: bool) -> bool:
        if cache_hit:
            return True
        return (
            not context.production.select(
                pl.struct(context.key_columns).is_duplicated().any()
            ).item()
            and context.country_id_series.null_count() == 0
            and context.production_country_ids.null_count() == 0
            and context.production_resource_ids.null_count() == 0
        )

    @staticmethod
    def _ordering_properties(
        context: _FastMarketContext,
        cache_hit: bool,
        cached_indices: _MarketIndexCache | None,
    ) -> tuple[bool, bool]:
        if cache_hit:
            return (
                cached_indices.keys_are_sorted,
                cached_indices.country_ids_precede_world,
            )
        return (
            context.production.select(pl.struct(context.key_columns)).to_series().is_sorted(),
            all(country_id < "WORLD" for country_id in context.country_id_series.to_list()),
        )

    @staticmethod
    def _numeric_schema_is_supported(
        context: _FastMarketContext,
        stockpiles: pl.DataFrame | None,
    ) -> bool:
        supported_numeric_types = {
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
        numeric_columns = (
            (context.production, "domestic_production"),
            (context.production, "tax_rate"),
            (context.ledger, "consumption_usd"),
            (context.countries, "economic_trade_modifier"),
            (stockpiles, "stock_amount"),
        )
        return not any(
            frame is not None
            and column in frame.columns
            and frame.schema[column] not in supported_numeric_types
            for frame, column in numeric_columns
        )

    @staticmethod
    def _resolve_indices(
        context: _FastMarketContext,
        cached_indices: _MarketIndexCache | None,
        cache_hit: bool,
        resource_indices_by_id: dict[str, int],
    ) -> tuple[np.ndarray, np.ndarray] | None:
        if cache_hit:
            return cached_indices.country_indices, cached_indices.resource_indices

        country_ids = context.country_id_series.to_list()
        country_index_by_id = {
            str(country_id): index for index, country_id in enumerate(country_ids)
        }
        if len(country_index_by_id) != len(country_ids):
            return None

        # Build Python hash mappings once per stable key layout, not once per tick.
        row_count = context.production.height
        country_indices = np.fromiter(
            (
                country_index_by_id.get(country_id, -1)
                for country_id in context.production_country_ids.to_numpy()
            ),
            dtype=np.int32,
            count=row_count,
        )
        resource_indices = np.fromiter(
            (
                resource_indices_by_id.get(resource_id, -1)
                for resource_id in context.production_resource_ids.to_numpy()
            ),
            dtype=np.int32,
            count=row_count,
        )
        return country_indices, resource_indices

    @staticmethod
    def _indices_are_valid(
        country_indices: np.ndarray,
        resource_indices: np.ndarray,
    ) -> bool:
        return not (country_indices < 0).any() and not (resource_indices < 0).any()
