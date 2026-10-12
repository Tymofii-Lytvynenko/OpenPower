from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Optional, TYPE_CHECKING

from src.client.ui.core.instrumented_imgui import imgui

from src.client.controllers.camera_controller import CameraController
from src.client.renderers.unit_batch_renderer import UnitBatchRenderer
from src.client.renderers.unit_flag_atlas import UnitFlagAtlas
from src.client.renderers.globe_overlay_projection import GlobeOverlayProjection
from src.client.renderers.unit_projection import (
    PreparedUnitProjectionData,
    ProjectedUnit,
    RegionAnchor,
    UnitProjectionService,
)
from src.client.renderers.unit_route_overlay import (
    UnitRouteOverlay,
    sample_route_waypoints,
    selected_unit_route_overlays,
)
from src.client.ui.core.primitives import UIPrimitives, UnitCompositionRow
from src.client.ui.core.theme import GAMETHEME
from src.core.map.geo import EquirectangularProjection, GeoCoordinate, MapPixelCoordinate
from src.core.map.engagement_geometry import EARTH_RADIUS_KM, ENGAGEMENT_RADIUS_KM

if TYPE_CHECKING:
    from src.shared.state import GameState


UNIT_DRAG_PREVIEW_WIDTH = 22.0
UNIT_DRAG_PREVIEW_HEIGHT = 15.0
UNIT_COMPOSITION_PLATE_WIDTH = 118.0
UNIT_COMPOSITION_PLATE_HEIGHT = 58.0
ENGAGEMENT_ZONE_SEGMENTS = 32
MAX_SELECTED_ENGAGEMENT_ZONES = 32
UNIT_SIGNATURE_COLUMNS = (
    "id",
    "owner",
    "unit_type",
    "strength",
    "current_region_id",
    "latitude",
    "longitude",
    "source_region_id",
    "source_latitude",
    "source_longitude",
    "target_region_id",
    "target_latitude",
    "target_longitude",
    "departed_at_minute",
    "arrival_at_minute",
    "movement_progress",
    "is_moving",
    "readiness_status",
    "readiness_progress",
    "readiness_transition_id",
)


@dataclass(frozen=True)
class UnitDragPreview:
    unit_id: str
    owner: str
    origin_x: float
    origin_y: float
    mouse_x: float
    mouse_y: float


