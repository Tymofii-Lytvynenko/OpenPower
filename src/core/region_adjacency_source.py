"""Configuration-aware loading of the runtime region adjacency table."""

from __future__ import annotations

from typing import Iterable

import polars as pl

from src.core.region_adjacency import REGION_ADJACENCY_SCHEMA, RegionAdjacencyBuilder
from src.shared.config import GameConfig


def load_region_adjacency(config: GameConfig, region_ids: Iterable[int]) -> pl.DataFrame:
    """Load adjacency from the highest-priority available region map."""
    valid_ids = {int(region_id) for region_id in region_ids if int(region_id) > 0}
    for data_directory in config.get_data_dirs():
        candidate = data_directory / "regions" / "regions.png"
        if candidate.exists():
            return RegionAdjacencyBuilder().from_image(candidate, valid_ids)
    fallback = config.get_asset_path("map/regions.png")
    if fallback.exists():
        return RegionAdjacencyBuilder().from_image(fallback, valid_ids)
    return pl.DataFrame(schema=REGION_ADJACENCY_SCHEMA)
