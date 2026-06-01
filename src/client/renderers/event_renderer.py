from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import numpy as np
from imgui_bundle import imgui

from src.client.controllers.camera_controller import CameraController
from src.client.ui.core.theme import GAMETHEME
from src.core.map.geo import EquirectangularProjection, GeoCoordinate, MapPixelCoordinate

if TYPE_CHECKING:
    from src.shared.state import GameState


# ── Visual constants ───────────────────────────────────────────
_PLACARD_PADDING_H = 8.0
_PLACARD_PADDING_V = 5.0
_PLACARD_ROUNDING = 4.0
_PLACARD_VERTICAL_OFFSET = -28.0  # pixels above the region center

# Map event_type → accent color (RGBA float tuples)
_EVENT_COLORS: dict[str, tuple[float, float, float, float]] = {
    "earthquake":        (0.95, 0.55, 0.15, 1.0),   # orange
    "flood":             (0.20, 0.60, 0.95, 1.0),   # blue
    "wildfire":          (1.00, 0.30, 0.18, 1.0),   # red-orange
    "tornado":           (0.60, 0.60, 0.70, 1.0),   # steel grey
    "volcanic_eruption": (0.85, 0.20, 0.15, 1.0),   # dark red
    "drought":           (0.92, 0.78, 0.22, 1.0),   # gold
    "epidemic":          (0.55, 0.90, 0.25, 1.0),   # lime green
    "economic_boom":     (0.30, 0.95, 0.60, 1.0),   # emerald
    "strike":            (0.95, 0.70, 0.20, 1.0),   # amber
    "tsunami":           (0.15, 0.45, 0.85, 1.0),   # deep blue
}
_DEFAULT_COLOR = (0.80, 0.80, 0.80, 1.0)