class UnitRenderer:
    """
    Draws unit billboards as an ImGui overlay projected from globe coordinates.
    The globe remains the depth-tested 3D layer; units are readable screen-space marks.
    """

    def __init__(
        self,
        camera: CameraController,
        map_width: int,
        map_height: int,
        globe_radius: float,
    ):
        self._projection = UnitProjectionService(camera, map_width, map_height, globe_radius)
        self._route_projection = GlobeOverlayProjection(camera, map_width, map_height, globe_radius)
        self._camera = camera
        self._geo_projection = EquirectangularProjection(map_width, map_height)
        self._flags = UnitFlagAtlas()
        self._batch = UnitBatchRenderer()
        self._region_lookup: dict[int, RegionAnchor] = {}
        self._region_count = -1
        self._billboards: list[ProjectedUnit] = []
        self._projection_cache_key: tuple | None = None
        self._prepared_units = PreparedUnitProjectionData.empty()
        self._prepared_units_key: tuple | None = None
        self._last_state_id: int | None = None
        self._last_units_signature: tuple | None = None
        self._last_units_revision: int | None = None
        self._flag_units_signature: tuple | None = None
        self._flag_owners: frozenset[str] = frozenset()
        self._filtered_units_cache_key: tuple | None = None
        self._filtered_units_cache: Any = None
        self._route_overlay_cache_key: tuple | None = None
        self._route_overlay_cache: list[UnitRouteOverlay] = []

    @property
    def billboards(self) -> list[ProjectedUnit]:
        return self._billboards

    def render(
        self,
        state: Optional["GameState"],
        selected_unit_id: Optional[str],
        selected_unit_ids: Optional[set[str]],
        hovered_unit_id: Optional[str],
        drag_preview: Optional[UnitDragPreview],
        selection_rect: Optional[tuple[float, float, float, float]] = None,
        visible_owners: Optional[set[str]] = None,
        show_engagement_zones: bool = True,
        presentation_total_minutes: float | None = None,
        viewer_country_tag: str | None = None,
    ) -> None:
        window = imgui.get_io().display_size
        width = int(window.x)
        height = int(window.y)
        filtered_units = self._get_filtered_units(state, visible_owners)
        units_signature = self._get_units_signature(state, filtered_units, visible_owners)

        self._prepare_flag_atlas_for_state(filtered_units, drag_preview, units_signature)
        self._billboards = self._project_units(
            state,
            filtered_units,
            width,
            height,
            units_signature,
            presentation_total_minutes,
        )
        selected_ids = {str(unit_id) for unit_id in (selected_unit_ids or ())}
        if selected_unit_id:
            selected_ids.add(str(selected_unit_id))
        ordered_selected_ids = (
            ([str(selected_unit_id)] if selected_unit_id else [])
            + sorted(selected_ids - ({str(selected_unit_id)} if selected_unit_id else set()))
        )
        route_overlays = self._get_selected_route_overlays(state, ordered_selected_ids, viewer_country_tag)
        batch_drawn = self._batch.render(self._billboards, self._flags, width, height)
        has_zone_targets = show_engagement_zones and any(
            unit.unit_id == selected_unit_id
            or (selected_unit_ids is not None and unit.unit_id in selected_unit_ids)
            or unit.unit_id == hovered_unit_id
            for unit in self._billboards
        )
        needs_imgui_overlay = (
            not batch_drawn
            or has_zone_targets
            or drag_preview is not None
            or selection_rect is not None
            or bool(route_overlays)
            or any(
                self._unit_needs_imgui_overlay(unit, selected_unit_id, selected_unit_ids, hovered_unit_id)
                for unit in self._billboards
            )
        )
        if not needs_imgui_overlay:
            return

        flags = (
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_background
            | imgui.WindowFlags_.no_inputs
        )
        for optional_flag in ("no_saved_settings", "no_focus_on_appearing", "no_nav"):
            flags |= getattr(imgui.WindowFlags_, optional_flag, 0)
        imgui.set_next_window_pos((0, 0))
        imgui.set_next_window_size((float(width), float(height)))

        if imgui.begin("##UnitOverlay", None, flags)[0]:
            draw_list = imgui.get_window_draw_list()
            self._draw_selected_routes(draw_list, route_overlays, width, height)
            if show_engagement_zones:
                self._draw_engagement_zones(
                    draw_list,
                    width,
                    height,
                    selected_unit_id,
                    selected_unit_ids,
                    hovered_unit_id,
                )
            for unit in self._billboards:
                if batch_drawn:
                    self._draw_unit_overlay(
                        draw_list,
                        unit,
                        width,
                        height,
                        selected_unit_id,
                        selected_unit_ids,
                        hovered_unit_id,
                    )
                else:
                    self._draw_unit(
                        draw_list,
                        unit,
                        width,
                        height,
                        selected_unit_id,
                        selected_unit_ids,
                        hovered_unit_id,
                    )

            if drag_preview is not None:
                self._draw_drag_preview(draw_list, drag_preview, height)

            if selection_rect is not None:
                self._draw_selection_rect(draw_list, selection_rect, height)

        imgui.end()

    def _get_selected_route_overlays(
        self,
        state: Optional["GameState"],
        selected_ids: list[str],
        viewer_country_tag: str | None,
    ) -> list[UnitRouteOverlay]:
        revisions = getattr(state, "table_revisions", {}) if state is not None else {}
        revision_names = (
            "units",
            "unit_movement_routes",
            "regions",
            "countries_treaties",
            "countries_wars",
        )
        cache_key = (
            tuple(selected_ids),
            str(viewer_country_tag or "").strip().upper(),
            tuple((name, int(revisions.get(name, 0))) for name in revision_names),
        )
        if cache_key != self._route_overlay_cache_key:
            self._route_overlay_cache = selected_unit_route_overlays(
                state,
                selected_ids,
                viewer_country_tag,
            )
            self._route_overlay_cache_key = cache_key
        return self._route_overlay_cache

    def _draw_selected_routes(
        self,
        draw_list: Any,
        overlays: list[UnitRouteOverlay],
        window_width: int,
        window_height: int,
    ) -> None:
        for overlay in overlays:
            samples = sample_route_waypoints(overlay.waypoints)
            geographic_points = [(point.latitude, point.longitude) for point in samples]
            projected = self._route_projection.project_anchors(
                geographic_points,
                window_width,
                window_height,
            )
            visible: list[tuple[int, float, float]] = []
            previous: tuple[float, float] | None = None
            for index, point in enumerate(projected):
                if point is None:
                    previous = None
                    continue
                screen_point = (point.screen_x, window_height - point.screen_y)
                visible.append((index, *screen_point))
                if previous is not None:
                    self._draw_route_segment(
                        draw_list,
                        previous,
                        screen_point,
                        overlay.color,
                        overlay.dash_lengths,
                    )
                previous = screen_point

            if visible:
                label_index = min(2, len(visible) - 1)
                _, anchor_x, anchor_y = visible[label_index]
                label = overlay.label if overlay.status_label == "In transit" else f"{overlay.label} · {overlay.status_label}"
                label_size = imgui.calc_text_size(label)
                label_x = anchor_x + 8.0
                label_y = anchor_y - float(label_size.y) - 5.0
                draw_list.add_rect_filled(
                    (label_x - 4.0, label_y - 2.0),
                    (label_x + float(label_size.x) + 4.0, label_y + float(label_size.y) + 2.0),
                    imgui.get_color_u32((0.03, 0.04, 0.06, 0.82)),
                    3.0,
                )
                draw_list.add_text(
                    (label_x, label_y),
                    imgui.get_color_u32(overlay.color),
                    label,
                )

    def _draw_route_segment(
        self,
        draw_list: Any,
        start: tuple[float, float],
        end: tuple[float, float],
        color: tuple[float, float, float, float],
        dash_lengths: tuple[float, float] | None,
    ) -> None:
        color_u32 = imgui.get_color_u32(color)
        if dash_lengths is None:
            draw_list.add_line(start, end, color_u32, 2.5)
            return

        delta_x = end[0] - start[0]
        delta_y = end[1] - start[1]
        segment_length = math.hypot(delta_x, delta_y)
        if segment_length <= 1e-6:
            return
        dash_length, gap_length = dash_lengths
        cursor = 0.0
        while cursor < segment_length:
            dash_end = min(segment_length, cursor + dash_length)
            start_fraction = cursor / segment_length
            end_fraction = dash_end / segment_length
            draw_list.add_line(
                (start[0] + delta_x * start_fraction, start[1] + delta_y * start_fraction),
                (start[0] + delta_x * end_fraction, start[1] + delta_y * end_fraction),
                color_u32,
                2.5,
            )
            cursor = dash_end + gap_length

    def get_unit_at(self, screen_x: float, screen_y: float) -> Optional[ProjectedUnit]:
        for unit in reversed(self._billboards):
            if unit.contains(screen_x, screen_y):
                return unit
        return None

    def get_unit(self, unit_id: str) -> Optional[ProjectedUnit]:
        for unit in self._billboards:
            if unit.unit_id == unit_id:
                return unit
        return None

    def _project_units(
        self,
        state: Optional["GameState"],
        filtered_units: Any,
        window_width: int,
        window_height: int,
        units_signature: tuple | None,
        presentation_total_minutes: float | None = None,
    ) -> list[ProjectedUnit]:
        if state is None or filtered_units is None:
            self._projection_cache_key = None
            self._prepared_units_key = None
            self._prepared_units = PreparedUnitProjectionData.empty()
            return []

        if filtered_units.is_empty():
            self._projection_cache_key = None
            self._prepared_units_key = None
            self._prepared_units = PreparedUnitProjectionData.empty()
            return []

        self._refresh_region_lookup(state)
        cache_key = self._make_projection_cache_key(
            units_signature,
            window_width,
            window_height,
            presentation_total_minutes,
        )
        if cache_key == self._projection_cache_key:
            return self._billboards

        current_minute = presentation_total_minutes
        if current_minute is None and state is not None:
            current_minute = float(state.time.total_minutes)
        transitions = state.tables.get("unit_readiness_transitions") if state is not None else None
        transition_rows = transitions.to_dicts() if transitions is not None and not transitions.is_empty() else []
        prepared = self._get_prepared_units(
            filtered_units,
            units_signature,
            transition_rows,
            current_minute,
        )
        self._projection_cache_key = cache_key
        return self._projection.project_prepared_units(
            prepared,
            window_width,
            window_height,
            presentation_total_minutes,
        )

    def _make_projection_cache_key(
        self,
        units_signature: tuple | None,
        window_width: int,
        window_height: int,
        presentation_total_minutes: float | None = None,
    ) -> tuple:
        return (
            units_signature,
            window_width,
            window_height,
            round(self._camera.yaw, 6),
            round(self._camera.pitch, 6),
            round(self._camera.distance, 4),
            self._region_count,
            None if presentation_total_minutes is None else round(presentation_total_minutes, 5),
        )

    def _get_prepared_units(
        self,
        units,
        units_signature: tuple | None,
        transition_rows: list[dict] | None = None,
        current_minute: float | None = None,
    ) -> PreparedUnitProjectionData:
        transition_by_unit = {
            str(row.get("unit_id") or ""): row
            for row in (transition_rows or [])
        }
        transition_signature = tuple(
            sorted(
                (
                    unit_id,
                    str(row.get("id") or ""),
                    str(row.get("target_status") or ""),
                    int(row.get("completes_at_minute") or 0),
                    float(row.get("progress") or 0.0),
                )
                for unit_id, row in transition_by_unit.items()
            )
        )
        display_minute = int(current_minute or 0)
        prepared_key = (units_signature, self._region_count, transition_signature, display_minute)
        if prepared_key == self._prepared_units_key:
            return self._prepared_units

        enriched_rows = []
        for row in units.to_dicts():
            enriched = dict(row)
            transition = transition_by_unit.get(str(row.get("id") or ""))
            if transition is not None:
                enriched["readiness_target"] = str(transition.get("target_status") or row.get("readiness_status") or "ready")
                enriched["readiness_eta_minute"] = int(
                    row.get("readiness_eta_minute")
                    or transition.get("completes_at_minute")
                    or 0
                )
                enriched["readiness_transition_id"] = str(
                    row.get("readiness_transition_id")
                    or transition.get("id")
                    or ""
                )
            enriched["current_game_minute"] = display_minute
            enriched_rows.append(enriched)
        self._prepared_units = self._projection.prepare_units(
            enriched_rows,
            self._region_lookup,
            current_game_minute=display_minute,
        )
        self._prepared_units_key = prepared_key
        return self._prepared_units

    def _get_filtered_units(self, state: Optional["GameState"], visible_owners: Optional[set[str]]):
        if state is None or "units" not in state.tables:
            return None
        units = state.tables["units"]
        revisions = getattr(state, "table_revisions", None)
        units_revision = int(revisions.get("units", 0)) if revisions is not None else None
        owners_hash = hash(frozenset(visible_owners)) if visible_owners is not None else 0
        cache_key = (id(units), units_revision, owners_hash)
        if cache_key == self._filtered_units_cache_key:
            return self._filtered_units_cache

        if units.is_empty():
            filtered = units
        elif "unit_lifecycle" in units.columns or (visible_owners is not None and "owner" in units.columns):
            import polars as pl
            filters = []
            if visible_owners is not None and "owner" in units.columns:
                filters.append(pl.col("owner").is_in(list(visible_owners)))
            if "unit_lifecycle" in units.columns:
                filters.append(~pl.col("unit_lifecycle").is_in([
                    "deployment_queued",
                    "deployment_transit",
                    "deployment_blocked",
                    "in_transit",
                    "route_blocked",
                    "training",
                ]))
            filtered = units.filter(pl.all_horizontal(filters))
        else:
            filtered = units

        self._filtered_units_cache_key = cache_key
        self._filtered_units_cache = filtered
        return filtered

    def _get_units_signature(
        self, 
        state: Optional["GameState"], 
        filtered_units: Any,
        visible_owners: Optional[set[str]],
    ) -> tuple | None:
        if state is None or filtered_units is None:
            self._last_state_id = None
            self._last_units_signature = None
            return None

        state_id = id(state)
        # Snapshot decoding replaces the GameState object, so revisions are a
        # more stable cache key than object identity when the authoritative
        # units table did not change.
        owners_hash = hash(frozenset(visible_owners)) if visible_owners is not None else 0
        revisions = getattr(state, "table_revisions", None)
        units_revision = int(revisions.get("units", 0)) if revisions is not None else None
        same_filter = owners_hash == getattr(self, "_last_owners_hash", None)
        same_units = units_revision is not None and units_revision == self._last_units_revision
        same_state = state_id == self._last_state_id
        if same_filter and (same_units or (units_revision is None and same_state)):
            return self._last_units_signature

        self._last_owners_hash = owners_hash
        units = filtered_units
        if units.is_empty():
            signature = ("empty", 0)
        else:
            columns = [column for column in UNIT_SIGNATURE_COLUMNS if column in units.columns]
            try:
                hashes = units.select(columns).hash_rows() if columns else None
                row_hash = (
                    int(hashes.sum()),
                    int(hashes.min()),
                    int(hashes.max()),
                ) if hashes is not None else (0, 0, 0)
            except Exception:
                tick = int(state.globals.get("tick", 0))
                row_hash = (tick, tick, tick)
            signature = (units.height, tuple(columns), row_hash)

        self._last_state_id = state_id
        self._last_units_revision = units_revision
        self._last_units_signature = signature
        return signature

    def _prepare_flag_atlas_for_state(
        self,
        filtered_units: Any,
        drag_preview: Optional[UnitDragPreview],
        units_signature: tuple | None,
    ) -> None:
        owners = set(self._flag_owners)
        if (
            filtered_units is not None
            and units_signature != self._flag_units_signature
        ):
            units = filtered_units
            if not units.is_empty() and "owner" in units.columns:
                self._flag_owners = frozenset(str(owner) for owner in units["owner"].unique().to_list())
                owners.update(self._flag_owners)
            else:
                self._flag_owners = frozenset()
            self._flag_units_signature = units_signature

        if drag_preview is not None:
            owners.add(drag_preview.owner)

        self._flags.ensure_owners(owners)

    def _draw_engagement_zones(
        self,
        draw_list: Any,
        window_width: int,
        window_height: int,
        selected_unit_id: Optional[str],
        selected_unit_ids: Optional[set[str]],
        hovered_unit_id: Optional[str],
    ) -> None:
        selected_ids = selected_unit_ids or set()
        units = [
            unit
            for unit in self._billboards
            if unit.unit_id == selected_unit_id
            or unit.unit_id in selected_ids
            or unit.unit_id == hovered_unit_id
        ]
        units = units[:MAX_SELECTED_ENGAGEMENT_ZONES]

        for unit in units:
            is_selected = unit.unit_id == selected_unit_id or (
                selected_unit_ids is not None and unit.unit_id in selected_unit_ids
            )
            fill_color = (0.95, 0.50, 0.16, 0.18) if is_selected else (0.30, 0.64, 0.96, 0.12)
            outline_color = (1.0, 0.68, 0.24, 0.92) if is_selected else (0.43, 0.76, 1.0, 0.72)
            ring = self._projection.project_surface_ring(
                unit.local_position,
                ENGAGEMENT_RADIUS_KM / EARTH_RADIUS_KM,
                window_width,
                window_height,
                ENGAGEMENT_ZONE_SEGMENTS,
            )
            visible_points = [imgui.ImVec2(*point) for point in ring if point is not None]
            if len(visible_points) == len(ring) and len(visible_points) >= 3:
                draw_list.add_convex_poly_filled(
                    visible_points,
                    imgui.get_color_u32(fill_color),
                )
                draw_list.add_polyline(
                    visible_points,
                    imgui.get_color_u32(outline_color),
                    imgui.ImDrawFlags_.closed,
                    1.25,
                )
                continue

            for index, point in enumerate(ring):
                next_point = ring[(index + 1) % len(ring)] if ring else None
                if point is not None and next_point is not None:
                    draw_list.add_line(
                        point,
                        next_point,
                        imgui.get_color_u32(outline_color),
                        1.25,
                    )

    def _unit_needs_imgui_overlay(
        self,
        unit: ProjectedUnit,
        selected_unit_id: Optional[str],
        selected_unit_ids: Optional[set[str]],
        hovered_unit_id: Optional[str],
    ) -> bool:
        return (
            unit.unit_id == selected_unit_id
            or (selected_unit_ids is not None and unit.unit_id in selected_unit_ids)
            or unit.unit_id == hovered_unit_id
            or unit.is_moving
            or bool(unit.readiness_transition_id)
            or (unit.stack_count > 1 and unit.stack_index == unit.stack_count - 1)
        )

    def _refresh_region_lookup(self, state: "GameState") -> None:
        if "regions" not in state.tables:
            self._region_lookup = {}
            self._region_count = -1
            return

        regions = state.tables["regions"]
        if regions.height == self._region_count and self._region_lookup:
            return

        required = {"id"}
        if regions.is_empty() or not required.issubset(set(regions.columns)):
            self._region_lookup = {}
            self._region_count = -1
            return

        owner_expr = "owner" if "owner" in regions.columns else None
        columns = ["id"]
        if {"latitude", "longitude"}.issubset(set(regions.columns)):
            columns.extend(["latitude", "longitude"])
        elif {"center_x", "center_y"}.issubset(set(regions.columns)):
            columns.extend(["center_x", "center_y"])
        else:
            self._region_lookup = {}
            self._region_count = -1
            return

        if owner_expr:
            columns.append(owner_expr)

        lookup = {}
        for row in regions.select(columns).iter_rows(named=True):
            region_id = int(row["id"])
            geo = self._row_to_geo(row)
            lookup[region_id] = RegionAnchor(
                region_id=region_id,
                geo=geo,
                owner=str(row.get("owner", "")),
            )

        self._region_lookup = lookup
        self._region_count = regions.height

    def _row_to_geo(self, row: dict) -> GeoCoordinate:
        if "latitude" in row and "longitude" in row:
            return GeoCoordinate(
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
            )

        return self._geo_projection.pixel_to_geo(
            MapPixelCoordinate(float(row["center_x"]), float(row["center_y"]))
        )

    def _draw_unit(
        self,
        draw_list: imgui.ImDrawList,
        unit: ProjectedUnit,
        window_width: int,
        window_height: int,
        selected_unit_id: Optional[str],
        selected_unit_ids: Optional[set[str]],
        hovered_unit_id: Optional[str],
    ) -> None:
        image_w = unit.width
        image_h = unit.height
        left = unit.screen_x - image_w * 0.5
        top = window_height - unit.screen_y - image_h * 0.5
        right = left + image_w
        bottom = top + image_h

        is_primary_selected = unit.unit_id == selected_unit_id
        is_selected = is_primary_selected or (selected_unit_ids is not None and unit.unit_id in selected_unit_ids)
        is_hovered = unit.unit_id == hovered_unit_id
        border_color = GAMETHEME.colors.warning if is_selected else GAMETHEME.colors.text_main
        if is_hovered and not is_selected:
            border_color = GAMETHEME.colors.info

        draw_list.add_rect_filled(
            (left - 3, top - 3),
            (right + 3, bottom + 3),
            imgui.get_color_u32((0.02, 0.02, 0.02, 0.72)),
            3.0,
        )

        if not self._flags.draw_flag(draw_list, unit.owner, left, top, right, bottom):
            draw_list.add_rect_filled(
                (left, top),
                (right, bottom),
                imgui.get_color_u32(GAMETHEME.colors.bg_input),
                2.0,
            )

        draw_list.add_rect(
            (left - 1, top - 1),
            (right + 1, bottom + 1),
            imgui.get_color_u32(border_color),
            3.0,
            0,
            1.5 if is_selected or is_hovered else 1.0,
        )

        if unit.is_moving:
            self._draw_progress_bar(draw_list, left, bottom + 4, image_w, unit.movement_progress)
        elif unit.readiness_transition_id:
            self._draw_progress_bar(draw_list, left, bottom + 4, image_w, unit.readiness_progress)
            if is_primary_selected or is_hovered:
                self._draw_readiness_label(draw_list, unit, left, bottom + 10)

        if unit.stack_count > 1 and unit.stack_index == unit.stack_count - 1:
            self._draw_stack_badge(
                draw_list,
                right - 3,
                top - 7,
                unit.stack_count,
                unit.stack_strength,
            )

        if is_primary_selected:
            self._draw_unit_composition_plate(draw_list, unit, right, top, window_width, window_height)

    def _draw_unit_overlay(
        self,
        draw_list: imgui.ImDrawList,
        unit: ProjectedUnit,
        window_width: int,
        window_height: int,
        selected_unit_id: Optional[str],
        selected_unit_ids: Optional[set[str]],
        hovered_unit_id: Optional[str],
    ) -> None:
        if not self._unit_needs_imgui_overlay(unit, selected_unit_id, selected_unit_ids, hovered_unit_id):
            return

        image_w = unit.width
        image_h = unit.height
        left = unit.screen_x - image_w * 0.5
        top = window_height - unit.screen_y - image_h * 0.5
        right = left + image_w
        bottom = top + image_h

        is_primary_selected = unit.unit_id == selected_unit_id
        is_selected = is_primary_selected or (selected_unit_ids is not None and unit.unit_id in selected_unit_ids)
        is_hovered = unit.unit_id == hovered_unit_id
        if is_selected or is_hovered:
            border_color = GAMETHEME.colors.warning if is_selected else GAMETHEME.colors.info
            draw_list.add_rect(
                (left - 1, top - 1),
                (right + 1, bottom + 1),
                imgui.get_color_u32(border_color),
                3.0,
                0,
                1.5 if is_selected else 1.0,
            )

        if unit.is_moving:
            self._draw_progress_bar(draw_list, left, bottom + 4, image_w, unit.movement_progress)
        elif unit.readiness_transition_id:
            self._draw_progress_bar(draw_list, left, bottom + 4, image_w, unit.readiness_progress)
            if is_primary_selected or is_hovered:
                self._draw_readiness_label(draw_list, unit, left, bottom + 10)

        if unit.stack_count > 1 and unit.stack_index == unit.stack_count - 1:
            self._draw_stack_badge(
                draw_list,
                right - 3,
                top - 7,
                unit.stack_count,
                unit.stack_strength,
            )

        if is_primary_selected:
            self._draw_unit_composition_plate(draw_list, unit, right, top, window_width, window_height)

    def _draw_selection_rect(
        self,
        draw_list: imgui.ImDrawList,
        rect: tuple[float, float, float, float],
        window_height: int,
    ) -> None:
        x1, y1, x2, y2 = rect
        left, right = sorted((x1, x2))
        bottom, top = sorted((y1, y2))
        draw_top = window_height - top
        draw_bottom = window_height - bottom

        draw_list.add_rect_filled(
            (left, draw_top),
            (right, draw_bottom),
            imgui.get_color_u32((0.25, 0.55, 0.95, 0.14)),
        )
        draw_list.add_rect(
            (left, draw_top),
            (right, draw_bottom),
            imgui.get_color_u32((0.45, 0.70, 1.00, 0.85)),
            0.0,
            0,
            1.2,
        )

    def _draw_unit_composition_plate(
        self,
        draw_list: imgui.ImDrawList,
        unit: ProjectedUnit,
        unit_right: float,
        unit_top: float,
        window_width: int,
        window_height: int,
    ) -> None:
        plate_x = unit_right + 7.0
        if plate_x + UNIT_COMPOSITION_PLATE_WIDTH > window_width - 4.0:
            plate_x = unit.screen_x - unit.width * 0.5 - UNIT_COMPOSITION_PLATE_WIDTH - 7.0

        plate_y = unit_top - 18.0
        plate_y = max(4.0, min(plate_y, window_height - UNIT_COMPOSITION_PLATE_HEIGHT - 4.0))

        UIPrimitives.unit_composition_plate(
            draw_list=draw_list,
            x=plate_x,
            y=plate_y,
            rows=self._unit_composition_rows(unit),
            max_value=unit.strength,
        )

    def _unit_composition_rows(self, unit: ProjectedUnit) -> tuple[UnitCompositionRow, ...]:
        infantry, ground, naval, air = self._classify_unit_strength(unit)
        return (
            UnitCompositionRow("I", infantry, (0.34, 0.78, 0.39, 1.0)),
            UnitCompositionRow("G", ground, (0.78, 0.30, 0.25, 1.0)),
            UnitCompositionRow("N", naval, (0.24, 0.50, 0.86, 1.0)),
            UnitCompositionRow("A", air, (0.86, 0.70, 0.28, 1.0)),
        )

    def _classify_unit_strength(self, unit: ProjectedUnit) -> tuple[int, int, int, int]:
        unit_type = unit.unit_type.casefold()
        strength = max(0, unit.strength)

        if any(token in unit_type for token in ("naval", "ship", "fleet")):
            return 0, 0, strength, 0
        if any(token in unit_type for token in ("air", "helicopter", "plane", "jet")):
            return 0, 0, 0, strength
        if any(token in unit_type for token in ("vehicle", "armor", "armour", "tank", "ground")):
            return 0, strength, 0, 0
        return strength, 0, 0, 0

    def _draw_progress_bar(
        self,
        draw_list: imgui.ImDrawList,
        left: float,
        top: float,
        width: float,
        progress: float,
    ) -> None:
        height = 4.0
        fraction = max(0.0, min(1.0, progress))
        draw_list.add_rect_filled(
            (left, top),
            (left + width, top + height),
            imgui.get_color_u32((0.02, 0.02, 0.02, 0.85)),
            2.0,
        )
        draw_list.add_rect_filled(
            (left, top),
            (left + width * fraction, top + height),
            imgui.get_color_u32(GAMETHEME.colors.military),
            2.0,
        )

    def _draw_readiness_label(
        self,
        draw_list: imgui.ImDrawList,
        unit: ProjectedUnit,
        left: float,
        top: float,
    ) -> None:
        target = unit.readiness_target.title()
        remaining = unit.readiness_remaining_label or "0h"
        draw_list.add_text(
            (left, top),
            imgui.get_color_u32(GAMETHEME.colors.text_main),
            f"{target} · {remaining}",
        )

    def _draw_stack_badge(
        self,
        draw_list: imgui.ImDrawList,
        x: float,
        y: float,
        count: int,
        total_strength: int,
    ) -> None:
        text = f"{count} · {total_strength:,}"
        text_size = imgui.calc_text_size(text)
        width = text_size.x + 10.0
        height = max(18.0, text_size.y + 6.0)
        left = x - width * 0.5
        top = y - height * 0.5
        right = left + width
        bottom = top + height
        rounding = height * 0.5
        # The original round count badge clipped combined strength labels at common sizes.
        draw_list.add_rect_filled(
            (left, top),
            (right, bottom),
            imgui.get_color_u32(GAMETHEME.colors.bg_popup),
            rounding,
        )
        draw_list.add_rect(
            (left, top),
            (right, bottom),
            imgui.get_color_u32(GAMETHEME.colors.text_main),
            rounding,
            0,
            1.0,
        )
        draw_list.add_text(
            (x - text_size.x * 0.5, y - text_size.y * 0.5),
            imgui.get_color_u32(GAMETHEME.colors.text_main),
            text,
        )

    def _draw_drag_preview(
        self,
        draw_list: imgui.ImDrawList,
        preview: UnitDragPreview,
        window_height: int,
    ) -> None:
        origin_y = window_height - preview.origin_y
        mouse_y = window_height - preview.mouse_y
        draw_list.add_line(
            (preview.origin_x, origin_y),
            (preview.mouse_x, mouse_y),
            imgui.get_color_u32((*GAMETHEME.colors.military[:3], 0.75)),
            2.0,
        )

        width = UNIT_DRAG_PREVIEW_WIDTH
        height = UNIT_DRAG_PREVIEW_HEIGHT
        left = preview.mouse_x - width * 0.5
        top = mouse_y - height * 0.5
        right = left + width
        bottom = top + height

        draw_list.add_rect_filled(
            (left - 4, top - 4),
            (right + 4, bottom + 4),
            imgui.get_color_u32((0.02, 0.02, 0.02, 0.65)),
            4.0,
        )

        if not self._flags.draw_flag(draw_list, preview.owner, left, top, right, bottom):
            draw_list.add_rect_filled(
                (left, top),
                (right, bottom),
                imgui.get_color_u32(GAMETHEME.colors.bg_input),
                2.0,
            )
