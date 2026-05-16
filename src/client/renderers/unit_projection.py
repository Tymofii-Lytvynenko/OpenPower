from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from src.client.controllers.camera_controller import CameraController


@dataclass(frozen=True)
class RegionAnchor:
    region_id: int
    center_x: float
    center_y: float
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
    stack_index: int = 0
    stack_count: int = 1

    def contains(self, screen_x: float, screen_y: float) -> bool:
        half_w = self.width * 0.5
        half_h = self.height * 0.5
        return (
            self.screen_x - half_w <= screen_x <= self.screen_x + half_w
            and self.screen_y - half_h <= screen_y <= self.screen_y + half_h
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
        surface_offset: float = 0.018,
    ):
        self.camera = camera
        self.map_width = max(1, int(map_width))
        self.map_height = max(1, int(map_height))
        self.globe_radius = float(globe_radius)
        self.surface_radius = float(globe_radius + surface_offset)

    def project_units(
        self,
        unit_rows: list[dict],
        region_lookup: dict[int, RegionAnchor],
        window_width: int,
        window_height: int,
    ) -> list[ProjectedUnit]:
        if window_width <= 0 or window_height <= 0:
            return []

        self.camera.update_matrices(window_width, window_height)
        vp_matrix, model_matrix = self.camera.get_cached_matrices()
        if vp_matrix is None or model_matrix is None:
            return []

        projected = []
        camera_pos = np.array([0.0, 0.0, self.camera.distance], dtype=np.float32)

        for row in unit_rows:
            unit = self._project_unit(row, region_lookup, vp_matrix, model_matrix, camera_pos, window_width, window_height)
            if unit is not None:
                projected.append(unit)

        projected.sort(key=lambda unit: unit.distance_to_camera, reverse=True)
        self._apply_stack_offsets(projected)
        return projected

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

        source = region_lookup.get(source_region_id) or region_lookup.get(current_region_id)
        if source is None:
            return None

        source_vec = self._anchor_to_unit_vector(source)
        if target_region_id <= 0 or progress <= 0.0:
            return source_vec * self.surface_radius

        target = region_lookup.get(target_region_id)
        if target is None:
            return source_vec * self.surface_radius

        target_vec = self._anchor_to_unit_vector(target)
        return self._slerp(source_vec, target_vec, progress) * self.surface_radius

    def _anchor_to_unit_vector(self, anchor: RegionAnchor) -> np.ndarray:
        u = anchor.center_x / self.map_width
        v = anchor.center_y / self.map_height
        lon = u * (2.0 * np.pi)
        lat = (0.5 - v) * np.pi

        x = np.cos(lat) * np.cos(lon)
        y = np.sin(lat)
        z = np.cos(lat) * np.sin(lon)
        return np.array([x, y, z], dtype=np.float32)

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
        width = 34.0 + max(0.0, min(1.0, zoom)) * 18.0
        return width, width * 0.68

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
