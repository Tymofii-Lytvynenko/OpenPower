from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import NamedTuple

import numpy as np
import polars as pl

from src.shared.state import GameState


@lru_cache(maxsize=4)
def _resource_market_metadata(
    physics_entries: tuple[tuple[str, bool, float], ...],
) -> tuple[dict[str, int], np.ndarray, np.ndarray]:
    resource_ids = tuple(resource_id for resource_id, _, _ in physics_entries)
    indices_by_id = {resource_id: index for index, resource_id in enumerate(resource_ids)}
    decay_rates = np.fromiter(
        (decay_rate for _, _, decay_rate in physics_entries),
        dtype=np.float64,
        count=len(physics_entries),
    )
    storable = np.fromiter(
        (is_storable for _, is_storable, _ in physics_entries),
        dtype=np.bool_,
        count=len(physics_entries),
    )
    return indices_by_id, decay_rates, storable


class _MarketIndexCache(NamedTuple):
    country_ids: pl.Series
    production_country_ids: pl.Series
    production_resource_ids: pl.Series
    physics_entries: tuple[tuple[str, bool, float], ...]
    country_indices: np.ndarray
    resource_indices: np.ndarray
    keys_are_sorted: bool
    country_ids_precede_world: bool


@dataclass(frozen=True)
class _FastMarketContext:
    state: GameState
    production: pl.DataFrame
    countries: pl.DataFrame
    ledger: pl.DataFrame
    country_id_series: pl.Series
    production_country_ids: pl.Series
    production_resource_ids: pl.Series
    key_columns: tuple[str, str]


@dataclass(frozen=True)
class _FastMarketLayout:
    context: _FastMarketContext
    stockpiles: pl.DataFrame | None
    physics_entries: tuple[tuple[str, bool, float], ...]
    country_indices: np.ndarray
    resource_indices: np.ndarray
    decay_rates_by_resource: np.ndarray
    storable_by_resource: np.ndarray
    cache_hit: bool
    keys_are_sorted: bool
    country_ids_precede_world: bool


@dataclass(frozen=True)
class _FastMarketArrays:
    production_values: np.ndarray
    demand: np.ndarray
    stock: np.ndarray
    trade_modifiers: np.ndarray
    trade_modifiers_by_country: np.ndarray
    government_controlled: np.ndarray
    legal: np.ndarray
    tax_rates: np.ndarray


@dataclass(frozen=True)
class _PreparedFastMarketOutput:
    market_output: pl.DataFrame
    cached_country_indices: np.ndarray
    cached_resource_indices: np.ndarray
