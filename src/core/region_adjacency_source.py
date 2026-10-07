"""Configuration-aware loading of the runtime region adjacency table."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
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
            return _cached_region_adjacency(candidate, valid_ids)
    fallback = config.get_asset_path("map/regions.png")
    if fallback.exists():
        return _cached_region_adjacency(fallback, valid_ids)
    return pl.DataFrame(schema=REGION_ADJACENCY_SCHEMA)


def _cached_region_adjacency(image_path: Path, valid_ids: set[int]) -> pl.DataFrame:
    resolved_path = image_path.resolve()
    stat = resolved_path.stat()
    return _load_region_adjacency(
        str(resolved_path),
        stat.st_mtime_ns,
        stat.st_size,
        tuple(sorted(valid_ids)),
    )


@lru_cache(maxsize=8)
def _load_region_adjacency(
    image_path: str,
    _modified_ns: int,
    _file_size: int,
    valid_region_ids: tuple[int, ...],
) -> pl.DataFrame:
    # Reuse the compact result across sessions so large region maps are decoded only once.
    return RegionAdjacencyBuilder().from_image(Path(image_path), set(valid_region_ids))
