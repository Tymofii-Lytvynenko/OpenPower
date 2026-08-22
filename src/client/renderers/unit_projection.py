from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from src.client.controllers.camera_controller import CameraController
from src.core.map.geo import EquirectangularProjection, GeoCoordinate


UNIT_BILLBOARD_BASE_WIDTH = 17.0
UNIT_BILLBOARD_ZOOM_BONUS = 9.0
UNIT_BILLBOARD_ASPECT_RATIO = 0.68


@dataclass(frozen=True)
class RegionAnchor:
    region_id: int
    geo: GeoCoordinate
    owner: str


@dataclass
class ProjectedUnit:
    unit_id: str
    owner: str
    unit_type: str
    strength: int
    current_region_id: int
    target_region_id: int
    screen_x: float
    screen_y: float
    distance_to_camera: float
    width: float
    height: float
    movement_progress: float
    is_moving: bool
    readiness_status: str = "ready"
    readiness_target: str = "ready"
    readiness_progress: float = 0.0
    readiness_transition_id: str = ""
    readiness_eta_minute: int = 0
    readiness_remaining_minutes: int = 0
    readiness_remaining_label: str = ""
    local_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    stack_index: int = 0
    stack_count: int = 1

    def contains(self, screen_x: float, screen_y: float) -> bool:
        half_w = self.width * 0.5
        half_h = self.height * 0.5
        return (
            self.screen_x - half_w <= screen_x <= self.screen_x + half_w
            and self.screen_y - half_h <= screen_y <= self.screen_y + half_h
        )


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
    def empty(cls) -> "PreparedUnitProjectionData":
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


