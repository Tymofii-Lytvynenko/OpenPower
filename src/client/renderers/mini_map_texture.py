from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Any, Mapping

import arcade
import numpy as np
from src.client.ui.core.instrumented_imgui import imgui


@dataclass(slots=True)
class MiniMapTexture:
    gl_obj: Any
    gl_id: int
    width: int
    height: int


class MiniMapRasterizer:
    """Downsample the live region overlay into the source mini-map dimensions."""

    WATER = (10, 22, 34, 255)
    UNKNOWN_LAND = (68, 82, 76, 255)
    BORDER = (17, 22, 26, 255)

    def __init__(self, size: tuple[int, int] = (180, 90)) -> None:
        self.width = max(1, int(size[0]))
        self.height = max(1, int(size[1]))

    def rasterize(
        self,
        packed_map: np.ndarray,
        palette: Mapping[int, tuple[int, ...]],
    ) -> np.ndarray:
        source = np.asarray(packed_map)
        if source.ndim != 2 or source.size == 0:
            raise ValueError("Mini-map source data must be a non-empty two-dimensional array.")

        source_height, source_width = source.shape
        x_indices = np.minimum(
            np.arange(self.width, dtype=np.uint64) * source_width // self.width,
            source_width - 1,
        )
        y_indices = np.minimum(
            np.arange(self.height, dtype=np.uint64) * source_height // self.height,
            source_height - 1,
        )
        sampled = source[np.ix_(y_indices, x_indices)].astype(np.int64, copy=False)

        rgba = np.empty((self.height, self.width, 4), dtype=np.uint8)
        rgba[:, :] = self.UNKNOWN_LAND
        rgba[sampled == 0] = self.WATER
        self._apply_palette(sampled, rgba, palette)

        borders = np.zeros(sampled.shape, dtype=bool)
        borders[:, :-1] |= (sampled[:, :-1] != sampled[:, 1:]) & (sampled[:, :-1] != 0)
        borders[1:, :] |= (sampled[1:, :] != sampled[:-1, :]) & (sampled[1:, :] != 0)
        rgba[borders] = self.BORDER
        return np.ascontiguousarray(rgba)

    @staticmethod
    def _apply_palette(
        sampled: np.ndarray,
        rgba: np.ndarray,
        palette: Mapping[int, tuple[int, ...]],
    ) -> None:
        entries = [
            (int(region_id), color)
            for region_id, color in palette.items()
            if int(region_id) != 0 and len(color) >= 3
        ]
        if not entries:
            return

        entries.sort(key=lambda item: item[0])
        ids = np.fromiter((item[0] for item in entries), dtype=np.int64)
        colors = np.asarray([
            (*tuple(int(channel) for channel in color[:3]), 255)
            for _, color in entries
        ], dtype=np.uint8)
        indexes = np.searchsorted(ids, sampled)
        valid = indexes < len(ids)
        valid &= ids[np.minimum(indexes, len(ids) - 1)] == sampled
        rgba[valid] = colors[indexes[valid]]


class MiniMapTextureCache:
    """Keep one uploaded texture for the current map mode and overlay revision."""

    def __init__(self, rasterizer: MiniMapRasterizer | None = None) -> None:
        self.rasterizer = rasterizer or MiniMapRasterizer()
        self._key: tuple[int, int, int, str, int] | None = None
        self._texture: MiniMapTexture | None = None
        self._upload_error_reported = False

    def get_texture(
        self,
        map_data,
        palette: Mapping[int, tuple[int, ...]],
        *,
        mode_key: str,
        overlay_revision: int,
    ) -> MiniMapTexture | None:
        if map_data is None:
            return None

        key = (
            id(map_data),
            int(map_data.width),
            int(map_data.height),
            str(mode_key),
            int(overlay_revision),
        )
        if key == self._key:
            return self._texture

        raster = self.rasterizer.rasterize(map_data.packed_map, palette)
        texture = self._upload(raster)
        self._release_texture(self._texture)
        self._texture = texture
        self._key = key
        return texture

    def draw(self, texture: MiniMapTexture, width: float, height: float,
             *, test_id: str | None = None) -> None:
        size = imgui.ImVec2(float(width), float(height))
        for factory in (
            getattr(imgui, "ImTextureRef", None),
            getattr(imgui, "ImTextureID", None),
        ):
            if factory is None:
                continue
            try:
                imgui.image(factory(texture.gl_id), size, test_id=test_id)
                return
            except Exception:
                pass

        try:
            imgui.image(texture.gl_id, size, test_id=test_id)
        except TypeError:
            imgui.image(ctypes.c_void_p(texture.gl_id), size, test_id=test_id)

    def close(self) -> None:
        self._release_texture(self._texture)
        self._texture = None
        self._key = None

    def _upload(self, rgba: np.ndarray) -> MiniMapTexture | None:
        try:
            try:
                window = arcade.get_window()
            except Exception:
                window = None
            if window is not None:
                context = window.ctx
                gl_texture = context.texture(
                    (rgba.shape[1], rgba.shape[0]),
                    components=4,
                    data=rgba.tobytes(),
                    filter=(context.NEAREST, context.NEAREST),
                )
                gl_id = self._texture_id(gl_texture)
                return MiniMapTexture(gl_texture, gl_id, rgba.shape[1], rgba.shape[0])

            return self._upload_with_current_context(rgba)
        except Exception as exc:
            if not self._upload_error_reported:
                print(f"[MiniMapTextureCache] GPU upload failed: {exc}")
                self._upload_error_reported = True
            return None

    def _upload_with_current_context(self, rgba: np.ndarray) -> MiniMapTexture | None:
        from OpenGL import GL

        if GL.glGetString(GL.GL_VERSION) is None:
            return None

        texture_id = int(GL.glGenTextures(1))
        if texture_id <= 0:
            return None

        active_texture = int(GL.glGetIntegerv(GL.GL_ACTIVE_TEXTURE))
        GL.glActiveTexture(GL.GL_TEXTURE0)
        previous_binding = int(GL.glGetIntegerv(GL.GL_TEXTURE_BINDING_2D))
        previous_unpack_alignment = int(GL.glGetIntegerv(GL.GL_UNPACK_ALIGNMENT))
        try:
            GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)
            GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
            GL.glTexImage2D(
                GL.GL_TEXTURE_2D,
                0,
                GL.GL_RGBA,
                rgba.shape[1],
                rgba.shape[0],
                0,
                GL.GL_RGBA,
                GL.GL_UNSIGNED_BYTE,
                rgba.tobytes(),
            )
        except Exception:
            GL.glDeleteTextures(1, [texture_id])
            raise
        finally:
            GL.glBindTexture(GL.GL_TEXTURE_2D, previous_binding)
            GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, previous_unpack_alignment)
            GL.glActiveTexture(active_texture)

        return MiniMapTexture(texture_id, texture_id, rgba.shape[1], rgba.shape[0])

    @classmethod
    def _release_texture(cls, texture: MiniMapTexture | None) -> None:
        if texture is None:
            return
        release = getattr(texture.gl_obj, "release", None)
        if callable(release):
            try:
                release()
            except Exception:
                pass
            return

        try:
            from OpenGL import GL

            if GL.glGetString(GL.GL_VERSION) is not None:
                GL.glDeleteTextures(1, [int(texture.gl_id)])
        except Exception:
            pass

    @staticmethod
    def _texture_id(texture: Any) -> int:
        raw = getattr(texture, "glo", None)
        if raw is None:
            return 0
        if hasattr(raw, "glo_id"):
            return int(raw.glo_id)
        if hasattr(raw, "value"):
            return int(raw.value)
        return int(raw)
