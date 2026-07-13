from __future__ import annotations

from math import radians, sin, tan
from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

from imgui_bundle import imgui

from src.client.controllers.camera_controller import CameraController
from src.client.renderers.unit_batch_renderer import UnitBatchRenderer
from src.client.renderers.unit_flag_atlas import UnitFlagAtlas
from src.client.renderers.unit_projection import (
    PreparedUnitProjectionData,
    ProjectedUnit,
    RegionAnchor,
    UnitProjectionService,
)
from src.client.ui.core.primitives import UIPrimitives, UnitCompositionRow
from src.client.ui.core.theme import GAMETHEME
from src.core.map.geo import EquirectangularProjection, GeoCoordinate, MapPixelCoordinate
from src.shared.engagement import EARTH_RADIUS_KM, ENGAGEMENT_RADIUS_KM

if TYPE_CHECKING:
    from src.shared.state import GameState


UNIT_DRAG_PREVIEW_WIDTH = 22.0
UNIT_DRAG_PREVIEW_HEIGHT = 15.0
UNIT_COMPOSITION_PLATE_WIDTH = 118.0
UNIT_COMPOSITION_PLATE_HEIGHT = 58.0
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
    "movement_progress",
    "is_moving",
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
        self._flag_units_signature: tuple | None = None
        self._flag_owners: frozenset[str] = frozenset()

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
    ) -> None:
        window = imgui.get_io().display_size
        width = int(window.x)
        height = int(window.y)
        filtered_units = self._get_filtered_units(state, visible_owners)
        units_signature = self._get_units_signature(state, filtered_units, visible_owners)

        self._prepare_flag_atlas_for_state(filtered_units, drag_preview, units_signature)
        self._billboards = self._project_units(state, filtered_units, width, height, units_signature)
        batch_drawn = self._batch.render(self._billboards, self._flags, width, height)
        needs_imgui_overlay = (
            not batch_drawn
            or show_engagement_zones
            or drag_preview is not None
            or selection_rect is not None
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
            if show_engagement_zones:
                self._draw_engagement_zones(
                    draw_list,
                    height,
                    selected_unit_id,
                    selected_unit_ids,
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
        cache_key = self._make_projection_cache_key(units_signature, window_width, window_height)
        if cache_key == self._projection_cache_key:
            return self._billboards

        prepared = self._get_prepared_units(filtered_units, units_signature)
        self._projection_cache_key = cache_key
        return self._projection.project_prepared_units(
            prepared,
            window_width,
            window_height,
        )

    def _make_projection_cache_key(
        self,
        units_signature: tuple | None,
        window_width: int,
        window_height: int,
    ) -> tuple:
        return (
            units_signature,
            window_width,
            window_height,
            round(self._camera.yaw, 6),
            round(self._camera.pitch, 6),
            round(self._camera.distance, 4),
            self._region_count,
        )

    def _get_prepared_units(self, units, units_signature: tuple | None) -> PreparedUnitProjectionData:
        prepared_key = (units_signature, self._region_count)
        if prepared_key == self._prepared_units_key:
            return self._prepared_units

        self._prepared_units = self._projection.prepare_units(units.to_dicts(), self._region_lookup)
        self._prepared_units_key = prepared_key
        return self._prepared_units

    def _get_filtered_units(self, state: Optional["GameState"], visible_owners: Optional[set[str]]):
        if state is None or "units" not in state.tables:
            return None
        units = state.tables["units"]
        if units.is_empty():
            return units
        if visible_owners is not None and "owner" in units.columns:
            import polars as pl
            units = units.filter(pl.col("owner").is_in(list(visible_owners)))
        return units

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
        # Using hash of visible_owners if it exists to invalidate cache when filter changes
        owners_hash = hash(frozenset(visible_owners)) if visible_owners is not None else 0
        if state_id == self._last_state_id and owners_hash == getattr(self, '_last_owners_hash', None):
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
        window_height: int,
        selected_unit_id: Optional[str],
        selected_unit_ids: Optional[set[str]],
    ) -> None:
        for unit in self._billboards:
            is_selected = unit.unit_id == selected_unit_id or (
                selected_unit_ids is not None and unit.unit_id in selected_unit_ids
            )
            fill_color = (0.95, 0.50, 0.16, 0.18) if is_selected else (0.30, 0.64, 0.96, 0.12)
            outline_color = (1.0, 0.68, 0.24, 0.92) if is_selected else (0.43, 0.76, 1.0, 0.72)
            center = (unit.screen_x, window_height - unit.screen_y)
            radius = self._engagement_zone_radius_pixels(unit, window_height)
            draw_list.add_circle_filled(center, radius, imgui.get_color_u32(fill_color), 48)
            draw_list.add_circle(center, radius, imgui.get_color_u32(outline_color), 48, 1.25)

    def _engagement_zone_radius_pixels(self, unit: ProjectedUnit, window_height: int) -> float:
        half_fov_radians = radians(max(1.0, self._camera.fov_deg)) * 0.5
        focal_length = window_height / (2.0 * tan(half_fov_radians))
        angular_radius = ENGAGEMENT_RADIUS_KM / EARTH_RADIUS_KM
        world_radius = self._projection.globe_radius * sin(angular_radius)
        return max(12.0, min(90.0, focal_length * world_radius / max(unit.distance_to_camera, 0.1)))

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

        if unit.stack_count > 1 and unit.stack_index == unit.stack_count - 1:
            self._draw_stack_badge(draw_list, right - 3, top - 7, unit.stack_count)

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

        if unit.stack_count > 1 and unit.stack_index == unit.stack_count - 1:
            self._draw_stack_badge(draw_list, right - 3, top - 7, unit.stack_count)

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

    def _draw_stack_badge(
        self,
        draw_list: imgui.ImDrawList,
        x: float,
        y: float,
        count: int,
    ) -> None:
        text = str(count)
        text_size = imgui.calc_text_size(text)
        radius = max(8.0, text_size.x * 0.5 + 5.0)
        draw_list.add_circle_filled(
            imgui.ImVec2(x, y),
            radius,
            imgui.get_color_u32(GAMETHEME.colors.bg_popup),
        )
        draw_list.add_circle(
            imgui.ImVec2(x, y),
            radius,
            imgui.get_color_u32(GAMETHEME.colors.text_main),
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
