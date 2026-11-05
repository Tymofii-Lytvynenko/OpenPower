from __future__ import annotations

import math
from typing import Any

from src.client.renderers.mini_map_texture import MiniMapTextureCache
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.testability import set_widget_value


class MiniMapPanel:
    """Render REFERENCE's compact map controls over OpenPower's live region map."""

    TEMPLATE = "Mini_Map"
    WIDTH = 228
    HEIGHT = 155

    def __init__(self, viewport_ctrl: Any, player_tag: str, on_interaction=None) -> None:
        self.viewport = viewport_ctrl
        self.player_tag = str(player_tag)
        self._on_interaction = on_interaction
        self.texture_cache = MiniMapTextureCache()

    def render(self) -> None:
        renderer = getattr(self.viewport, "renderer", None)
        map_data = getattr(renderer, "map_data", None)
        if map_data is None:
            return

        display = imgui.get_io().display_size
        if display.x <= 0 or display.y <= 0:
            return
        x = max(0.0, float(display.x) - self.WIDTH)
        y = max(0.0, float(display.y) - self.HEIGHT)
        flags = (
            imgui.WindowFlags_.no_title_bar
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_collapse
            | imgui.WindowFlags_.no_saved_settings
        )
        with WindowManager.window(
            "MINI MAP",
            x=x,
            y=y,
            w=self.WIDTH,
            h=self.HEIGHT,
            closable=False,
            flags=flags,
            test_id="mini_map.panel",
            gml_template=self.TEMPLATE,
            padding=(0.0, 0.0),
            follow_position=True,
        ) as is_open:
            if is_open:
                self._render_contents(renderer, map_data)

    def close(self) -> None:
        self.texture_cache.close()

    def _render_contents(self, renderer, map_data) -> None:
        widgets = GMLWidgets(self.TEMPLATE)
        texture_manager = getattr(renderer, "texture_manager", None)
        palette = getattr(texture_manager, "active_color_map", {})
        overlay_revision = int(getattr(texture_manager, "overlay_revision", 0))
        mode_key = str(getattr(self.viewport, "current_mode_key", "political"))
        if mode_key == "terrain":
            palette = {}
        texture = self.texture_cache.get_texture(
            map_data,
            palette,
            mode_key=mode_key,
            overlay_revision=overlay_revision,
        )

        widgets.frame("frmMap")
        map_rect = widgets.rect("frmMap/btnMap")
        if map_rect is None:
            return
        origin = self._window_origin()
        draw = imgui.get_window_draw_list()
        map_minimum = (origin[0] + map_rect.x, origin[1] + map_rect.y)
        map_maximum = (map_minimum[0] + map_rect.width, map_minimum[1] + map_rect.height)
        draw.add_rect_filled(
            map_minimum,
            map_maximum,
            imgui.get_color_u32((0.04, 0.08, 0.12, 1.0)),
        )
        if texture is not None:
            widgets.picture(
                "frmMap/btnMap",
                lambda width, height: self.texture_cache.draw(
                    texture,
                    width,
                    height,
                    test_id="mini_map.image",
                ),
            )

        center_x, center_y = self._map_center()
        cross_x = map_minimum[0] + center_x * map_rect.width
        cross_y = map_minimum[1] + center_y * map_rect.height
        crosshair_color = imgui.get_color_u32((0.95, 0.92, 0.73, 0.68))
        draw.add_line((cross_x, map_minimum[1]), (cross_x, map_maximum[1]), crosshair_color, 1.0)
        draw.add_line((map_minimum[0], cross_y), (map_maximum[0], cross_y), crosshair_color, 1.0)
        draw.add_rect(
            map_minimum,
            map_maximum,
            imgui.get_color_u32((0.58, 0.66, 0.70, 0.9)),
            0.0,
            flags=0,
            thickness=1.0,
        )
        self._draw_crosshair(draw, cross_x, cross_y)

        self._draw_zoom(draw, widgets, origin)
        self._draw_home(draw, widgets, origin)
        self._draw_magnifier(draw, widgets, origin)

        clicked, active = widgets.hitbox_state("frmMap/btnMap", "mini_map.map")
        if clicked or (active and imgui.is_mouse_dragging(imgui.MouseButton_.left)):
            self._focus_from_mouse(map_rect, origin)
            if self._on_interaction is not None:
                self._on_interaction("mini_map.navigate")

    def _draw_zoom(self, draw, widgets: GMLWidgets, origin: tuple[float, float]) -> None:
        track = widgets.rect("btnZoom")
        if track is None:
            return
        x, y = origin[0] + track.x, origin[1] + track.y
        fraction = max(0.0, min(1.0, float(self._zoom_fraction())))
        rail = imgui.get_color_u32((0.08, 0.10, 0.12, 0.96))
        fill = imgui.get_color_u32((0.28, 0.50, 0.59, 0.82))
        thumb = imgui.get_color_u32((0.86, 0.89, 0.87, 1.0))
        draw.add_rect_filled((x + 3, y), (x + track.width - 3, y + track.height), rail)
        hidden_height = track.height * (1.0 - fraction)
        draw.add_rect_filled(
            (x + 3, y),
            (x + track.width - 3, y + hidden_height),
            fill,
        )
        thumb_y = y + hidden_height
        draw.add_rect_filled(
            (x - 1, thumb_y - 2),
            (x + track.width + 1, thumb_y + 2),
            thumb,
        )
        clicked, active = widgets.hitbox_state("btnZoomRect", "mini_map.zoom")
        if clicked or active:
            mouse = imgui.get_mouse_pos()
            value = 1.0 - (float(mouse.y) - y) / max(1.0, track.height)
            self._set_zoom_fraction(value)
            if self._on_interaction is not None:
                self._on_interaction("mini_map.zoom")

    def _draw_home(self, draw, widgets: GMLWidgets, origin: tuple[float, float]) -> None:
        rect = widgets.rect("btnHome")
        if rect is None:
            return
        x, y = origin[0] + rect.x, origin[1] + rect.y
        color = imgui.get_color_u32((0.82, 0.86, 0.86, 0.95))
        center_x = x + rect.width / 2.0
        draw.add_triangle_filled(
            (center_x, y + 5.5),
            (x + 6.5, y + 12.0),
            (x + rect.width - 6.5, y + 12.0),
            color,
        )
        draw.add_rect_filled(
            (x + 8.0, y + 11.0),
            (x + rect.width - 8.0, y + rect.height - 5.0),
            color,
        )
        draw.add_rect_filled(
            (center_x - 2.0, y + rect.height - 11.0),
            (center_x + 2.0, y + rect.height - 5.0),
            imgui.get_color_u32((0.10, 0.14, 0.17, 1.0)),
        )
        if widgets.hitbox("btnHome", "mini_map.home", tooltip="Return to your country"):
            self.viewport.focus_on_country(self.player_tag)

    def _draw_magnifier(self, draw, widgets: GMLWidgets, origin: tuple[float, float]) -> None:
        rect = widgets.rect("togMagnifier")
        if rect is None:
            return
        x, y = origin[0] + rect.x, origin[1] + rect.y
        enabled = bool(getattr(self.viewport, "show_all_units", False))
        background = (
            imgui.get_color_u32((0.20, 0.43, 0.49, 0.96))
            if enabled
            else imgui.get_color_u32((0.08, 0.10, 0.12, 0.96))
        )
        draw.add_rect_filled((x, y), (x + rect.width, y + rect.height), background)
        center_x, center_y = x + rect.width * 0.44, y + rect.height * 0.43
        color = imgui.get_color_u32((0.88, 0.91, 0.90, 1.0))
        radius = min(rect.width, rect.height) * 0.23
        points = [
            (center_x + math.cos(index * math.tau / 12) * radius,
             center_y + math.sin(index * math.tau / 12) * radius)
            for index in range(13)
        ]
        for start, end in zip(points, points[1:]):
            draw.add_line(start, end, color, 1.5)
        draw.add_line(
            (center_x + radius * 0.72, center_y + radius * 0.72),
            (center_x + radius * 1.55, center_y + radius * 1.55),
            color,
            2.0,
        )
        if widgets.hitbox(
            "togMagnifier",
            "mini_map.magnifier",
            tooltip="Show all unit icons",
        ):
            self.viewport.show_all_units = not enabled
        set_widget_value("mini_map.magnifier", bool(getattr(self.viewport, "show_all_units", False)))

    @staticmethod
    def _draw_crosshair(draw, center_x: float, center_y: float) -> None:
        color = imgui.get_color_u32((1.0, 0.94, 0.65, 0.95))
        draw.add_rect_filled(
            (center_x - 3.5, center_y - 3.5),
            (center_x + 3.5, center_y + 3.5),
            imgui.get_color_u32((0.04, 0.06, 0.07, 0.85)),
        )
        draw.add_rect(
            (center_x - 3.5, center_y - 3.5),
            (center_x + 3.5, center_y + 3.5),
            color,
            0.0,
            flags=0,
            thickness=1.0,
        )

    def _focus_from_mouse(self, map_rect, origin: tuple[float, float]) -> None:
        mouse = imgui.get_mouse_pos()
        x = (float(mouse.x) - origin[0] - map_rect.x) / max(1.0, map_rect.width)
        y = (float(mouse.y) - origin[1] - map_rect.y) / max(1.0, map_rect.height)
        self.viewport.focus_on_map_fraction(
            max(0.0, min(1.0, x)),
            max(0.0, min(1.0, y)),
        )

    def _map_center(self) -> tuple[float, float]:
        getter = getattr(self.viewport, "map_center_fraction", None)
        if not callable(getter):
            return 0.5, 0.5
        x, y = getter()
        return max(0.0, min(1.0, float(x))), max(0.0, min(1.0, float(y)))

    def _zoom_fraction(self) -> float:
        getter = getattr(self.viewport, "zoom_fraction", None)
        return float(getter()) if callable(getter) else 0.5

    def _set_zoom_fraction(self, value: float) -> None:
        setter = getattr(self.viewport, "set_zoom_fraction", None)
        if callable(setter):
            setter(max(0.0, min(1.0, float(value))))

    @staticmethod
    def _window_origin() -> tuple[float, float]:
        position = imgui.get_window_pos()
        return float(position.x), float(position.y)
