"""Shared geographic projection boundary for presentation-only globe overlays."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

import numpy as np

from src.client.controllers.camera_controller import CameraController
from src.core.map.geo import EquirectangularProjection, GeoCoordinate


@dataclass(frozen=True, slots=True)
class ProjectedSurfacePoint:
    """A front-facing geographic point in OpenGL screen coordinates.

    ``screen_y`` uses the existing renderer convention (bottom-left origin).
    ImGui callers convert it to top-left coordinates at their drawing boundary.
    """

    latitude: float
    longitude: float
    screen_x: float
    screen_y: float
    depth: float
    marker_radius: float
    silhouette_clearance: float
    front_facing: bool = True

    @property
    def marker_size(self) -> float:
        return self.marker_radius * 2.0

    @property
    def is_front_facing(self) -> bool:
        return self.front_facing

    @property
    def screen_position(self) -> tuple[float, float]:
        return self.screen_x, self.screen_y


class GlobeOverlayProjection:
    """Project geographic anchors using the same camera matrices as the globe."""

    def __init__(
        self,
        camera: CameraController,
        map_width: int,
        map_height: int,
        globe_radius: float,
        *,
        min_marker_radius: float = 4.0,
        max_marker_radius: float = 12.0,
    ) -> None:
        self.camera = camera
        self.globe_radius = max(float(globe_radius), 1.0e-6)
        self._geo = EquirectangularProjection(map_width, map_height)
        self.min_marker_radius = float(min_marker_radius)
        self.max_marker_radius = max(float(max_marker_radius), self.min_marker_radius)
        self._frame_key: tuple[object, ...] | None = None
        self._vp_matrix: np.ndarray | None = None
        self._model_matrix: np.ndarray | None = None
        self._mvp_matrix: np.ndarray | None = None
        self._camera_position: np.ndarray | None = None

    def prepare(self, window_width: int, window_height: int) -> bool:
        """Cache camera matrices once for a frame containing many anchors."""

        if window_width <= 0 or window_height <= 0:
            return False
        frame_key = (
            int(window_width),
            int(window_height),
            float(self.camera.yaw),
            float(self.camera.pitch),
            float(self.camera.distance),
            float(self.camera.fov_deg),
            float(self.camera.near),
            float(self.camera.far),
            tuple(float(value) for value in self.camera.target),
        )
        if frame_key == self._frame_key and self._mvp_matrix is not None:
            return True
        self.camera.update_matrices(int(window_width), int(window_height))
        vp_matrix, model_matrix = self.camera.get_cached_matrices()
        if vp_matrix is None or model_matrix is None:
            self._frame_key = None
            return False
        self._frame_key = frame_key
        self._vp_matrix = vp_matrix
        self._model_matrix = model_matrix
        self._mvp_matrix = vp_matrix @ model_matrix
        self._camera_position = np.array(
            [0.0, 0.0, float(self.camera.distance)], dtype=np.float32
        )
        return True

    def project_anchor(
        self,
        latitude: float,
        longitude: float,
        window_width: int,
        window_height: int,
        *,
        marker_radius: float = 7.0,
    ) -> Optional[ProjectedSurfacePoint]:
        """Return a bounded front-facing point, or ``None`` when it is hidden."""

        if window_width <= 0 or window_height <= 0:
            return None
        try:
            latitude_value = float(latitude)
            longitude_value = float(longitude)
        except (TypeError, ValueError):
            return None
        if not (
            math.isfinite(latitude_value)
            and math.isfinite(longitude_value)
            and -90.0 <= latitude_value <= 90.0
            and -180.0 <= longitude_value <= 180.0
        ):
            return None

        if not self.prepare(int(window_width), int(window_height)):
            return None
        model_matrix = self._model_matrix
        mvp_matrix = self._mvp_matrix
        camera_position = self._camera_position
        if model_matrix is None or mvp_matrix is None or camera_position is None:
            return None

        ux, uy, uz = self._geo.geo_to_unit_vector(
            GeoCoordinate(latitude_value, longitude_value)
        )
        local = np.array(
            [ux * self.globe_radius, uy * self.globe_radius, uz * self.globe_radius, 1.0],
            dtype=np.float32,
        )
        world = model_matrix @ local
        normal = world[:3].astype(np.float32, copy=True)
        normal_length = float(np.linalg.norm(normal))
        if normal_length <= 1.0e-6:
            return None
        normal /= normal_length
        view_direction = camera_position - world[:3]
        if float(np.dot(normal, view_direction)) < -0.02:
            return None

        clip = mvp_matrix @ local
        clip_w = float(clip[3])
        if abs(clip_w) <= 1.0e-6:
            return None
        ndc = clip[:3] / clip_w
        if not (
            math.isfinite(float(ndc[0]))
            and math.isfinite(float(ndc[1]))
            and -1.2 <= float(ndc[0]) <= 1.2
            and -1.2 <= float(ndc[1]) <= 1.2
        ):
            return None

        screen_x = (float(ndc[0]) * 0.5 + 0.5) * float(window_width)
        screen_y = (float(ndc[1]) * 0.5 + 0.5) * float(window_height)
        clearance = self._silhouette_clearance(screen_x, screen_y, window_width, window_height)
        bounded_radius = max(
            self.min_marker_radius,
            min(self.max_marker_radius, float(marker_radius)),
        )
        return ProjectedSurfacePoint(
            latitude=latitude_value,
            longitude=longitude_value,
            screen_x=screen_x,
            screen_y=screen_y,
            depth=float(ndc[2]),
            marker_radius=bounded_radius,
            silhouette_clearance=clearance,
            front_facing=True,
        )

    def project_anchors(
        self,
        anchors: list[tuple[float, float]],
        window_width: int,
        window_height: int,
        *,
        marker_radius: float = 7.0,
    ) -> list[ProjectedSurfacePoint | None]:
        """Project a batch without allocating camera matrices per anchor."""

        if not anchors or not self.prepare(int(window_width), int(window_height)):
            return [None for _ in anchors]
        model_matrix = self._model_matrix
        mvp_matrix = self._mvp_matrix
        camera_position = self._camera_position
        if model_matrix is None or mvp_matrix is None or camera_position is None:
            return [None for _ in anchors]

        values = np.asarray(anchors, dtype=np.float32)
        latitudes = values[:, 0]
        longitudes = values[:, 1]
        valid = (
            np.isfinite(latitudes)
            & np.isfinite(longitudes)
            & (latitudes >= -90.0)
            & (latitudes <= 90.0)
            & (longitudes >= -180.0)
            & (longitudes <= 180.0)
        )
        safe_latitudes = np.clip(latitudes, -90.0, 90.0)
        normalized_longitudes = (longitudes + 180.0) % 360.0 - 180.0
        latitudes_radians = np.radians(safe_latitudes)
        longitudes_radians = np.radians(normalized_longitudes + 180.0)
        cos_latitudes = np.cos(latitudes_radians)
        local = np.column_stack(
            (
                cos_latitudes * np.cos(longitudes_radians) * self.globe_radius,
                -np.sin(latitudes_radians) * self.globe_radius,
                cos_latitudes * np.sin(longitudes_radians) * self.globe_radius,
                np.ones(len(anchors), dtype=np.float32),
            )
        ).astype(np.float32, copy=False)
        world = local @ model_matrix.T
        normals = world[:, :3]
        normal_lengths = np.linalg.norm(normals, axis=1)
        safe_lengths = np.maximum(normal_lengths, 1.0e-6)
        normals = normals / safe_lengths[:, None]
        view_directions = camera_position[None, :] - world[:, :3]
        front_facing = np.sum(normals * view_directions, axis=1) >= -0.02

        clip = local @ mvp_matrix.T
        clip_w = clip[:, 3]
        safe_w = np.where(np.abs(clip_w) > 1.0e-6, clip_w, 1.0)
        ndc = clip[:, :3] / safe_w[:, None]
        finite_screen = np.isfinite(ndc[:, 0]) & np.isfinite(ndc[:, 1])
        in_frame = (
            (ndc[:, 0] >= -1.2)
            & (ndc[:, 0] <= 1.2)
            & (ndc[:, 1] >= -1.2)
            & (ndc[:, 1] <= 1.2)
        )
        visible = valid & front_facing & finite_screen & in_frame & (np.abs(clip_w) > 1.0e-6)
        screen_x = (ndc[:, 0] * 0.5 + 0.5) * float(window_width)
        screen_y = (ndc[:, 1] * 0.5 + 0.5) * float(window_height)
        limb_radius = self._projected_limb_radius(window_height)
        distance = np.hypot(screen_x - float(window_width) * 0.5, screen_y - float(window_height) * 0.5)
        clearance = np.maximum(0.0, limb_radius - distance)
        bounded_radius = max(self.min_marker_radius, min(self.max_marker_radius, float(marker_radius)))

        result: list[ProjectedSurfacePoint | None] = []
        for index, (latitude, longitude) in enumerate(anchors):
            if not bool(visible[index]):
                result.append(None)
                continue
            result.append(
                ProjectedSurfacePoint(
                    latitude=float(latitude),
                    longitude=float(longitude),
                    screen_x=float(screen_x[index]),
                    screen_y=float(screen_y[index]),
                    depth=float(ndc[index, 2]),
                    marker_radius=bounded_radius,
                    silhouette_clearance=float(clearance[index]),
                    front_facing=True,
                )
            )
        return result

    def _silhouette_clearance(
        self,
        screen_x: float,
        screen_y: float,
        window_width: int,
        window_height: int,
    ) -> float:
        """Approximate distance from the point to the projected sphere limb.

        The camera is centered on the spherical globe, so the projected limb is
        a screen-space circle.  The analytic radius avoids per-anchor sampling
        and keeps decorative culling predictable during camera motion.
        """

        center_x = float(window_width) * 0.5
        center_y = float(window_height) * 0.5
        distance = math.hypot(screen_x - center_x, screen_y - center_y)
        return max(0.0, self._projected_limb_radius(window_height) - distance)

    def _projected_limb_radius(self, window_height: int) -> float:
        focal_y = float(window_height) / (2.0 * math.tan(math.radians(self.camera.fov_deg) * 0.5))
        radius_squared = float(self.camera.distance) ** 2 - self.globe_radius ** 2
        if radius_squared <= 1.0e-9:
            return 0.0
        return focal_y * self.globe_radius / math.sqrt(radius_squared)


def project_surface_anchor(
    projection: GlobeOverlayProjection,
    latitude: float,
    longitude: float,
    window_width: int,
    window_height: int,
    *,
    marker_radius: float = 7.0,
) -> Optional[ProjectedSurfacePoint]:
    """Functional adapter useful for lightweight tests and renderers."""

    return projection.project_anchor(
        latitude,
        longitude,
        window_width,
        window_height,
        marker_radius=marker_radius,
    )
