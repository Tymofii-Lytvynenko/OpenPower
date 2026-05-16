from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sqrt
from pathlib import Path
from typing import Any, Iterable, Optional

import arcade
from PIL import Image, ImageOps
from imgui_bundle import imgui

from src.core.paths import ProjectPaths


FLAG_ATLAS_CELL_WIDTH = 32
FLAG_ATLAS_CELL_HEIGHT = 22
FLAG_ATLAS_PADDING = 2


@dataclass(frozen=True)
class FlagAtlasEntry:
    uv_min: imgui.ImVec2
    uv_max: imgui.ImVec2


class UnitFlagAtlas:
    """
    Packs all unit flags into one small GPU texture.
    This avoids one ImGui texture switch per country icon, which is very expensive
    when hundreds of unit billboards are visible.
    """

    def __init__(self):
        self.flags_dir = ProjectPaths.assets("base") / "flags"
        self._fallback_tag = "XXX"
        self._texture: Optional[Any] = None
        self._texture_id: int = 0
        self._entries: dict[str, FlagAtlasEntry] = {}
        self._owners_key: frozenset[str] = frozenset()
        self._error_printed = False

    @property
    def texture_id(self) -> int:
        return self._texture_id

    def ensure_owners(self, owners: Iterable[str]) -> None:
        requested = frozenset(self._clean_tag(owner) for owner in owners if owner)
        if not requested:
            return

        if requested.issubset(self._owners_key) and self._texture_id > 0:
            return

        self._build_atlas(self._owners_key | requested)

    def draw_flag(
        self,
        draw_list: imgui.ImDrawList,
        owner: str,
        left: float,
        top: float,
        right: float,
        bottom: float,
    ) -> bool:
        entry = self._entries.get(self._clean_tag(owner)) or self._entries.get(self._fallback_tag)
        if entry is None or self._texture_id <= 0:
            return False

        try:
            draw_list.add_image(
                imgui.ImTextureRef(self._texture_id),
                imgui.ImVec2(left, top),
                imgui.ImVec2(right, bottom),
                entry.uv_min,
                entry.uv_max,
            )
            return True
        except Exception:
            if not self._error_printed:
                print("[UnitFlagAtlas] Failed to draw atlas image via ImGui.")
                self._error_printed = True
            return False

    def _build_atlas(self, owners: frozenset[str]) -> None:
        tags = sorted(owners | {self._fallback_tag})
        cell_w = FLAG_ATLAS_CELL_WIDTH + FLAG_ATLAS_PADDING * 2
        cell_h = FLAG_ATLAS_CELL_HEIGHT + FLAG_ATLAS_PADDING * 2
        columns = max(1, ceil(sqrt(len(tags))))
        rows = ceil(len(tags) / columns)
        atlas_w = columns * cell_w
        atlas_h = rows * cell_h

        atlas = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))
        entries = {}

        for index, tag in enumerate(tags):
            col = index % columns
            row = index // columns
            x = col * cell_w + FLAG_ATLAS_PADDING
            y = row * cell_h + FLAG_ATLAS_PADDING

            flag = self._load_resized_flag(tag)
            atlas.paste(flag, (x, y), flag)

            entries[tag] = FlagAtlasEntry(
                uv_min=imgui.ImVec2(x / atlas_w, y / atlas_h),
                uv_max=imgui.ImVec2((x + FLAG_ATLAS_CELL_WIDTH) / atlas_w, (y + FLAG_ATLAS_CELL_HEIGHT) / atlas_h),
            )

        texture = self._upload_to_gpu(atlas)
        if texture is None:
            return

        self._texture = texture
        self._texture_id = self._extract_texture_id(texture)
        self._entries = entries
        self._owners_key = owners

    def _load_resized_flag(self, tag: str) -> Image.Image:
        path = self._resolve_flag_path(tag)
        try:
            with Image.open(path) as image:
                source = image.convert("RGBA")
        except Exception:
            source = Image.new("RGBA", (FLAG_ATLAS_CELL_WIDTH, FLAG_ATLAS_CELL_HEIGHT), (255, 0, 255, 255))

        resized = ImageOps.contain(
            source,
            (FLAG_ATLAS_CELL_WIDTH, FLAG_ATLAS_CELL_HEIGHT),
            method=self._resize_filter(),
        )
        output = Image.new("RGBA", (FLAG_ATLAS_CELL_WIDTH, FLAG_ATLAS_CELL_HEIGHT), (0, 0, 0, 0))
        x = (FLAG_ATLAS_CELL_WIDTH - resized.width) // 2
        y = (FLAG_ATLAS_CELL_HEIGHT - resized.height) // 2
        output.paste(resized, (x, y), resized)
        return output

    def _resolve_flag_path(self, tag: str) -> Path:
        clean_tag = self._clean_tag(tag)
        candidates = [
            self.flags_dir / f"{clean_tag}.png",
            self.flags_dir / f"{clean_tag.lower()}.png",
            self.flags_dir / f"{self._fallback_tag}.png",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return candidates[-1]

    def _upload_to_gpu(self, image: Image.Image) -> Optional[Any]:
        try:
            window = arcade.get_window()
            ctx = window.ctx
            texture = ctx.texture(
                (image.width, image.height),
                components=4,
                data=image.tobytes(),
            )
            texture.filter = (ctx.LINEAR, ctx.LINEAR)
            return texture
        except Exception as exc:
            print(f"[UnitFlagAtlas] GPU upload failed: {exc}")
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

    def _resize_filter(self) -> int:
        return getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BILINEAR)

    def _clean_tag(self, tag: str) -> str:
        return str(tag or self._fallback_tag).strip() or self._fallback_tag
