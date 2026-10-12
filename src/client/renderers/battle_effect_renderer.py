"""Presentation-only tactical battle effects for the globe overlay."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
import math
import time
from typing import Any, Callable, Iterable, Mapping, Optional, TYPE_CHECKING

from src.client.ui.core.instrumented_imgui import imgui

from src.client.renderers.globe_overlay_projection import (
    GlobeOverlayProjection,
    ProjectedSurfacePoint,
)
from src.client.ui.core.theme import GAMETHEME
from src.client.utils.color_generator import generate_political_colors
from src.core.map.geo import EquirectangularProjection, MapPixelCoordinate

if TYPE_CHECKING:
    from src.client.controllers.camera_controller import CameraController
    from src.shared.state import GameState


LOGGER = logging.getLogger(__name__)
_VALID_STATUSES = frozenset({"active", "stalemate", "concluded"})
_VALID_MODES = frozenset({"positional", "assault"})
_MAX_FOOTPRINT_DIAMETER = 128.0
_GRID_CELL_SIZE = 8.0
_FALLBACK_COLUMN_SPACING = _MAX_FOOTPRINT_DIAMETER
_FALLBACK_ROW_SPACING = 32.0
_CONCLUSION_DURATION_SECONDS = 1.0
_MAX_CONCLUSION_CACHE = 256
_FIXED_OFFSETS: tuple[tuple[float, float], ...] = (
    (0.0, -30.0),
    (30.0, -24.0),
    (-30.0, -24.0),
    (0.0, 28.0),
    (34.0, 0.0),
    (-34.0, 0.0),
    (28.0, 28.0),
    (-28.0, 28.0),
)


@dataclass(frozen=True, slots=True)
class BattlePlacement:
    battle_id: str
    row: Mapping[str, Any]
    point: ProjectedSurfacePoint
    label: str
    mode: str
    status: str
    label_x: float
    label_y: float
    anchor_x: float
    anchor_y: float
    offset: tuple[float, float]
    attacker_color: tuple[float, float, float, float]
    defender_color: tuple[float, float, float, float]
    phase: float


@dataclass(slots=True)
class _FallbackSlotGrid:
    columns: int
    rows: int
    slots: list[tuple[float, float, tuple[float, float, float, float], tuple[tuple[int, int], ...]]]
    occupied_rows: list[int]


class BattleEffectRenderer:
    """Draw all battle effects in one non-interactive ImGui overlay.

    Authoritative rows are normalized only when their table revisions change.
    Camera-dependent projection and collision placement remain frame-local, so
    a unit filter can never relocate or hide a valid battle anchor.
    """

    MAX_FOOTPRINT_DIAMETER = _MAX_FOOTPRINT_DIAMETER
    GRID_CELL_SIZE = _GRID_CELL_SIZE
    FIXED_OFFSETS = _FIXED_OFFSETS
    MAX_CONCLUSION_CACHE = _MAX_CONCLUSION_CACHE

    def __init__(
        self,
        camera: "CameraController",
        map_width: int,
        map_height: int,
        globe_radius: float,
        *,
        color_resolver: Callable[[str], tuple[int, int, int]] | None = None,
    ) -> None:
        self._projection = GlobeOverlayProjection(
            camera,
            map_width,
            map_height,
            globe_radius,
            min_marker_radius=5.0,
            max_marker_radius=12.0,
        )
        self._geo = EquirectangularProjection(map_width, map_height)
        self._color_resolver = color_resolver
        self._normalized_cache_key: tuple[Any, ...] | None = None
        self._normalized_rows: tuple[dict[str, Any], ...] = ()
        self._region_cache: dict[int, tuple[float, float]] = {}
        self._side_palette: dict[str, tuple[float, float, float, float]] = {}
        self._conclusion_cache: dict[str, tuple[dict[str, Any], float]] = {}
        self._fallback_slot_layouts: dict[
            tuple[int, int, float, float],
            tuple[int, int, list[tuple[float, float, tuple[float, float, float, float], tuple[tuple[int, int], ...]]]],
        ] = {}
        self._diagnostic_keys: set[tuple[Any, ...]] = set()
        self._last_layout: tuple[BattlePlacement, ...] = ()

    @property
    def normalized_rows(self) -> tuple[dict[str, Any], ...]:
        """Expose the revision-cached rows for diagnostics and focused tests."""

        return self._normalized_rows

    @property
    def normalized_cache_key(self) -> tuple[Any, ...] | None:
        return self._normalized_cache_key

    @property
    def last_layout(self) -> tuple[BattlePlacement, ...]:
        return self._last_layout

    @property
    def conclusion_cache_size(self) -> int:
        return len(self._conclusion_cache)

    def render(
        self,
        state: Optional["GameState"],
        presentation_total_minutes: float | None = None,
        reduce_motion: bool = False,
    ) -> None:
        if state is None:
            self._last_layout = ()
            return

        rows = list(self._normalize_state(state))
        now = time.monotonic()
        visible_rows: list[dict[str, Any]] = []
        current_ids: set[str] = set()
        appended_conclusion = False
        for row in rows:
            battle_id = str(row.get("id") or "")
            if not battle_id:
                self._diagnose("missing_id", battle_id, self._normalized_cache_key)
                continue
            current_ids.add(battle_id)
            status = self._status(row)
            if status == "concluded":
                self._conclusion_cache.setdefault(battle_id, (dict(row), now))
                if len(self._conclusion_cache) > _MAX_CONCLUSION_CACHE:
                    oldest_id = min(
                        self._conclusion_cache,
                        key=lambda key: self._conclusion_cache[key][1],
                    )
                    self._conclusion_cache.pop(oldest_id, None)
            else:
                self._conclusion_cache.pop(battle_id, None)
            visible_rows.append(row)

        # A concluded row may disappear on the next snapshot.  Keep only the
        # short local cue; never resurrect active animation from this cache.
        for battle_id, (cached_row, started_at) in list(self._conclusion_cache.items()):
            if now - started_at > _CONCLUSION_DURATION_SECONDS:
                del self._conclusion_cache[battle_id]
            elif battle_id not in current_ids:
                visible_rows.append(cached_row)
                appended_conclusion = True

        if appended_conclusion:
            visible_rows.sort(key=lambda row: str(row.get("id") or ""))
        window = imgui.get_io().display_size
        width = int(window.x)
        height = int(window.y)
        if width <= 0 or height <= 0:
            self._last_layout = ()
            return

        if not self._projection.prepare(width, height):
            self._last_layout = ()
            return

        candidate_rows: list[dict[str, Any]] = []
        candidate_anchors: list[tuple[float, float]] = []
        for row in visible_rows:
            anchor = self._anchor_for_row(row)
            if anchor is None:
                self._diagnose("missing_anchor", str(row.get("id") or ""), self._normalized_cache_key)
                continue
            candidate_rows.append(row)
            candidate_anchors.append(anchor)

        projected: list[tuple[dict[str, Any], ProjectedSurfacePoint]] = []
        points = self._projection.project_anchors(
            candidate_anchors,
            width,
            height,
            marker_radius=8.0,
        )
        for row, point in zip(candidate_rows, points):
            if point is not None:
                projected.append((row, point))

        placements = self._layout(projected, width, height, presentation_total_minutes, reduce_motion)
        self._last_layout = tuple(placements)
        if not placements:
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
        if imgui.begin("##BattleEffectOverlay", None, flags)[0]:
            draw_list = imgui.get_window_draw_list()
            for placement in placements:
                self._draw_placement(draw_list, placement, width, height, reduce_motion)
        imgui.end()

    def _normalize_state(self, state: "GameState") -> tuple[dict[str, Any], ...]:
        tables = getattr(state, "tables", {})
        battles = tables.get("battles")
        regions = tables.get("regions")
        revisions = getattr(state, "table_revisions", {})
        battle_revision = revisions.get("battles", id(battles)) if battles is not None else 0
        region_revision = revisions.get("regions", id(regions)) if regions is not None else 0
        country_revision = revisions.get("countries", 0)
        cache_key = (int(battle_revision), int(region_revision), int(country_revision))
        if cache_key == self._normalized_cache_key:
            return self._normalized_rows

        region_cache: dict[int, tuple[float, float]] = {}
        if regions is not None and not regions.is_empty() and "id" in regions.columns:
            has_geo = {"latitude", "longitude"}.issubset(regions.columns)
            has_pixel = {"center_x", "center_y"}.issubset(regions.columns)
            for raw_row in regions.to_dicts():
                try:
                    region_id = int(raw_row.get("id") or 0)
                    if has_geo and self._valid_coordinate(raw_row.get("latitude"), raw_row.get("longitude")):
                        region_cache[region_id] = (
                            float(raw_row["latitude"]),
                            self._normalize_longitude(float(raw_row["longitude"])),
                        )
                    elif has_pixel:
                        geo = self._geo.pixel_to_geo(
                            MapPixelCoordinate(float(raw_row["center_x"]), float(raw_row["center_y"]))
                        )
                        region_cache[region_id] = (geo.latitude, geo.longitude)
                except (TypeError, ValueError, OverflowError):
                    self._diagnose("invalid_region", raw_row.get("id"), region_revision)

        rows: list[dict[str, Any]] = []
        if battles is not None and not battles.is_empty():
            for raw_row in battles.to_dicts():
                row = {
                    key: raw_row.get(key)
                    for key in (
                        "id",
                        "region_id",
                        "anchor_latitude",
                        "anchor_longitude",
                        "anchor_source",
                        "attacker_side",
                        "defender_side",
                        "mode",
                        "status",
                        "round",
                        "started_at_minute",
                        "concluded_at_minute",
                    )
                }
                rows.append(row)
        rows.sort(key=lambda row: str(row.get("id") or ""))
        self._normalized_cache_key = cache_key
        self._normalized_rows = tuple(rows)
        self._region_cache = region_cache
        self._refresh_palette(rows)
        return self._normalized_rows

    def _refresh_palette(self, rows: Iterable[Mapping[str, Any]]) -> None:
        side_keys = {
            side
            for row in rows
            for side in (self._side_key(row.get("attacker_side")), self._side_key(row.get("defender_side")))
            if side
        }
        for side in sorted(side_keys):
            self._side_palette.setdefault(side, self._resolve_side_color(side))

    def _resolve_side_color(self, side: str) -> tuple[float, float, float, float]:
        if self._color_resolver is not None:
            try:
                red, green, blue = self._color_resolver(side)
                scale = 1.0 if max(abs(float(red)), abs(float(green)), abs(float(blue))) <= 1.0 else 255.0
                return (
                    max(0.0, min(1.0, float(red) / scale)),
                    max(0.0, min(1.0, float(green) / scale)),
                    max(0.0, min(1.0, float(blue) / scale)),
                    1.0,
                )
            except (TypeError, ValueError):
                self._diagnose("invalid_side_color", side, self._normalized_cache_key)
        generated = generate_political_colors([side]).get(side, (120, 120, 120))
        return (generated[0] / 255.0, generated[1] / 255.0, generated[2] / 255.0, 1.0)

    def side_colors(self, row: Mapping[str, Any]) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
        attacker = self._side_key(row.get("attacker_side"))
        defender = self._side_key(row.get("defender_side"))
        attacker_color = self._side_palette.get(attacker) or self._resolve_side_color(attacker or "SIDE_A")
        defender_color = self._side_palette.get(defender) or self._resolve_side_color(defender or "SIDE_B")
        if attacker == defender:
            defender_color = self._resolve_side_color((defender or "SIDE_B") + ":defender")
        return attacker_color, defender_color

    def phase_for(
        self,
        row: Mapping[str, Any],
        presentation_total_minutes: float | None,
        reduce_motion: bool = False,
    ) -> float:
        """Return a stable digest-seeded phase independent of Python hash()."""

        if reduce_motion:
            return 0.5
        battle_id = str(row.get("id") or "")
        digest = hashlib.blake2b(battle_id.encode("utf-8"), digest_size=8).digest()
        seed = int.from_bytes(digest, "big") / float(2**64)
        started = float(row.get("started_at_minute") or 0.0)
        round_number = float(row.get("round") or 0.0)
        clock = float(presentation_total_minutes) if presentation_total_minutes is not None else started
        cadence = 0.65 if self._mode(row) == "assault" else 0.32
        return (seed + clock * cadence + started * 0.013 + round_number * 0.071) % 1.0

    @staticmethod
    def can_draw_decorative(point: ProjectedSurfacePoint, footprint_radius: float) -> bool:
        """Keep a complete halo/exchange footprint inside the visible limb."""

        return point.silhouette_clearance >= max(0.0, float(footprint_radius))

    def _layout(
        self,
        projected: list[tuple[dict[str, Any], ProjectedSurfacePoint]],
        width: int,
        height: int,
        presentation_total_minutes: float | None,
        reduce_motion: bool,
    ) -> list[BattlePlacement]:
        occupied: dict[int, int] = {}
        anchor_counts: dict[tuple[float, float], int] = {}
        for _, point in projected:
            anchor_key = (point.screen_x, float(height) - point.screen_y)
            anchor_counts[anchor_key] = anchor_counts.get(anchor_key, 0) + 1
        anchor_ranks: dict[tuple[float, float], int] = {}
        fallback_grids: dict[tuple[float, float], _FallbackSlotGrid] = {}
        placed_rects: list[tuple[float, float, float, float]] = []
        placements: list[BattlePlacement] = []
        for row, point in projected:
            battle_id = str(row.get("id") or "")
            status = self._status(row)
            mode = self._mode(row)
            label = self._label(mode, status)
            anchor_x = point.screen_x
            anchor_y = float(height) - point.screen_y
            text_width = max(44.0, float(len(label) * 7 + 18))
            text_height = 22.0
            chosen_offset = _FIXED_OFFSETS[0]
            chosen_rect = self._clamp_rect(
                self._rect_for_offset(anchor_x, anchor_y, text_width, text_height, chosen_offset),
                width,
                height,
            )
            anchor_key = (anchor_x, anchor_y)
            anchor_rank = anchor_ranks.get(anchor_key, 0)
            anchor_ranks[anchor_key] = anchor_rank + 1
            crowded_anchor = anchor_counts[anchor_key] > len(_FIXED_OFFSETS)
            skip_fixed_offsets = crowded_anchor and anchor_rank >= len(_FIXED_OFFSETS)
            found_offset = False
            if not skip_fixed_offsets:
                for offset in _FIXED_OFFSETS:
                    candidate = self._clamp_rect(
                        self._rect_for_offset(anchor_x, anchor_y, text_width, text_height, offset),
                        width,
                        height,
                    )
                    if not self._rect_collides(candidate, occupied):
                        chosen_offset = offset
                        chosen_rect = candidate
                        found_offset = True
                        break

            if not found_offset:
                grid_key = (text_width, text_height)
                fallback_grid = fallback_grids.get(grid_key)
                if fallback_grid is None:
                    layout_key = (width, height, text_width, text_height)
                    slot_layout = self._fallback_slot_layouts.get(layout_key)
                    if slot_layout is None:
                        built_grid = self._build_fallback_grid(
                            width,
                            height,
                            text_width,
                            text_height,
                        )
                        slot_layout = (built_grid.columns, built_grid.rows, built_grid.slots)
                        self._fallback_slot_layouts[layout_key] = slot_layout
                        if len(self._fallback_slot_layouts) > 8:
                            self._fallback_slot_layouts.pop(next(iter(self._fallback_slot_layouts)))
                    fallback_grid = _FallbackSlotGrid(
                        slot_layout[0],
                        slot_layout[1],
                        slot_layout[2],
                        [0] * slot_layout[1],
                    )
                    for placed_rect in placed_rects:
                        self._mark_fallback_slots(placed_rect, fallback_grid)
                    fallback_grids[grid_key] = fallback_grid
                slot = self._nearest_fallback_slot(anchor_x, anchor_y, fallback_grid)
                while slot is not None:
                    offset, candidate, coverage, column, grid_row = slot
                    if not self._coverage_collides(coverage, occupied):
                        chosen_offset = offset
                        chosen_rect = candidate
                        found_offset = True
                        break
                    fallback_grid.occupied_rows[grid_row] |= 1 << column
                    slot = self._nearest_fallback_slot(anchor_x, anchor_y, fallback_grid)
            self._occupy(chosen_rect, occupied)
            placed_rects.append(chosen_rect)
            for fallback_grid in fallback_grids.values():
                self._mark_fallback_slots(chosen_rect, fallback_grid)
            attacker_color, defender_color = self.side_colors(row)
            placements.append(
                BattlePlacement(
                    battle_id=battle_id,
                    row=row,
                    point=point,
                    label=label,
                    mode=mode,
                    status=status,
                    label_x=chosen_rect[0],
                    label_y=chosen_rect[1],
                    anchor_x=anchor_x,
                    anchor_y=anchor_y,
                    offset=chosen_offset,
                    attacker_color=attacker_color,
                    defender_color=defender_color,
                    phase=self.phase_for(row, presentation_total_minutes, reduce_motion),
                )
            )
        return placements

    def _nearest_fallback_slot(
        self,
        anchor_x: float,
        anchor_y: float,
        grid: _FallbackSlotGrid,
    ) -> tuple[tuple[float, float], tuple[float, float, float, float], tuple[tuple[int, int], ...], int, int] | None:
        """Return the nearest currently available grid slot using row bitmasks."""

        half_width = grid.slots[0][2][2] * 0.5 if grid.slots else 0.0
        half_height = grid.slots[0][2][3] * 0.5 if grid.slots else 0.0
        origin_column = min(
            grid.columns - 1,
            max(0, round((anchor_x - half_width) / _FALLBACK_COLUMN_SPACING)),
        )
        origin_row = min(
            grid.rows - 1,
            max(0, round((anchor_y - half_height) / _FALLBACK_ROW_SPACING)),
        )
        best_distance: int | None = None
        best_slot: tuple[int, int] | None = None
        full_mask = (1 << grid.columns) - 1
        max_vertical_distance = max(origin_row, grid.rows - 1 - origin_row)
        for vertical_distance in range(max_vertical_distance + 1):
            candidate_rows = (
                (origin_row,)
                if vertical_distance == 0
                else (origin_row - vertical_distance, origin_row + vertical_distance)
            )
            for row in candidate_rows:
                if not 0 <= row < grid.rows:
                    continue
                free_columns = full_mask & ~grid.occupied_rows[row]
                if not free_columns:
                    continue
                left_columns = free_columns & ((1 << (origin_column + 1)) - 1)
                right_columns = free_columns & (full_mask ^ ((1 << (origin_column + 1)) - 1))
                candidate_columns = []
                if left_columns:
                    candidate_columns.append(left_columns.bit_length() - 1)
                if right_columns:
                    candidate_columns.append((right_columns & -right_columns).bit_length() - 1)
                for column in candidate_columns:
                    horizontal_distance = column - origin_column
                    distance = (horizontal_distance * horizontal_distance) + (vertical_distance * vertical_distance)
                    if best_distance is None or distance < best_distance:
                        best_distance = distance
                        best_slot = (column, row)

            if best_distance is not None and (vertical_distance + 1) ** 2 > best_distance:
                break

        if best_slot is None:
            return None
        column, row = best_slot
        center_x, center_y, rect, coverage = grid.slots[row * grid.columns + column]
        return (center_x - anchor_x, center_y - anchor_y), rect, coverage, column, row

    @staticmethod
    def _build_fallback_grid(
        width: int,
        height: int,
        text_width: float,
        text_height: float,
    ) -> _FallbackSlotGrid:
        half_width = text_width * 0.5
        half_height = text_height * 0.5
        columns = max(1, int(max(0.0, width - text_width) // _FALLBACK_COLUMN_SPACING) + 1)
        rows = max(1, int(max(0.0, height - text_height) // _FALLBACK_ROW_SPACING) + 1)
        slots = []
        for row in range(rows):
            center_y = half_height + row * _FALLBACK_ROW_SPACING
            for column in range(columns):
                center_x = half_width + column * _FALLBACK_COLUMN_SPACING
                rect = (
                    center_x - half_width,
                    center_y - half_height,
                    center_x + half_width,
                    center_y + half_height,
                )
                min_cell_x, max_cell_x, min_cell_y, max_cell_y, column_mask = BattleEffectRenderer._rect_cell_coverage(rect)
                coverage = tuple(
                    (cell_y, column_mask)
                    for cell_y in range(min_cell_y, max_cell_y + 1)
                )
                slots.append((center_x, center_y, rect, coverage))
        return _FallbackSlotGrid(columns, rows, slots, [0] * rows)

    @staticmethod
    def _mark_fallback_slots(
        rect: tuple[float, float, float, float],
        grid: _FallbackSlotGrid,
    ) -> None:
        text_width = grid.slots[0][2][2] - grid.slots[0][2][0]
        text_height = grid.slots[0][2][3] - grid.slots[0][2][1]
        left, top, right, bottom = rect
        min_column = max(0, math.floor((left - text_width) / _FALLBACK_COLUMN_SPACING) + 1)
        max_column = min(grid.columns - 1, math.ceil(right / _FALLBACK_COLUMN_SPACING) - 1)
        min_row = max(0, math.floor((top - text_height) / _FALLBACK_ROW_SPACING) + 1)
        max_row = min(grid.rows - 1, math.ceil(bottom / _FALLBACK_ROW_SPACING) - 1)
        for row in range(min_row, max_row + 1):
            for column in range(min_column, max_column + 1):
                grid.occupied_rows[row] |= 1 << column

    @staticmethod
    def _coverage_collides(coverage: tuple[tuple[int, int], ...], occupied: Mapping[int, int]) -> bool:
        return any(occupied.get(cell_y, 0) & column_mask for cell_y, column_mask in coverage)

    def _draw_placement(
        self,
        draw_list: Any,
        placement: BattlePlacement,
        width: int,
        height: int,
        reduce_motion: bool,
    ) -> None:
        point = placement.point
        x = placement.anchor_x
        y = placement.anchor_y
        radius = point.marker_radius
        phase = placement.phase
        if placement.status == "stalemate":
            marker_color = (0.95, 0.65, 0.18, 0.95)
        elif placement.status == "concluded":
            marker_color = (0.92, 0.92, 0.92, 0.95)
        elif placement.mode == "assault":
            marker_color = placement.attacker_color
        else:
            marker_color = placement.defender_color

        draw_list.add_circle_filled((x, y), radius, imgui.get_color_u32(marker_color), 20)
        draw_list.add_circle(
            (x, y),
            radius + 2.0,
            imgui.get_color_u32((1.0, 0.85, 0.35, 0.95)),
            20,
            1.5,
        )
        draw_list.add_text(
            (x - 3.0, y - 7.0),
            imgui.get_color_u32((1.0, 1.0, 1.0, 1.0)),
            "!" if placement.status != "concluded" else "×",
        )

        decorative_footprint = 34.0 if placement.mode == "assault" else 24.0
        if (
            placement.status in {"active"}
            and not reduce_motion
            and placement.mode in {"positional", "assault"}
            and self.can_draw_decorative(point, decorative_footprint)
        ):
            if placement.mode == "assault":
                pulse = 0.65 + 0.35 * (0.5 + 0.5 * math.sin(phase * math.tau))
                draw_list.add_circle(
                    (x, y),
                    radius + 8.0 + 4.0 * pulse,
                    imgui.get_color_u32((*placement.attacker_color[:3], 0.60)),
                    24,
                    2.0,
                )
                left = (x - 18.0, y)
                right = (x + 18.0, y)
                draw_list.add_line(left, right, imgui.get_color_u32(placement.defender_color), 2.0)
                draw_list.add_circle(
                    (x + 18.0 * (phase - 0.5), y),
                    4.0,
                    imgui.get_color_u32(placement.attacker_color),
                    12,
                    1.5,
                )
            else:
                pulse = 0.5 + 0.5 * math.sin(phase * math.tau)
                draw_list.add_circle(
                    (x, y),
                    radius + 5.0 + 2.0 * pulse,
                    imgui.get_color_u32((*placement.defender_color[:3], 0.48)),
                    20,
                    1.5,
                )
                draw_list.add_line(
                    (x - 10.0, y),
                    (x + 10.0, y),
                    imgui.get_color_u32(placement.attacker_color),
                    1.5,
                )
        elif placement.status == "concluded":
            draw_list.add_line(
                (x - radius, y - radius),
                (x + radius, y + radius),
                imgui.get_color_u32((1.0, 1.0, 1.0, 0.85)),
                1.5,
            )

        # The leader always terminates at the exact projected anchor.  It is
        # not shifted by collision layout and therefore preserves geography.
        label_center_x = placement.label_x + max(22.0, float(len(placement.label) * 7 + 18)) * 0.5
        label_center_y = placement.label_y + 11.0
        draw_list.add_line(
            (x, y),
            (label_center_x, label_center_y),
            imgui.get_color_u32((1.0, 1.0, 1.0, 0.42)),
            1.0,
        )
        text_width = max(44.0, float(len(placement.label) * 7 + 18))
        draw_list.add_rect_filled(
            (placement.label_x, placement.label_y),
            (placement.label_x + text_width, placement.label_y + 22.0),
            imgui.get_color_u32((0.04, 0.04, 0.06, 0.86)),
            4.0,
        )
        draw_list.add_rect(
            (placement.label_x, placement.label_y),
            (placement.label_x + text_width, placement.label_y + 22.0),
            imgui.get_color_u32(marker_color),
            4.0,
            0,
            1.2,
        )
        draw_list.add_text(
            (placement.label_x + 9.0, placement.label_y + 4.0),
            imgui.get_color_u32(GAMETHEME.colors.text_main),
            placement.label,
        )

    def _anchor_for_row(self, row: Mapping[str, Any]) -> tuple[float, float] | None:
        source = str(row.get("anchor_source") or "").strip().lower()
        if (
            self._valid_coordinate(row.get("anchor_latitude"), row.get("anchor_longitude"))
            and source in {"", "contact", "region_center"}
        ):
            return (
                float(row["anchor_latitude"]),
                self._normalize_longitude(float(row["anchor_longitude"])),
            )
        try:
            return self._region_cache.get(int(row.get("region_id") or 0))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _status(row: Mapping[str, Any]) -> str:
        status = str(row.get("status") or "").strip().lower()
        return status if status in _VALID_STATUSES else "unknown"

    @staticmethod
    def _mode(row: Mapping[str, Any]) -> str:
        mode = str(row.get("mode") or "").strip().lower()
        return mode if mode in _VALID_MODES else "unknown"

    @staticmethod
    def _label(mode: str, status: str) -> str:
        if status not in _VALID_STATUSES:
            return "Battle"
        if status == "stalemate":
            return "Stalemate"
        if status == "concluded":
            return "Concluded"
        if mode == "assault":
            return "Active"
        if mode == "positional":
            return "Passive"
        return "Battle"

    @staticmethod
    def _side_key(value: Any) -> str:
        if isinstance(value, (list, tuple, set, frozenset)):
            return ",".join(sorted(str(item).strip().upper() for item in value if str(item).strip()))
        return ",".join(sorted(part.strip().upper() for part in str(value or "").split(",") if part.strip()))

    @staticmethod
    def _valid_coordinate(latitude: Any, longitude: Any) -> bool:
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (TypeError, ValueError):
            return False
        return math.isfinite(lat) and math.isfinite(lon) and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0

    @staticmethod
    def _normalize_longitude(longitude: float) -> float:
        normalized = float(longitude)
        while normalized >= 180.0:
            normalized -= 360.0
        while normalized < -180.0:
            normalized += 360.0
        return normalized

    @staticmethod
    def _rect_for_offset(
        anchor_x: float,
        anchor_y: float,
        text_width: float,
        text_height: float,
        offset: tuple[float, float],
    ) -> tuple[float, float, float, float]:
        center_x = anchor_x + offset[0]
        center_y = anchor_y + offset[1]
        return (
            center_x - text_width * 0.5,
            center_y - text_height * 0.5,
            center_x + text_width * 0.5,
            center_y + text_height * 0.5,
        )

    @staticmethod
    def _rect_collides(
        rect: tuple[float, float, float, float],
        occupied: Mapping[int, int],
    ) -> bool:
        _, _, min_cell_y, max_cell_y, column_mask = BattleEffectRenderer._rect_cell_coverage(rect)
        return any(
            occupied.get(cell_y, 0) & column_mask
            for cell_y in range(min_cell_y, max_cell_y + 1)
        )

    @staticmethod
    def _clamp_rect(
        rect: tuple[float, float, float, float],
        width: int,
        height: int,
    ) -> tuple[float, float, float, float]:
        left, top, right, bottom = rect
        rect_width = right - left
        rect_height = bottom - top
        left = max(0.0, min(float(width) - rect_width, left))
        top = max(0.0, min(float(height) - rect_height, top))
        return left, top, left + rect_width, top + rect_height

    @staticmethod
    def _occupy(
        rect: tuple[float, float, float, float],
        occupied: dict[int, int],
    ) -> None:
        # Row bitmasks conservatively detect shared screen cells without scanning stored label rectangles.
        min_cell_x, max_cell_x, min_cell_y, max_cell_y, column_mask = BattleEffectRenderer._rect_cell_coverage(rect)
        for cell_y in range(min_cell_y, max_cell_y + 1):
            occupied[cell_y] = occupied.get(cell_y, 0) | column_mask

    @staticmethod
    def _rect_cell_coverage(
        rect: tuple[float, float, float, float],
    ) -> tuple[int, int, int, int, int]:
        left, top, right, bottom = rect
        min_cell_x = math.floor(left / _GRID_CELL_SIZE)
        max_cell_x = math.floor(right / _GRID_CELL_SIZE)
        min_cell_y = math.floor(top / _GRID_CELL_SIZE)
        max_cell_y = math.floor(bottom / _GRID_CELL_SIZE)
        column_count = max_cell_x - min_cell_x + 1
        column_mask = ((1 << column_count) - 1) << min_cell_x
        return min_cell_x, max_cell_x, min_cell_y, max_cell_y, column_mask

    def _diagnose(self, kind: str, value: Any, revision: Any) -> None:
        key = (kind, str(value), revision)
        if key in self._diagnostic_keys:
            return
        self._diagnostic_keys.add(key)
        LOGGER.warning("Battle overlay isolated %s (%s) at revision %s", kind, value, revision)
