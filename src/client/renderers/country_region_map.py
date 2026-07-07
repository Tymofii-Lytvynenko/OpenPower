from __future__ import annotations

import ctypes
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import arcade
import numpy as np
from imgui_bundle import imgui
from PIL import Image

from src.core.map_data import RegionMapData


@dataclass(frozen=True, slots=True)
class CountryMapRaster:
    image: Image.Image
    region_ids: tuple[int, ...]
    source_bbox: tuple[int, int, int, int]


@dataclass(slots=True)
class CountryMapTexture:
    gl_obj: Any
    gl_id: int
    width: int
    height: int


class CountryRegionMapRasterizer:
    """Builds a cropped 2D country silhouette from the technical region map."""

    def __init__(
        self,
        max_size: tuple[int, int] = (520, 360),
        padding_px: int = 12,
        background: tuple[int, int, int, int] = (11, 13, 15, 255),
        fill: tuple[int, int, int, int] = (10, 89, 164, 255),
        border: tuple[int, int, int, int] = (33, 156, 255, 255),
    ):
        self.max_size = max_size
        self.padding_px = max(0, int(padding_px))
        self.background = np.asarray(background, dtype=np.uint8)
        self.fill = np.asarray(fill, dtype=np.uint8)
        self.border = np.asarray(border, dtype=np.uint8)

    def render(self, map_data: RegionMapData, region_ids: Iterable[int]) -> Optional[CountryMapRaster]:
        clean_region_ids = tuple(sorted({int(region_id) for region_id in region_ids if int(region_id) > 0}))
        if not clean_region_ids:
            return None

        id_values = np.asarray(clean_region_ids, dtype=map_data.packed_map.dtype)
        country_mask = np.isin(map_data.packed_map, id_values)
        if not bool(country_mask.any()):
            return None

        ys, xs = np.nonzero(country_mask)
        x0 = max(0, int(xs.min()) - self.padding_px)
        y0 = max(0, int(ys.min()) - self.padding_px)
        x1 = min(map_data.width, int(xs.max()) + self.padding_px + 1)
        y1 = min(map_data.height, int(ys.max()) + self.padding_px + 1)

        crop_ids = map_data.packed_map[y0:y1, x0:x1]
        crop_mask = country_mask[y0:y1, x0:x1]
        image = self._build_image(crop_ids, crop_mask)
        image = self._resize_to_fit(image)

        return CountryMapRaster(
            image=image,
            region_ids=clean_region_ids,
            source_bbox=(x0, y0, x1, y1),
        )

    def _build_image(self, crop_ids: np.ndarray, crop_mask: np.ndarray) -> Image.Image:
        h, w = crop_ids.shape
        rgba = np.empty((h, w, 4), dtype=np.uint8)
        rgba[:, :] = self.background

        variation = ((crop_ids % 7) * 7).astype(np.uint8)
        rgba[crop_mask, 0] = np.clip(int(self.fill[0]) + variation[crop_mask] // 4, 0, 255)
        rgba[crop_mask, 1] = np.clip(int(self.fill[1]) + variation[crop_mask], 0, 255)
        rgba[crop_mask, 2] = np.clip(int(self.fill[2]) + variation[crop_mask], 0, 255)
        rgba[crop_mask, 3] = self.fill[3]

        borders = self._region_borders(crop_ids, crop_mask)
        rgba[borders] = self.border

        return Image.fromarray(rgba)

    def _region_borders(self, crop_ids: np.ndarray, crop_mask: np.ndarray) -> np.ndarray:
        borders = np.zeros(crop_mask.shape, dtype=bool)

        borders[:-1, :] |= crop_mask[:-1, :] & (
            (crop_ids[:-1, :] != crop_ids[1:, :]) | ~crop_mask[1:, :]
        )
        borders[1:, :] |= crop_mask[1:, :] & (
            (crop_ids[1:, :] != crop_ids[:-1, :]) | ~crop_mask[:-1, :]
        )
        borders[:, :-1] |= crop_mask[:, :-1] & (
            (crop_ids[:, :-1] != crop_ids[:, 1:]) | ~crop_mask[:, 1:]
        )
        borders[:, 1:] |= crop_mask[:, 1:] & (
            (crop_ids[:, 1:] != crop_ids[:, :-1]) | ~crop_mask[:, :-1]
        )

        return borders

    def _resize_to_fit(self, image: Image.Image) -> Image.Image:
        max_w, max_h = self.max_size
        if image.width <= 0 or image.height <= 0:
            return image

        scale = min(max_w / image.width, max_h / image.height)
        new_size = (
            max(1, int(round(image.width * scale))),
            max(1, int(round(image.height * scale))),
        )
        if new_size == image.size:
            return image

        resampling = getattr(getattr(Image, "Resampling", Image), "NEAREST", Image.NEAREST)
        return image.resize(new_size, resampling)


class CountryRegionMapTextureCache:
    """Caches GPU textures for country previews while keeping GL objects alive."""

    def __init__(
        self,
        rasterizer: CountryRegionMapRasterizer | None = None,
        max_entries: int = 10,
    ):
        self.rasterizer = rasterizer or CountryRegionMapRasterizer()
        self.max_entries = max(1, int(max_entries))
        self._cache: OrderedDict[tuple[int, int, int, tuple[int, ...]], Optional[CountryMapTexture]] = OrderedDict()
        self._error_printed = False

    def get_texture(
        self,
        map_data: RegionMapData | None,
        region_ids: Iterable[int],
    ) -> Optional[CountryMapTexture]:
        if map_data is None:
            return None

        clean_region_ids = tuple(sorted({int(region_id) for region_id in region_ids if int(region_id) > 0}))
        if not clean_region_ids:
            return None

        key = (id(map_data), int(map_data.width), int(map_data.height), clean_region_ids)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        raster = self.rasterizer.render(map_data, clean_region_ids)
        texture = self._upload_to_gpu(raster.image) if raster is not None else None
        self._cache[key] = texture
        self._cache.move_to_end(key)
        while len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)

        return texture

    def draw_texture(self, texture: CountryMapTexture, width: float, height: float) -> None:
        self._render_imgui_image(texture.gl_id, width, height)

    def _upload_to_gpu(self, image: Image.Image) -> Optional[CountryMapTexture]:
        try:
            window = arcade.get_window()
            ctx = window.ctx
            gl_texture = ctx.texture(
                (image.width, image.height),
                components=4,
                data=image.tobytes(),
            )
            gl_texture.filter = (ctx.NEAREST, ctx.NEAREST)
            tex_id = self._extract_texture_id(gl_texture)
            if tex_id <= 0:
                return None
            return CountryMapTexture(gl_texture, tex_id, image.width, image.height)
        except Exception as exc:
            if not self._error_printed:
                print(f"[CountryRegionMapTextureCache] GPU upload failed: {exc}")
                self._error_printed = True
            return None

    def _extract_texture_id(self, texture: Any) -> int:
        raw_glo = getattr(texture, "glo", None)
        if raw_glo is None:
            return 0
        if hasattr(raw_glo, "glo_id"):
            return int(raw_glo.glo_id)
        if hasattr(raw_glo, "value"):
            return int(raw_glo.value)
        return int(raw_glo)

    def _render_imgui_image(self, gl_id: int, width: float, height: float) -> None:
        size = imgui.ImVec2(width, height)

        for factory in (
            getattr(imgui, "ImTextureRef", None),
            getattr(imgui, "ImTextureID", None),
        ):
            if factory is None:
                continue
            try:
                imgui.image(factory(gl_id), size)
                return
            except Exception:
                pass

        try:
            imgui.image(gl_id, size)
            return
        except TypeError:
            pass

        imgui.image(ctypes.c_void_p(gl_id), size)