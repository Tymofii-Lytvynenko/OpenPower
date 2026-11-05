from __future__ import annotations

from typing import Optional

import numpy as np

from src.client.renderers.unit_projection_data import (
    PreparedUnitProjectionData,
    PreparedUnitProjectionRow,
    RegionAnchor,
    UnitReadinessProjection,
    UnitProjectionRegionIds,
)
from src.core.map.geo import EquirectangularProjection, GeoCoordinate


class UnitGeographyResolver:
    """Resolve unit coordinates and convert them to globe-space vectors."""

    def __init__(self, projection: EquirectangularProjection) -> None:
        self._projection = projection

    def to_unit_vector(self, geo: GeoCoordinate) -> np.ndarray:
        x, y, z = self._projection.geo_to_unit_vector(geo)
        return np.array([x, y, z], dtype=np.float32)

    @staticmethod
    def row_geo(
        row: dict,
        latitude_key: str,
        longitude_key: str,
    ) -> Optional[GeoCoordinate]:
        latitude = row.get(latitude_key)
        longitude = row.get(longitude_key)
        if latitude is None or longitude is None:
            return None
        return GeoCoordinate(latitude=float(latitude), longitude=float(longitude))

    @staticmethod
    def anchor_geo(
        region_lookup: dict[int, RegionAnchor],
        primary_region_id: int,
        fallback_region_id: Optional[int] = None,
    ) -> Optional[GeoCoordinate]:
        anchor = region_lookup.get(primary_region_id)
        if anchor is None and fallback_region_id is not None:
            anchor = region_lookup.get(fallback_region_id)
        return anchor.geo if anchor is not None else None

    def resolve_vectors(
        self,
        row: dict,
        region_lookup: dict[int, RegionAnchor],
        region_ids: UnitProjectionRegionIds,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        current_geo = self.row_geo(row, "latitude", "longitude")
        source_geo = self.row_geo(row, "source_latitude", "source_longitude")
        target_geo = self.row_geo(row, "target_latitude", "target_longitude")
        source = (
            source_geo
            or current_geo
            or self.anchor_geo(
                region_lookup,
                region_ids.source,
                region_ids.current,
            )
        )
        if source is None:
            return None

        target = target_geo if region_ids.target > 0 else None
        if target is None and region_ids.target > 0:
            target = self.anchor_geo(region_lookup, region_ids.target)
        source_vector = self.to_unit_vector(source)
        target_vector = (
            self.to_unit_vector(target) if target is not None else source_vector
        )
        return source_vector, target_vector


class UnitReadinessResolver:
    """Normalize readiness labels and calculate the remaining transition time."""

    @staticmethod
    def resolve(
        row: dict,
        current_game_minute: float | None,
    ) -> UnitReadinessProjection:
        status = str(row.get("readiness_status", "ready") or "ready").strip().lower()
        target = str(row.get("readiness_target", status) or status).strip().lower()
        transition_id = str(row.get("readiness_transition_id", "") or "")
        eta_minute = int(row.get("readiness_eta_minute", 0) or 0)
        remaining_minutes = (
            max(0, eta_minute - int(current_game_minute or 0))
            if transition_id
            else 0
        )
        return UnitReadinessProjection(
            status=status,
            target=target,
            progress=float(row.get("readiness_progress", 0.0) or 0.0),
            transition_id=transition_id,
            eta_minute=eta_minute,
            remaining_minutes=remaining_minutes,
        )


class UnitProjectionRowNormalizer:
    """Normalize one raw unit record while preserving geographic fallbacks."""

    def __init__(
        self,
        geography: UnitGeographyResolver,
        readiness_resolver: UnitReadinessResolver,
    ) -> None:
        self._geography = geography
        self._readiness_resolver = readiness_resolver

    def normalize(
        self,
        row: dict,
        region_lookup: dict[int, RegionAnchor],
        current_game_minute: float | None,
    ) -> PreparedUnitProjectionRow | None:
        region_ids = self._region_ids(row)
        vectors = self._geography.resolve_vectors(
            row,
            region_lookup,
            region_ids,
        )
        if vectors is None:
            return None
        source_vector, target_vector = vectors
        readiness = self._readiness_resolver.resolve(row, current_game_minute)
        return self._prepared_row(row, region_ids, source_vector, target_vector, readiness)

    @staticmethod
    def _region_ids(row: dict) -> UnitProjectionRegionIds:
        current_region_id = UnitProjectionRowNormalizer._integer(
            row,
            "current_region_id",
            0,
        )
        return UnitProjectionRegionIds(
            current=current_region_id,
            source=UnitProjectionRowNormalizer._integer(
                row,
                "source_region_id",
                current_region_id,
            ),
            target=UnitProjectionRowNormalizer._integer(row, "target_region_id", -1),
        )

    @staticmethod
    def _integer(row: dict, field_name: str, default: int) -> int:
        return int(row.get(field_name, default) or default)

    @staticmethod
    def _number(row: dict, field_name: str, default: float) -> float:
        return float(row.get(field_name, default) or default)

    def _prepared_row(
        self,
        row: dict,
        region_ids: UnitProjectionRegionIds,
        source_vector: np.ndarray,
        target_vector: np.ndarray,
        readiness: UnitReadinessProjection,
    ) -> PreparedUnitProjectionRow:
        return PreparedUnitProjectionRow(
            unit_id=str(row.get("id", "")),
            owner=str(row.get("owner", "")),
            unit_type=str(row.get("unit_type", "")),
            strength=self._integer(row, "strength", 1),
            current_region_id=region_ids.current,
            target_region_id=region_ids.target,
            source_vector=source_vector,
            target_vector=target_vector,
            movement_progress=self._number(row, "movement_progress", 0.0),
            departed_at_minute=self._number(row, "departed_at_minute", 0.0),
            arrival_at_minute=self._number(row, "arrival_at_minute", 0.0),
            is_moving=bool(row.get("is_moving", False)),
            readiness=readiness,
        )


class PreparedUnitProjectionBatchBuilder:
    """Collect normalized rows into typed, index-aligned projection columns."""

    def __init__(self) -> None:
        self._rows: list[PreparedUnitProjectionRow] = []

    def add(self, row: PreparedUnitProjectionRow) -> None:
        self._rows.append(row)

    def build(self) -> PreparedUnitProjectionData:
        if not self._rows:
            return PreparedUnitProjectionData.empty()
        return PreparedUnitProjectionData(
            unit_ids=self._values("unit_id"),
            owners=self._values("owner"),
            unit_types=self._values("unit_type"),
            strengths=self._array("strength", np.int32),
            current_region_ids=self._array("current_region_id", np.int32),
            target_region_ids=self._array("target_region_id", np.int32),
            source_vectors=self._array("source_vector", np.float32),
            target_vectors=self._array("target_vector", np.float32),
            movement_progress=self._array("movement_progress", np.float32),
            departed_at_minutes=self._array("departed_at_minute", np.float32),
            arrival_at_minutes=self._array("arrival_at_minute", np.float32),
            is_moving=self._array("is_moving", np.bool_),
            readiness_statuses=self._readiness_values("status"),
            readiness_targets=self._readiness_values("target"),
            readiness_progress=self._readiness_array("progress", np.float32),
            readiness_transition_ids=self._readiness_values("transition_id"),
            readiness_eta_minutes=self._readiness_array("eta_minute", np.int64),
            readiness_remaining_minutes=self._readiness_array(
                "remaining_minutes",
                np.int64,
            ),
        )

    def _values(self, field_name: str) -> list:
        return [getattr(row, field_name) for row in self._rows]

    def _array(self, field_name: str, dtype: type) -> np.ndarray:
        return np.asarray(self._values(field_name), dtype=dtype)

    def _readiness_values(self, field_name: str) -> list:
        return [getattr(row.readiness, field_name) for row in self._rows]

    def _readiness_array(self, field_name: str, dtype: type) -> np.ndarray:
        return np.asarray(self._readiness_values(field_name), dtype=dtype)


class UnitProjectionDataPreparer:
    """Build aligned vectorized data for the unit projection pass."""

    def __init__(self, geography: UnitGeographyResolver) -> None:
        self._geography = geography
        self._row_normalizer = UnitProjectionRowNormalizer(
            geography,
            UnitReadinessResolver(),
        )

    def prepare(
        self,
        unit_rows: list[dict],
        region_lookup: dict[int, RegionAnchor],
        current_game_minute: float | None = None,
    ) -> PreparedUnitProjectionData:
        if not unit_rows:
            return PreparedUnitProjectionData.empty()

        batch = PreparedUnitProjectionBatchBuilder()
        for row in unit_rows:
            prepared = self._row_normalizer.normalize(
                row,
                region_lookup,
                current_game_minute,
            )
            if prepared is not None:
                batch.add(prepared)
        return batch.build()
