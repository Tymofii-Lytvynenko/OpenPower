from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from imgui_bundle import imgui

from src.client.controllers.camera_controller import CameraController
from src.client.renderers.flag_renderer import FlagRenderer, FlagTexture
from src.client.renderers.unit_projection import ProjectedUnit, RegionAnchor, UnitProjectionService
from src.client.ui.core.theme import GAMETHEME

if TYPE_CHECKING:
    from src.server.state import GameState


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
        self._flags = FlagRenderer()
        self._region_lookup: dict[int, RegionAnchor] = {}
        self._region_count = -1
        self._billboards: list[ProjectedUnit] = []

    @property
    def billboards(self) -> list[ProjectedUnit]:
        return self._billboards

    def render(
        self,
        state: Optional["GameState"],
        selected_unit_id: Optional[str],
        hovered_unit_id: Optional[str],
        drag_preview: Optional[UnitDragPreview],
    ) -> None:
        window = imgui.get_io().display_size
        width = int(window.x)
        height = int(window.y)

        self._billboards = self._project_units(state, width, height)

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
            for unit in self._billboards:
                self._draw_unit(draw_list, unit, height, selected_unit_id, hovered_unit_id)

            if drag_preview is not None:
                self._draw_drag_preview(draw_list, drag_preview, height)

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
        window_width: int,
        window_height: int,
    ) -> list[ProjectedUnit]:
        if state is None or "units" not in state.tables:
            return []

        units = state.tables["units"]
        if units.is_empty():
            return []

        self._refresh_region_lookup(state)
        return self._projection.project_units(
            units.to_dicts(),
            self._region_lookup,
            window_width,
            window_height,
        )

    def _refresh_region_lookup(self, state: "GameState") -> None:
        if "regions" not in state.tables:
            self._region_lookup = {}
            self._region_count = -1
            return

        regions = state.tables["regions"]
        if regions.height == self._region_count and self._region_lookup:
            return

        required = {"id", "center_x", "center_y"}
        if regions.is_empty() or not required.issubset(set(regions.columns)):
            self._region_lookup = {}
            self._region_count = -1
            return

        owner_expr = "owner" if "owner" in regions.columns else None
        columns = ["id", "center_x", "center_y"]
        if owner_expr:
            columns.append(owner_expr)

        lookup = {}
        for row in regions.select(columns).iter_rows(named=True):
            region_id = int(row["id"])
            lookup[region_id] = RegionAnchor(
                region_id=region_id,
                center_x=float(row["center_x"]),
                center_y=float(row["center_y"]),
                owner=str(row.get("owner", "")),
            )

        self._region_lookup = lookup
        self._region_count = regions.height

    def _draw_unit(
        self,
        draw_list: imgui.ImDrawList,
        unit: ProjectedUnit,
        window_height: int,
        selected_unit_id: Optional[str],
        hovered_unit_id: Optional[str],
    ) -> None:
        image_w = unit.width
        image_h = unit.height
        left = unit.screen_x - image_w * 0.5
        top = window_height - unit.screen_y - image_h * 0.5
        right = left + image_w
        bottom = top + image_h

        is_selected = unit.unit_id == selected_unit_id
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

        texture = self._flags.get_texture(unit.owner)
        if texture:
            self._draw_flag_image(draw_list, texture, left, top, right, bottom)
        else:
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

    def _draw_flag_image(
        self,
        draw_list: imgui.ImDrawList,
        texture: FlagTexture,
        left: float,
        top: float,
        right: float,
        bottom: float,
    ) -> None:
        try:
            draw_list.add_image(
                imgui.ImTextureRef(texture.gl_id),
                imgui.ImVec2(left, top),
                imgui.ImVec2(right, bottom),
            )
        except Exception:
            draw_list.add_rect_filled(
                (left, top),
                (right, bottom),
                imgui.get_color_u32(GAMETHEME.colors.bg_input),
                2.0,
            )

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

        texture = self._flags.get_texture(preview.owner)
        width = 44.0
        height = 30.0
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

        if texture:
            self._draw_flag_image(draw_list, texture, left, top, right, bottom)
