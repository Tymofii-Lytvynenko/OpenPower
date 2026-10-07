from __future__ import annotations

import math
from typing import Optional

import arcade
import arcade.gl

from src.client.renderers.texture_manager import TextureManager
from src.client.shader_registry import ShaderRegistry


class PlanarMapRenderer:
    """Render the shared map textures as an editor-only equirectangular map."""

    def __init__(
        self,
        context: arcade.gl.Context,
        texture_manager: TextureManager,
        map_width: int,
        map_height: int,
    ) -> None:
        self.context = context
        self.texture_manager = texture_manager
        self.map_width = max(1, int(map_width))
        self.map_height = max(1, int(map_height))
        self.transform = PlanarMapTransform(self.map_width, self.map_height)
        shader_sources = ShaderRegistry.load_bundle(
            ShaderRegistry.POLITICAL_V,
            ShaderRegistry.POLITICAL_F,
        )
        self.program = context.program(**shader_sources)
        self.geometry = arcade.gl.geometry.quad_2d_fs()

        self.program["u_map_texture"] = 0
        self.program["u_lookup_texture"] = 1
        self.program["u_terrain_texture"] = 2
        self.program["u_previous_lookup_texture"] = 3
        self.texture_manager.set_uniforms(self.program)

    def draw(
        self,
        viewport_size: tuple[int, int],
        *,
        overlay_enabled: bool,
        opacity: float,
        selected_dense_id: int,
    ) -> None:
        viewport_width, viewport_height = viewport_size
        if viewport_width <= 0 or viewport_height <= 0:
            return

        self.context.disable(self.context.DEPTH_TEST)
        self.texture_manager.bind_textures(self.program)
        self.program["u_viewport_size"] = (float(viewport_width), float(viewport_height))
        self.program["u_map_size"] = (float(self.map_width), float(self.map_height))
        self.program["u_map_center"] = (self.transform.center_u, self.transform.center_v)
        self.program["u_pan"] = (self.transform.pan_x, self.transform.pan_y)
        self.program["u_zoom"] = self.transform.zoom
        self.program["u_selected_id"] = int(selected_dense_id)
        self.program["u_overlay_mode"] = 1 if overlay_enabled else 0
        self.program["u_opacity"] = float(opacity)
        self.program["u_overlay_transition"] = self.texture_manager.overlay_transition_progress()
        self.geometry.render(self.program)

    def screen_to_pixel(
        self,
        screen_x: float,
        screen_y: float,
        viewport_size: tuple[int, int],
    ) -> Optional[tuple[int, int]]:
        return self.transform.screen_to_pixel(screen_x, screen_y, viewport_size)

    def pan(self, delta_x: float, delta_y: float) -> None:
        self.transform.pan(delta_x, delta_y)

    def zoom_at(
        self,
        screen_x: float,
        screen_y: float,
        scroll_steps: int,
        viewport_size: tuple[int, int],
    ) -> None:
        self.transform.zoom_at(screen_x, screen_y, scroll_steps, viewport_size)

    def focus_pixel(self, pixel_x: float, pixel_y: float) -> None:
        self.transform.focus_pixel(pixel_x, pixel_y)


class PlanarMapTransform:
    """Headless viewport transform shared by planar rendering and map picking."""

    MIN_ZOOM = 1.0
    MAX_ZOOM = 64.0
    ZOOM_STEP = 1.15

    def __init__(self, map_width: int, map_height: int) -> None:
        self.map_width = max(1, int(map_width))
        self.map_height = max(1, int(map_height))
        self.zoom = self.MIN_ZOOM
        self.center_u = 0.5
        self.center_v = 0.5
        self.pan_x = 0.0
        self.pan_y = 0.0

    def screen_to_pixel(
        self,
        screen_x: float,
        screen_y: float,
        viewport_size: tuple[int, int],
    ) -> Optional[tuple[int, int]]:
        """Use the shader's fit, pan, zoom, and UV orientation for editor picking."""
        viewport_width, viewport_height = viewport_size
        if viewport_width <= 0 or viewport_height <= 0:
            return None

        fit_scale = self._fit_scale(viewport_size, (self.map_width, self.map_height))
        map_screen_width = self.map_width * fit_scale * self.zoom
        map_screen_height = self.map_height * fit_scale * self.zoom
        pixel_center_x = math.floor(screen_x) + 0.5
        pixel_center_y = math.floor(screen_y) + 0.5
        u = self.center_u + (
            pixel_center_x - viewport_width * 0.5 - self.pan_x
        ) / map_screen_width
        v = self.center_v + (
            pixel_center_y - viewport_height * 0.5 - self.pan_y
        ) / map_screen_height
        if not (0.0 <= u < 1.0 and 0.0 <= v < 1.0):
            return None

        pixel_x = min(self.map_width - 1, int(u * self.map_width))
        pixel_y = min(self.map_height - 1, int((1.0 - v) * self.map_height))
        return pixel_x, pixel_y

    def pan(self, delta_x: float, delta_y: float) -> None:
        self.pan_x += float(delta_x)
        self.pan_y += float(delta_y)

    def zoom_at(
        self,
        screen_x: float,
        screen_y: float,
        scroll_steps: int,
        viewport_size: tuple[int, int],
    ) -> None:
        if scroll_steps == 0 or viewport_size[0] <= 0 or viewport_size[1] <= 0:
            return

        fit_scale = self._fit_scale(viewport_size, (self.map_width, self.map_height))
        pixel_center_x = math.floor(screen_x) + 0.5
        pixel_center_y = math.floor(screen_y) + 0.5
        offset_x = pixel_center_x - viewport_size[0] * 0.5 - self.pan_x
        offset_y = pixel_center_y - viewport_size[1] * 0.5 - self.pan_y
        anchor_u = self.center_u + offset_x / (self.map_width * fit_scale * self.zoom)
        anchor_v = self.center_v + offset_y / (self.map_height * fit_scale * self.zoom)

        next_zoom = min(
            self.MAX_ZOOM,
            max(self.MIN_ZOOM, self.zoom * self.ZOOM_STEP ** int(scroll_steps)),
        )
        if next_zoom == self.zoom:
            return

        self.zoom = next_zoom
        self.center_u = anchor_u - offset_x / (self.map_width * fit_scale * self.zoom)
        self.center_v = anchor_v - offset_y / (self.map_height * fit_scale * self.zoom)

    def focus_pixel(self, pixel_x: float, pixel_y: float) -> None:
        # Focus on texel centers so picking round-trips through the half-open UV bounds.
        self.center_u = min(1.0, max(0.0, (float(pixel_x) + 0.5) / self.map_width))
        self.center_v = min(1.0, max(0.0, 1.0 - (float(pixel_y) + 0.5) / self.map_height))
        self.pan_x = 0.0
        self.pan_y = 0.0

    @staticmethod
    def _fit_scale(
        viewport_size: tuple[int, int],
        map_size: tuple[int, int],
    ) -> float:
        return min(viewport_size[0] / map_size[0], viewport_size[1] / map_size[1])
