from __future__ import annotations

from typing import Optional

import arcade
import numpy as np

from src.client.renderers.unit_flag_atlas import UnitFlagAtlas
from src.client.renderers.unit_projection import ProjectedUnit


UNIT_BATCH_VERTEX_SHADER = """
#version 330

uniform vec2 u_screen_size;

in vec2 in_pos;
in vec2 in_uv;
in vec4 in_color;

out vec2 v_uv;
out vec4 v_color;

void main() {
    vec2 ndc = vec2(
        (in_pos.x / u_screen_size.x) * 2.0 - 1.0,
        (in_pos.y / u_screen_size.y) * 2.0 - 1.0
    );
    gl_Position = vec4(ndc, 0.0, 1.0);
    v_uv = in_uv;
    v_color = in_color;
}
"""


UNIT_BATCH_FRAGMENT_SHADER = """
#version 330

uniform sampler2D u_texture;

in vec2 v_uv;
in vec4 v_color;

out vec4 fragColor;

void main() {
    fragColor = texture(u_texture, v_uv) * v_color;
}
"""


class UnitBatchRenderer:
    """Draws all normal unit flags with one dynamic GPU batch."""

    def __init__(self):
        self._window = arcade.get_window()
        self._ctx = self._window.ctx
        self._program: Optional[arcade.gl.Program] = None
        self._buffer: Optional[arcade.gl.Buffer] = None
        self._geometry: Optional[arcade.gl.Geometry] = None
        self._capacity_vertices = 0
        self._stride_bytes = 8 * 4
        self._error_printed = False

    def render(
        self,
        units: list[ProjectedUnit],
        flags: UnitFlagAtlas,
        screen_width: int,
        screen_height: int,
    ) -> bool:
        if screen_width <= 0 or screen_height <= 0:
            return True
        if not units:
            return True
        if flags.texture is None:
            return False

        try:
            self._ensure_resources()
            if self._program is None or self._geometry is None or self._buffer is None:
                return False

            vertices = self._build_vertices(units, flags)
            if vertices.size == 0:
                return True

            vertex_count = int(vertices.shape[0])
            self._ensure_capacity(vertex_count)
            if self._geometry is None or self._buffer is None:
                return False

            self._buffer.orphan()
            self._buffer.write(vertices)

            self._ctx.scissor = None
            self._ctx.viewport = (0, 0, screen_width, screen_height)
            self._ctx.enable_only((self._ctx.BLEND,))
            self._ctx.blend_func = self._ctx.BLEND_DEFAULT

            flags.texture.use(0)
            self._program["u_texture"] = 0
            self._program["u_screen_size"] = (float(screen_width), float(screen_height))
            self._geometry.render(self._program, vertices=vertex_count)
            return True
        except Exception as exc:
            if not self._error_printed:
                print(f"[UnitBatchRenderer] Falling back to ImGui unit rendering: {exc}")
                self._error_printed = True
            return False

    def _ensure_resources(self) -> None:
        if self._program is None:
            self._program = self._ctx.program(
                vertex_shader=UNIT_BATCH_VERTEX_SHADER,
                fragment_shader=UNIT_BATCH_FRAGMENT_SHADER,
            )
        if self._buffer is None or self._geometry is None:
            self._ensure_capacity(1024)

    def _ensure_capacity(self, required_vertices: int) -> None:
        if self._buffer is not None and required_vertices <= self._capacity_vertices:
            return

        self._capacity_vertices = max(1024, required_vertices, self._capacity_vertices * 2)
        self._buffer = self._ctx.buffer(
            reserve=self._capacity_vertices * self._stride_bytes,
            usage="dynamic",
        )
        self._geometry = self._ctx.geometry(
            [
                arcade.gl.BufferDescription(
                    self._buffer,
                    "2f 2f 4f",
                    ["in_pos", "in_uv", "in_color"],
                )
            ],
            mode=self._ctx.TRIANGLES,
        )

    def _build_vertices(self, units: list[ProjectedUnit], flags: UnitFlagAtlas) -> np.ndarray:
        vertices = np.empty((len(units) * 6, 8), dtype=np.float32)
        cursor = 0

        for unit in units:
            entry = flags.entry_for(unit.owner)
            if entry is None:
                continue

            half_w = unit.width * 0.5
            half_h = unit.height * 0.5
            left = unit.screen_x - half_w
            right = unit.screen_x + half_w
            bottom = unit.screen_y - half_h
            top = unit.screen_y + half_h

            vertices[cursor : cursor + 6] = (
                (left, bottom, entry.u0, entry.v1, 1.0, 1.0, 1.0, 1.0),
                (right, bottom, entry.u1, entry.v1, 1.0, 1.0, 1.0, 1.0),
                (right, top, entry.u1, entry.v0, 1.0, 1.0, 1.0, 1.0),
                (left, bottom, entry.u0, entry.v1, 1.0, 1.0, 1.0, 1.0),
                (right, top, entry.u1, entry.v0, 1.0, 1.0, 1.0, 1.0),
                (left, top, entry.u0, entry.v0, 1.0, 1.0, 1.0, 1.0),
            )
            cursor += 6

        return vertices[:cursor]
