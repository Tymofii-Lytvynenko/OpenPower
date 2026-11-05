from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.core.map.geo import GeoCoordinate


@dataclass(frozen=True)
class RegionAnchor:
    region_id: int
    geo: GeoCoordinate
    owner: str


@dataclass(frozen=True)
class PreparedUnitProjectionData:
    unit_ids: list[str]
    owners: list[str]
    unit_types: list[str]
    strengths: np.ndarray
    current_region_ids: np.ndarray
    target_region_ids: np.ndarray
    source_vectors: np.ndarray
    target_vectors: np.ndarray
    movement_progress: np.ndarray
    departed_at_minutes: np.ndarray
    arrival_at_minutes: np.ndarray
    is_moving: np.ndarray
    readiness_statuses: list[str]
    readiness_targets: list[str]
    readiness_progress: np.ndarray
    readiness_transition_ids: list[str]
    readiness_eta_minutes: np.ndarray
    readiness_remaining_minutes: np.ndarray

    @property
    def count(self) -> int:
        return len(self.unit_ids)

    @classmethod
    def empty(cls) -> PreparedUnitProjectionData:
        empty_int = np.empty(0, dtype=np.int32)
        empty_float = np.empty(0, dtype=np.float32)
        empty_vectors = np.empty((0, 3), dtype=np.float32)
        return cls(
            unit_ids=[],
            owners=[],
            unit_types=[],
            strengths=empty_int,
            current_region_ids=empty_int,
            target_region_ids=empty_int,
            source_vectors=empty_vectors,
            target_vectors=empty_vectors,
            movement_progress=empty_float,
            departed_at_minutes=empty_float,
            arrival_at_minutes=empty_float,
            is_moving=np.empty(0, dtype=np.bool_),
            readiness_statuses=[],
            readiness_targets=[],
            readiness_progress=empty_float,
            readiness_transition_ids=[],
            readiness_eta_minutes=empty_int,
            readiness_remaining_minutes=empty_int,
        )


@dataclass(frozen=True)
class PreparedUnitProjectionRow:
    unit_id: str
    owner: str
    unit_type: str
    strength: int
    current_region_id: int
    target_region_id: int
    source_vector: np.ndarray
    target_vector: np.ndarray
    movement_progress: float
    departed_at_minute: float
    arrival_at_minute: float
    is_moving: bool
    readiness: UnitReadinessProjection


@dataclass(frozen=True)
class UnitProjectionRegionIds:
    current: int
    source: int
    target: int


@dataclass(frozen=True)
class UnitReadinessProjection:
    status: str
    target: str
    progress: float
    transition_id: str
    eta_minute: int
    remaining_minutes: int