class UnitProjectionService:
    """
    Projects spherical world-space unit anchors into screen-space billboards.
    The renderer stays presentation-only while this service owns coordinate math.
    """

    def __init__(
        self,
        camera: CameraController,
        map_width: int,
        map_height: int,
        globe_radius: float,
        surface_offset: float = 0.0,
    ):
        self.camera = camera
        self.map_width = max(1, int(map_width))
        self.map_height = max(1, int(map_height))
        self.globe_radius = float(globe_radius)
        # Billboards are drawn in screen space, so lifting their anchor above the
        # globe creates visible parallax drift at close zoom instead of preventing
        # z-fighting.
        self.surface_radius = float(globe_radius + surface_offset)
        self._geo_projection = EquirectangularProjection(self.map_width, self.map_height)

    def project_units(
        self,
        unit_rows: list[dict],
        region_lookup: dict[int, RegionAnchor],
        window_width: int,
        window_height: int,
        presentation_total_minutes: float | None = None,
    ) -> list[ProjectedUnit]:
        prepared = self.prepare_units(unit_rows, region_lookup)
        return self.project_prepared_units(
            prepared,
            window_width,
            window_height,
            presentation_total_minutes,
        )

    def prepare_units(
        self,
        unit_rows: list[dict],
        region_lookup: dict[int, RegionAnchor],
        current_game_minute: float | None = None,
    ) -> PreparedUnitProjectionData:
        if not unit_rows:
            return PreparedUnitProjectionData.empty()

        unit_ids: list[str] = []
        owners: list[str] = []
        unit_types: list[str] = []
        strengths: list[int] = []
        current_region_ids: list[int] = []
        target_region_ids: list[int] = []
        source_vectors: list[np.ndarray] = []
        target_vectors: list[np.ndarray] = []
        movement_progress: list[float] = []
        departed_at_minutes: list[float] = []
        arrival_at_minutes: list[float] = []
        is_moving: list[bool] = []
        readiness_statuses: list[str] = []
        readiness_targets: list[str] = []
        readiness_progress: list[float] = []
        readiness_transition_ids: list[str] = []
        readiness_eta_minutes: list[int] = []
        readiness_remaining_minutes: list[int] = []

        for row in unit_rows:
            current_region_id = int(row.get("current_region_id", 0) or 0)
            source_region_id = int(row.get("source_region_id", current_region_id) or current_region_id)
            target_region_id = int(row.get("target_region_id", -1) or -1)

            current_geo = self._row_geo(row, "latitude", "longitude")
            source_geo = self._row_geo(row, "source_latitude", "source_longitude")
            target_geo = self._row_geo(row, "target_latitude", "target_longitude")

            source = source_geo or current_geo or self._anchor_geo(region_lookup, source_region_id, current_region_id)
            if source is None:
                continue

            target = target_geo if target_region_id > 0 else None
            if target is None and target_region_id > 0:
                target = self._anchor_geo(region_lookup, target_region_id)

            source_vec = self._geo_to_unit_vector(source)
            target_vec = self._geo_to_unit_vector(target) if target is not None else source_vec

            unit_ids.append(str(row.get("id", "")))
            owners.append(str(row.get("owner", "")))
            unit_types.append(str(row.get("unit_type", "")))
            strengths.append(int(row.get("strength", 1) or 1))
            current_region_ids.append(current_region_id)
            target_region_ids.append(target_region_id)
            source_vectors.append(source_vec)
            target_vectors.append(target_vec)
            movement_progress.append(float(row.get("movement_progress", 0.0) or 0.0))
            departed_at_minutes.append(float(row.get("departed_at_minute", 0) or 0))
            arrival_at_minutes.append(float(row.get("arrival_at_minute", 0) or 0))
            is_moving.append(bool(row.get("is_moving", False)))
            readiness_status = str(row.get("readiness_status", "ready") or "ready").strip().lower()
            transition_id = str(row.get("readiness_transition_id", "") or "")
            eta_minute = int(row.get("readiness_eta_minute", 0) or 0)
            remaining_minutes = max(
                0,
                eta_minute - int(current_game_minute or 0),
            ) if transition_id else 0
            readiness_statuses.append(readiness_status)
            readiness_targets.append(str(row.get("readiness_target", readiness_status) or readiness_status).strip().lower())
            readiness_progress.append(float(row.get("readiness_progress", 0.0) or 0.0))
            readiness_transition_ids.append(transition_id)
            readiness_eta_minutes.append(eta_minute)
            readiness_remaining_minutes.append(remaining_minutes)

        if not unit_ids:
            return PreparedUnitProjectionData.empty()

        return PreparedUnitProjectionData(
            unit_ids=unit_ids,
            owners=owners,
            unit_types=unit_types,
            strengths=np.asarray(strengths, dtype=np.int32),
            current_region_ids=np.asarray(current_region_ids, dtype=np.int32),
            target_region_ids=np.asarray(target_region_ids, dtype=np.int32),
            source_vectors=np.asarray(source_vectors, dtype=np.float32),
            target_vectors=np.asarray(target_vectors, dtype=np.float32),
            movement_progress=np.asarray(movement_progress, dtype=np.float32),
            departed_at_minutes=np.asarray(departed_at_minutes, dtype=np.float32),
            arrival_at_minutes=np.asarray(arrival_at_minutes, dtype=np.float32),
            is_moving=np.asarray(is_moving, dtype=np.bool_),
            readiness_statuses=readiness_statuses,
            readiness_targets=readiness_targets,
            readiness_progress=np.asarray(readiness_progress, dtype=np.float32),
            readiness_transition_ids=readiness_transition_ids,
            readiness_eta_minutes=np.asarray(readiness_eta_minutes, dtype=np.int64),
            readiness_remaining_minutes=np.asarray(readiness_remaining_minutes, dtype=np.int64),
        )

    def project_prepared_units(
        self,
        prepared: PreparedUnitProjectionData,
        window_width: int,
        window_height: int,
        presentation_total_minutes: float | None = None,
    ) -> list[ProjectedUnit]:
        if window_width <= 0 or window_height <= 0:
            return []
        if prepared.count == 0:
            return []

        self.camera.update_matrices(window_width, window_height)
        vp_matrix, model_matrix = self.camera.get_cached_matrices()
        if vp_matrix is None or model_matrix is None:
            return []

        camera_pos = np.array([0.0, 0.0, self.camera.distance], dtype=np.float32)
        effective_progress = self._presentation_movement_progress(
            prepared,
            presentation_total_minutes,
        )
        local_positions = self._resolve_local_positions(prepared, effective_progress)
        local_h = np.empty((prepared.count, 4), dtype=np.float32)
        local_h[:, :3] = local_positions
        local_h[:, 3] = 1.0

        world_h = local_h @ model_matrix.T
        world = world_h[:, :3]
        normal = self._normalize_rows(world)
        view_direction = camera_pos.reshape(1, 3) - world
        facing = np.einsum("ij,ij->i", normal, view_direction) > -0.02

        mvp_matrix = vp_matrix @ model_matrix
        clip = local_h @ mvp_matrix.T
        clip_w = clip[:, 3]
        valid_w = np.abs(clip_w) >= 1e-6

        ndc = np.empty((prepared.count, 3), dtype=np.float32)
        ndc[valid_w] = clip[valid_w, :3] / clip_w[valid_w, None]
        ndc[~valid_w] = 0.0

        in_frame = (
            (ndc[:, 0] >= -1.2)
            & (ndc[:, 0] <= 1.2)
            & (ndc[:, 1] >= -1.2)
            & (ndc[:, 1] <= 1.2)
        )
        visible = facing & valid_w & in_frame
        visible_indices = np.flatnonzero(visible)
        if visible_indices.size == 0:
            return []

        screen_x = (ndc[:, 0] * 0.5 + 0.5) * float(window_width)
        screen_y = (ndc[:, 1] * 0.5 + 0.5) * float(window_height)
        distances = np.linalg.norm(view_direction, axis=1)
        width, height = self._billboard_size()

        sorted_indices = visible_indices[np.argsort(distances[visible_indices])[::-1]]
        projected = [
            ProjectedUnit(
                unit_id=prepared.unit_ids[index],
                owner=prepared.owners[index],
                unit_type=prepared.unit_types[index],
                strength=int(prepared.strengths[index]),
                current_region_id=int(prepared.current_region_ids[index]),
                target_region_id=int(prepared.target_region_ids[index]),
                screen_x=float(screen_x[index]),
                screen_y=float(screen_y[index]),
                distance_to_camera=float(distances[index]),
                width=width,
                height=height,
                movement_progress=float(effective_progress[index]),
                is_moving=bool(prepared.is_moving[index]),
                readiness_status=prepared.readiness_statuses[index],
                readiness_target=prepared.readiness_targets[index],
                readiness_progress=float(prepared.readiness_progress[index]),
                readiness_transition_id=prepared.readiness_transition_ids[index],
                readiness_eta_minute=int(prepared.readiness_eta_minutes[index]),
                readiness_remaining_minutes=int(prepared.readiness_remaining_minutes[index]),
                readiness_remaining_label=self._format_remaining(int(prepared.readiness_remaining_minutes[index])),
                local_position=tuple(float(value) for value in local_positions[index]),
            )
            for index in sorted_indices
        ]

        self._apply_stack_offsets(projected)
        return projected

    def project_surface_ring(
        self,
        center_local_position: tuple[float, float, float],
        angular_radius: float,
        window_width: int,
        window_height: int,
        segments: int = 32,
    ) -> list[tuple[float, float] | None]:
        """Project a fixed geographic ring from the globe surface into screen space."""
        if window_width <= 0 or window_height <= 0 or segments < 3:
            return []

        center = np.asarray(center_local_position, dtype=np.float32)
        center_length = float(np.linalg.norm(center))
        if center_length <= 1e-6:
            return []
        center /= center_length

        reference = (
            np.array([0.0, 1.0, 0.0], dtype=np.float32)
            if abs(float(center[1])) < 0.9
            else np.array([1.0, 0.0, 0.0], dtype=np.float32)
        )
        tangent_a = self._safe_normalize(np.cross(reference, center))
        tangent_b = self._safe_normalize(np.cross(center, tangent_a))
        angles = np.linspace(0.0, 2.0 * np.pi, int(segments), endpoint=False, dtype=np.float32)
        directions = (
            center.reshape(1, 3) * np.cos(angular_radius)
            + (
                np.cos(angles)[:, None] * tangent_a.reshape(1, 3)
                + np.sin(angles)[:, None] * tangent_b.reshape(1, 3)
            )
            * np.sin(angular_radius)
        )
        local_positions = directions * self.surface_radius

        self.camera.update_matrices(window_width, window_height)
        vp_matrix, model_matrix = self.camera.get_cached_matrices()
        if vp_matrix is None or model_matrix is None:
            return []

        local_h = np.empty((segments, 4), dtype=np.float32)
        local_h[:, :3] = local_positions
        local_h[:, 3] = 1.0
        world_h = local_h @ model_matrix.T
        world = world_h[:, :3]
        normal = self._normalize_rows(world)
        camera_pos = np.array([0.0, 0.0, self.camera.distance], dtype=np.float32)
        facing = np.einsum("ij,ij->i", normal, camera_pos.reshape(1, 3) - world) > -0.02

        clip = local_h @ (vp_matrix @ model_matrix).T
        clip_w = clip[:, 3]
        valid_w = np.abs(clip_w) >= 1e-6
        ndc = np.zeros((segments, 3), dtype=np.float32)
        ndc[valid_w] = clip[valid_w, :3] / clip_w[valid_w, None]
        in_frame = (
            (ndc[:, 0] >= -1.2)
            & (ndc[:, 0] <= 1.2)
            & (ndc[:, 1] >= -1.2)
            & (ndc[:, 1] <= 1.2)
        )
        visible = facing & valid_w & in_frame

        screen_x = (ndc[:, 0] * 0.5 + 0.5) * float(window_width)
        screen_y = (1.0 - (ndc[:, 1] * 0.5 + 0.5)) * float(window_height)
        return [
            (float(screen_x[index]), float(screen_y[index])) if visible[index] else None
            for index in range(segments)
        ]

    def _presentation_movement_progress(
        self,
        prepared: PreparedUnitProjectionData,
        presentation_total_minutes: float | None,
    ) -> np.ndarray:
        # Snapshots arrive less often than render frames; the schedule lets the
        # overlay advance between snapshots without mutating authoritative state.
        progress = prepared.movement_progress.copy()
        if presentation_total_minutes is None:
            return progress

        valid_schedule = (
            prepared.is_moving
            & (prepared.target_region_ids > 0)
            & (prepared.arrival_at_minutes > prepared.departed_at_minutes)
        )
        if np.any(valid_schedule):
            progress[valid_schedule] = np.clip(
                (
                    float(presentation_total_minutes)
                    - prepared.departed_at_minutes[valid_schedule]
                )
                / (
                    prepared.arrival_at_minutes[valid_schedule]
                    - prepared.departed_at_minutes[valid_schedule]
                ),
                0.0,
                1.0,
            )
        return progress

    def _resolve_local_positions(
        self,
        prepared: PreparedUnitProjectionData,
        movement_progress: np.ndarray | None = None,
    ) -> np.ndarray:
        positions = prepared.source_vectors.copy()
        progress = prepared.movement_progress if movement_progress is None else movement_progress
        moving = (
            prepared.is_moving
            & (prepared.target_region_ids > 0)
            & (progress > 0.0)
        )
        if np.any(moving):
            positions[moving] = self._slerp_rows(
                prepared.source_vectors[moving],
                prepared.target_vectors[moving],
                progress[moving],
            )

        return positions * self.surface_radius

    def _slerp_rows(
        self,
        start: np.ndarray,
        end: np.ndarray,
        progress: np.ndarray,
    ) -> np.ndarray:
        t = np.clip(progress, 0.0, 1.0).astype(np.float32)
        dots = np.clip(np.einsum("ij,ij->i", start, end), -1.0, 1.0)
        result = np.empty_like(start)

        linear = dots > 0.9995
        if np.any(linear):
            t_linear = t[linear, None]
            result[linear] = self._normalize_rows(start[linear] + (end[linear] - start[linear]) * t_linear)

        curved = ~linear
        if np.any(curved):
            curved_start = start[curved]
            curved_end = end[curved]
            curved_t = t[curved]
            theta = np.arccos(dots[curved])
            sin_theta = np.sin(theta)
            safe = sin_theta > 1e-6
            curved_result = curved_start.copy()

            if np.any(safe):
                safe_start = curved_start[safe]
                safe_end = curved_end[safe]
                safe_theta = theta[safe]
                safe_sin = sin_theta[safe]
                safe_t = curved_t[safe]
                a = (np.sin((1.0 - safe_t) * safe_theta) / safe_sin)[:, None]
                b = (np.sin(safe_t * safe_theta) / safe_sin)[:, None]
                curved_result[safe] = self._normalize_rows((safe_start * a) + (safe_end * b))

            result[curved] = curved_result

        return result

    def _normalize_rows(self, values: np.ndarray) -> np.ndarray:
        lengths = np.linalg.norm(values, axis=1)
        safe = lengths > 1e-6
        result = values.copy()
        result[safe] = result[safe] / lengths[safe, None]
        return result

    def _project_unit(
        self,
        row: dict,
        region_lookup: dict[int, RegionAnchor],
        vp_matrix: np.ndarray,
        model_matrix: np.ndarray,
        camera_pos: np.ndarray,
        window_width: int,
        window_height: int,
    ) -> Optional[ProjectedUnit]:
        local_pos = self._unit_local_position(row, region_lookup)
        if local_pos is None:
            return None

        world_pos4 = model_matrix @ np.array([local_pos[0], local_pos[1], local_pos[2], 1.0], dtype=np.float32)
        world_pos = world_pos4[:3]
        normal = self._safe_normalize(world_pos)

        if float(np.dot(normal, camera_pos - world_pos)) <= -0.02:
            return None

        clip = vp_matrix @ world_pos4
        if abs(float(clip[3])) < 1e-6:
            return None

        ndc = clip[:3] / clip[3]
        if ndc[0] < -1.2 or ndc[0] > 1.2 or ndc[1] < -1.2 or ndc[1] > 1.2:
            return None

        screen_x = (float(ndc[0]) * 0.5 + 0.5) * window_width
        screen_y = (float(ndc[1]) * 0.5 + 0.5) * window_height
        width, height = self._billboard_size()

        return ProjectedUnit(
            unit_id=str(row.get("id", "")),
            owner=str(row.get("owner", "")),
            unit_type=str(row.get("unit_type", "")),
            strength=int(row.get("strength", 1) or 1),
            current_region_id=int(row.get("current_region_id", 0) or 0),
            target_region_id=int(row.get("target_region_id", -1) or -1),
            screen_x=screen_x,
            screen_y=screen_y,
            distance_to_camera=float(np.linalg.norm(camera_pos - world_pos)),
            width=width,
            height=height,
            movement_progress=float(row.get("movement_progress", 0.0) or 0.0),
            is_moving=bool(row.get("is_moving", False)),
            readiness_status=str(row.get("readiness_status", "ready") or "ready").strip().lower(),
            readiness_target=str(row.get("readiness_target", row.get("readiness_status", "ready")) or "ready").strip().lower(),
            readiness_progress=float(row.get("readiness_progress", 0.0) or 0.0),
            readiness_transition_id=str(row.get("readiness_transition_id", "") or ""),
            readiness_eta_minute=int(row.get("readiness_eta_minute", 0) or 0),
            readiness_remaining_minutes=max(
                0,
                int(row.get("readiness_eta_minute", 0) or 0)
                - int(row.get("current_game_minute", 0) or 0),
            ) if str(row.get("readiness_transition_id", "") or "") else 0,
            readiness_remaining_label=self._format_remaining(
                max(
                    0,
                    int(row.get("readiness_eta_minute", 0) or 0)
                    - int(row.get("current_game_minute", 0) or 0),
                )
            ) if str(row.get("readiness_transition_id", "") or "") else "",
            local_position=tuple(float(value) for value in local_pos),
        )

    def _unit_local_position(
        self,
        row: dict,
        region_lookup: dict[int, RegionAnchor],
    ) -> Optional[np.ndarray]:
        current_region_id = int(row.get("current_region_id", 0) or 0)
        source_region_id = int(row.get("source_region_id", current_region_id) or current_region_id)
        target_region_id = int(row.get("target_region_id", -1) or -1)
        progress = float(row.get("movement_progress", 0.0) or 0.0)

        current_geo = self._row_geo(row, "latitude", "longitude")
        source_geo = self._row_geo(row, "source_latitude", "source_longitude")
        target_geo = self._row_geo(row, "target_latitude", "target_longitude")

        source = source_geo or current_geo or self._anchor_geo(region_lookup, source_region_id, current_region_id)
        if source is None:
            return None

        source_vec = self._geo_to_unit_vector(source)
        if target_region_id <= 0 or progress <= 0.0:
            return source_vec * self.surface_radius

        target = target_geo or self._anchor_geo(region_lookup, target_region_id)
        if target is None:
            return source_vec * self.surface_radius

        target_vec = self._geo_to_unit_vector(target)
        return self._slerp(source_vec, target_vec, progress) * self.surface_radius

    def _geo_to_unit_vector(self, geo: GeoCoordinate) -> np.ndarray:
        x, y, z = self._geo_projection.geo_to_unit_vector(geo)
        return np.array([x, y, z], dtype=np.float32)

    def _format_remaining(self, minutes: int) -> str:
        days, remainder = divmod(max(0, int(minutes)), 24 * 60)
        hours = remainder // 60
        return f"{days}d {hours}h" if days else f"{hours}h"

    def _row_geo(self, row: dict, latitude_key: str, longitude_key: str) -> Optional[GeoCoordinate]:
        latitude = row.get(latitude_key)
        longitude = row.get(longitude_key)
        if latitude is None or longitude is None:
            return None

        return GeoCoordinate(latitude=float(latitude), longitude=float(longitude))

    def _anchor_geo(
        self,
        region_lookup: dict[int, RegionAnchor],
        primary_region_id: int,
        fallback_region_id: Optional[int] = None,
    ) -> Optional[GeoCoordinate]:
        anchor = region_lookup.get(primary_region_id)
        if anchor is None and fallback_region_id is not None:
            anchor = region_lookup.get(fallback_region_id)
        return anchor.geo if anchor is not None else None

    def _slerp(self, start: np.ndarray, end: np.ndarray, progress: float) -> np.ndarray:
        t = max(0.0, min(1.0, progress))
        dot = float(np.clip(np.dot(start, end), -1.0, 1.0))

        if dot > 0.9995:
            return self._safe_normalize(start + (end - start) * t)

        theta = float(np.arccos(dot))
        sin_theta = float(np.sin(theta))
        if sin_theta <= 1e-6:
            return start

        a = float(np.sin((1.0 - t) * theta) / sin_theta)
        b = float(np.sin(t * theta) / sin_theta)
        return self._safe_normalize((start * a) + (end * b))

    def _safe_normalize(self, value: np.ndarray) -> np.ndarray:
        length = float(np.linalg.norm(value))
        if length <= 1e-6:
            return value
        return value / length

    def _billboard_size(self) -> tuple[float, float]:
        zoom = (self.camera.max_distance - self.camera.distance) / max(
            self.camera.max_distance - self.camera.min_distance,
            1e-6,
        )
        width = UNIT_BILLBOARD_BASE_WIDTH + max(0.0, min(1.0, zoom)) * UNIT_BILLBOARD_ZOOM_BONUS
        return width, width * UNIT_BILLBOARD_ASPECT_RATIO

    def _apply_stack_offsets(self, units: list[ProjectedUnit]) -> None:
        groups: dict[tuple[int, int], list[ProjectedUnit]] = {}
        for unit in units:
            key = (round(unit.screen_x / 24.0), round(unit.screen_y / 24.0))
            groups.setdefault(key, []).append(unit)

        for group in groups.values():
            if len(group) <= 1:
                continue

            midpoint = (len(group) - 1) * 0.5
            for index, unit in enumerate(group):
                offset = (index - midpoint) * min(14.0, unit.width * 0.36)
                unit.screen_x += offset
                unit.screen_y += abs(index - midpoint) * 2.0
                unit.stack_index = index
                unit.stack_count = len(group)
