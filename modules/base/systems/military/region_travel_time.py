"""Movement estimates with a lazily built coordinate index for one map snapshot."""

from __future__ import annotations

import polars as pl

from modules.base.systems.military.military_system import (
    DEFAULT_MOVE_MINUTES,
    MovementDurationPolicy,
)
from src.core.map.geo import GeoCoordinate


class RegionTravelTime:
    """Reuse region coordinates across route searches within one system update."""

    def __init__(
        self,
        regions: pl.DataFrame | None,
        duration_policy: MovementDurationPolicy | None = None,
    ) -> None:
        self._regions = regions
        self._duration_policy = duration_policy or MovementDurationPolicy()
        self._locations: dict[int, GeoCoordinate] | None = None
        self._edge_distance_km: dict[tuple[int, int], float] = {}

    def use_edge_distance_index(self, edge_distance_km: dict[tuple[int, int], float]) -> None:
        self._edge_distance_km = edge_distance_km

    def estimate_minutes(self, source_region_id: int, target_region_id: int) -> int:
        source_id, target_id = int(source_region_id), int(target_region_id)
        edge_key = (source_id, target_id) if source_id < target_id else (target_id, source_id)
        distance = self._edge_distance_km.get(edge_key)
        if distance is not None:
            return self._duration_policy.estimate_from_distance(distance)

        if self._locations is None:
            # Route searches evaluate many edges; rebuilding the world index for
            # each edge made a single simulation tick take over a minute.
            self._locations = (
                {} if self._regions is None
                else self._duration_policy.region_locations(self._regions)
            )
        source = self._locations.get(source_id)
        target = self._locations.get(target_id)
        if source is None or target is None:
            return DEFAULT_MOVE_MINUTES
        return self._duration_policy.estimate_between(source, target)