class EventRenderer:
    """
    Draws small event placards on the 3D globe as an ImGui overlay.

    Each placard floats above the center of its region, using the same
    globe → screen projection math as ``UnitRenderer`` to ensure correct
    tracking during orbit, zoom, and rotation.
    """

    def __init__(
        self,
        camera: CameraController,
        map_width: int,
        map_height: int,
        globe_radius: float,
    ):
        self._camera = camera
        self._globe_radius = float(globe_radius)
        self._geo = EquirectangularProjection(map_width, map_height)
        self._map_width = map_width
        self._map_height = map_height

        # Cache region center lookups {region_id: GeoCoordinate}
        self._region_geo_cache: dict[int, GeoCoordinate] = {}
        self._region_cache_size: int = -1

    # ── Public API ────────────────────────────────────────────

    def render(self, state: Optional["GameState"]) -> None:
        if state is None:
            return

        active_events: list[dict] = state.globals.get("active_events", [])
        if not active_events:
            return

        self._refresh_region_cache(state)

        window = imgui.get_io().display_size
        w = int(window.x)
        h = int(window.y)

        if w <= 0 or h <= 0:
            return

        self._camera.update_matrices(w, h)
        vp_matrix, model_matrix = self._camera.get_cached_matrices()
        if vp_matrix is None or model_matrix is None:
            return

        camera_pos = np.array([0.0, 0.0, self._camera.distance], dtype=np.float32)
        mvp_matrix = vp_matrix @ model_matrix

        # Collect visible placards
        placards: list[tuple[float, float, str, str, float]] = []
        for event_data in active_events:
            result = self._project_event(
                event_data, model_matrix, mvp_matrix, camera_pos, w, h
            )
            if result is not None:
                placards.append(result)

        if not placards:
            return

        # Draw all placards in a single fullscreen ImGui overlay
        flags = (
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_background
            | imgui.WindowFlags_.no_inputs
        )
        for flag_name in ("no_saved_settings", "no_focus_on_appearing", "no_nav"):
            flags |= getattr(imgui.WindowFlags_, flag_name, 0)

        imgui.set_next_window_pos((0, 0))
        imgui.set_next_window_size((float(w), float(h)))

        if imgui.begin("##EventOverlay", None, flags)[0]:
            draw_list = imgui.get_window_draw_list()
            for sx, sy, label, event_type, severity in placards:
                self._draw_placard(draw_list, sx, sy, label, event_type, severity, h)
        imgui.end()

    # ── Projection ────────────────────────────────────────────

    def _project_event(
        self,
        event_data: dict,
        model_matrix: np.ndarray,
        mvp_matrix: np.ndarray,
        camera_pos: np.ndarray,
        window_width: int,
        window_height: int,
    ) -> tuple[float, float, str, str, float] | None:
        region_id = int(event_data.get("region_id", 0))
        geo = self._region_geo_cache.get(region_id)
        if geo is None:
            return None

        # Geo → unit vector → local 3D position on the globe surface
        ux, uy, uz = self._geo.geo_to_unit_vector(geo)
        local = np.array(
            [ux * self._globe_radius, uy * self._globe_radius, uz * self._globe_radius, 1.0],
            dtype=np.float32,
        )

        # Back-face test: is this point facing the camera?
        world = model_matrix @ local
        normal = world[:3].copy()
        norm_len = float(np.linalg.norm(normal))
        if norm_len > 1e-6:
            normal /= norm_len
        view_dir = camera_pos - world[:3]
        if float(np.dot(normal, view_dir)) < -0.02:
            return None

        # Clip space
        clip = mvp_matrix @ local
        clip_w = float(clip[3])
        if abs(clip_w) < 1e-6:
            return None

        ndc = clip[:3] / clip_w
        if ndc[0] < -1.2 or ndc[0] > 1.2 or ndc[1] < -1.2 or ndc[1] > 1.2:
            return None

        sx = (float(ndc[0]) * 0.5 + 0.5) * window_width
        sy = (float(ndc[1]) * 0.5 + 0.5) * window_height

        label = str(event_data.get("label", "Event"))
        event_type = str(event_data.get("event_type", ""))
        severity = float(event_data.get("severity", 0.5))

        return sx, sy, label, event_type, severity

    # ── Drawing ───────────────────────────────────────────────

    def _draw_placard(
        self,
        draw_list: imgui.ImDrawList,
        screen_x: float,
        screen_y: float,
        label: str,
        event_type: str,
        severity: float,
        window_height: int,
    ) -> None:
        # Convert from bottom-left origin (GL) to top-left origin (ImGui)
        draw_y = window_height - screen_y + _PLACARD_VERTICAL_OFFSET

        text_size = imgui.calc_text_size(label)
        half_w = text_size.x * 0.5 + _PLACARD_PADDING_H
        half_h = text_size.y * 0.5 + _PLACARD_PADDING_V

        left = screen_x - half_w
        top = draw_y - half_h
        right = screen_x + half_w
        bottom = draw_y + half_h

        accent = _EVENT_COLORS.get(event_type, _DEFAULT_COLOR)

        # Background — semi-transparent dark panel
        bg_alpha = 0.78 + severity * 0.12
        draw_list.add_rect_filled(
            (left, top),
            (right, bottom),
            imgui.get_color_u32((0.04, 0.04, 0.06, bg_alpha)),
            _PLACARD_ROUNDING,
        )

        # Accent border
        draw_list.add_rect(
            (left, top),
            (right, bottom),
            imgui.get_color_u32(accent),
            _PLACARD_ROUNDING,
            0,
            1.4,
        )

        # Thin severity indicator bar along the bottom
        bar_width = (right - left - 4.0) * severity
        draw_list.add_rect_filled(
            (left + 2.0, bottom - 3.0),
            (left + 2.0 + bar_width, bottom - 1.0),
            imgui.get_color_u32(accent),
            1.0,
        )

        # Label text (centered)
        text_x = screen_x - text_size.x * 0.5
        text_y = draw_y - text_size.y * 0.5
        draw_list.add_text(
            (text_x, text_y),
            imgui.get_color_u32(GAMETHEME.colors.text_main),
            label,
        )

        # Small downward pointer triangle connecting placard to region
        tri_half = 5.0
        draw_list.add_triangle_filled(
            (screen_x - tri_half, bottom),
            (screen_x + tri_half, bottom),
            (screen_x, bottom + 8.0),
            imgui.get_color_u32((0.04, 0.04, 0.06, bg_alpha)),
        )

    # ── Region cache ──────────────────────────────────────────

    def _refresh_region_cache(self, state: "GameState") -> None:
        """
        Rebuild the region_id → GeoCoordinate lookup when the regions
        table changes (lazily, based on row count).
        """
        if "regions" not in state.tables:
            return

        regions = state.tables["regions"]
        if regions.height == self._region_cache_size and self._region_geo_cache:
            return

        cache: dict[int, GeoCoordinate] = {}
        has_geo = {"latitude", "longitude"}.issubset(set(regions.columns))
        has_pixel = {"center_x", "center_y"}.issubset(set(regions.columns))

        if not has_geo and not has_pixel:
            return

        for row in regions.iter_rows(named=True):
            rid = int(row["id"])
            if has_geo:
                cache[rid] = GeoCoordinate(
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                )
            elif has_pixel:
                cache[rid] = self._geo.pixel_to_geo(
                    MapPixelCoordinate(float(row["center_x"]), float(row["center_y"]))
                )

        self._region_geo_cache = cache
        self._region_cache_size = regions.height
