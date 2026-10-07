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
    u0: float
    v0: float
    u1: float
    v1: float

    @property
    def uv_min(self) -> imgui.ImVec2:
        return imgui.ImVec2(self.u0, self.v0)

    @property
    def uv_max(self) -> imgui.ImVec2:
        return imgui.ImVec2(self.u1, self.v1)


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
        self._slot_by_owner: dict[str, int] = {}
        self._atlas_columns = 0
        self._atlas_capacity = 0
        self._resized_flag_cache: dict[
            str,
            tuple[tuple[Path, int | None, int | None], Image.Image],
        ] = {}
        self._error_printed = False

    @property
    def texture_id(self) -> int:
        return self._texture_id

    @property
    def texture(self) -> Optional[Any]:
        return self._texture

    def entry_for(self, owner: str) -> Optional[FlagAtlasEntry]:
        return self._entries.get(self._clean_tag(owner)) or self._entries.get(self._fallback_tag)

    def ensure_owners(self, owners: Iterable[str]) -> None:
        requested = frozenset(self._clean_tag(owner) for owner in owners if owner)
        if not requested:
            return

        if requested.issubset(self._owners_key) and self._texture_id > 0:
            return

        owners = self._owners_key | requested
        if self._texture_id > 0 and self._append_new_owners(owners):
            return
        self._build_atlas(owners)

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
        slot_by_owner = dict(self._slot_by_owner)
        for tag in tags:
            if tag not in slot_by_owner:
                slot_by_owner[tag] = len(slot_by_owner)
        requested_capacity = 1 << (len(slot_by_owner) - 1).bit_length()
        requested_capacity = max(requested_capacity, self._atlas_capacity)
        columns = max(1, ceil(sqrt(requested_capacity)))
        rows = ceil(requested_capacity / columns)
        atlas_w = columns * cell_w
        atlas_h = rows * cell_h

        atlas = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))
        entries = {}

        for tag in tags:
            index = slot_by_owner[tag]
            col = index % columns
            row = index // columns
            x = col * cell_w + FLAG_ATLAS_PADDING
            y = row * cell_h + FLAG_ATLAS_PADDING

            flag = self._load_resized_flag(tag)
            atlas.paste(flag, (x, y), flag)

            entries[tag] = FlagAtlasEntry(
                u0=x / atlas_w,
                v0=y / atlas_h,
                u1=(x + FLAG_ATLAS_CELL_WIDTH) / atlas_w,
                v1=(y + FLAG_ATLAS_CELL_HEIGHT) / atlas_h,
            )

        texture = self._upload_to_gpu(atlas)
        if texture is None:
            return

        self._texture = texture
        self._texture_id = self._extract_texture_id(texture)
        self._entries = entries
        self._owners_key = owners
        self._slot_by_owner = slot_by_owner
        self._atlas_columns = columns
        self._atlas_capacity = columns * rows

    def _append_new_owners(self, owners: frozenset[str]) -> bool:
        """Upload new cells in reserved atlas space without re-packing existing UVs."""
        texture = self._texture
        if (
            texture is None
            or not callable(getattr(texture, "write", None))
            or self._atlas_columns < 1
        ):
            return False

        tags = owners | {self._fallback_tag}
        new_tags = sorted(tags.difference(self._slot_by_owner))
        if not new_tags:
            self._owners_key = owners
            return True
        if len(self._slot_by_owner) + len(new_tags) > self._atlas_capacity:
            return False

        cell_w = FLAG_ATLAS_CELL_WIDTH + FLAG_ATLAS_PADDING * 2
        cell_h = FLAG_ATLAS_CELL_HEIGHT + FLAG_ATLAS_PADDING * 2
        new_entries: dict[str, FlagAtlasEntry] = {}
        new_slots: dict[str, int] = {}
        for tag in new_tags:
            slot = len(self._slot_by_owner) + len(new_slots)
            col = slot % self._atlas_columns
            row = slot // self._atlas_columns
            x = col * cell_w
            y = row * cell_h
            flag = self._load_resized_flag(tag)
            cell = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
            cell.paste(flag, (FLAG_ATLAS_PADDING, FLAG_ATLAS_PADDING), flag)
            try:
                texture.write(
                    cell.tobytes(),
                    viewport=(x, y, cell_w, cell_h),
                )
            except Exception as exc:
                print(
                    "[UnitFlagAtlas] Partial atlas update failed; "
                    f"rebuilding the atlas: {exc}"
                )
                return False
            new_entries[tag] = FlagAtlasEntry(
                (x + FLAG_ATLAS_PADDING) / (self._atlas_columns * cell_w),
                (y + FLAG_ATLAS_PADDING) / ((self._atlas_capacity // self._atlas_columns) * cell_h),
                (x + FLAG_ATLAS_PADDING + FLAG_ATLAS_CELL_WIDTH)
                / (self._atlas_columns * cell_w),
                (y + FLAG_ATLAS_PADDING + FLAG_ATLAS_CELL_HEIGHT)
                / ((self._atlas_capacity // self._atlas_columns) * cell_h),
            )
            new_slots[tag] = slot

        self._entries.update(new_entries)
        self._slot_by_owner.update(new_slots)
        self._owners_key = owners
        return True

    def _load_resized_flag(self, tag: str) -> Image.Image:
        path = self._resolve_flag_path(tag)
        try:
            stat = path.stat()
            source_signature = (path, stat.st_mtime_ns, stat.st_size)
        except OSError:
            source_signature = (path, None, None)

        cached = self._resized_flag_cache.get(tag)
        if cached is not None and cached[0] == source_signature:
            return cached[1]

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
        # Mod-added owners rebuild the atlas, but unchanged flag files need not be decoded and resized again.
        self._resized_flag_cache[tag] = (source_signature, output)
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
