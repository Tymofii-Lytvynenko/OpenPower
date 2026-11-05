from __future__ import annotations

import math
from dataclasses import dataclass

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import active_gml_layout, gml_child_frame
from src.client.ui.layouts.gml_rows import gml_row
from src.client.utils.diplomacy_utils import get_military_allies
from src.client.utils.gradient import get_heatmap_color
from src.client.visualization.map_modes.empire_mode import EmpireMapMode


@dataclass(frozen=True, slots=True)
class LegendCountry:
    tag: str
    name: str
    relation: float | None
    selected: bool


class ThematicMapLegend:
    """Render the map-mode key and country ranking from the current game state."""

    TEMPLATE = "Thematic_Map_Legend"
    WINDOW_ID = "map.legend.panel"
    WIDTH = 232
    HEIGHT = 163
    TOP = 40

    def __init__(self, viewport, *, flag_renderer=None):
        self.viewport = viewport
        self.flag_renderer = flag_renderer

    def render(self, state, player_tag: str) -> None:
        mode_key = str(getattr(self.viewport, "current_mode_key", "political"))
        mode = getattr(self.viewport, "map_modes", {}).get(mode_key)
        if mode is None or mode_key in {"political", "terrain"}:
            return

        imgui.push_style_color(imgui.Col_.window_bg, (100 / 255, 100 / 255, 100 / 255, 179 / 255))
        try:
            flags = (
                imgui.WindowFlags_.no_title_bar
                | imgui.WindowFlags_.no_move
                | imgui.WindowFlags_.no_resize
                | imgui.WindowFlags_.no_collapse
                | imgui.WindowFlags_.no_scrollbar
                | imgui.WindowFlags_.no_scroll_with_mouse
            )
            with WindowManager.window(
                "Thematic Map Legend",
                x=0,
                y=self.TOP,
                w=self.WIDTH,
                h=self.HEIGHT,
                closable=False,
                flags=flags,
                test_id=self.WINDOW_ID,
                gml_template=self.TEMPLATE,
                padding=(0.0, 0.0),
                horizontal_anchor="right",
                horizontal_margin=2.0,
                follow_position=True,
                fit_layout_width=True,
            ) as opened:
                if opened:
                    self._render_content(state, player_tag, mode_key, mode)
        finally:
            imgui.pop_style_color()

    def _render_content(self, state, player_tag: str, mode_key: str, mode) -> None:
        ui = GMLWidgets(self.TEMPLATE)
        selected_tag = self._selected_country_tag()
        title = str(getattr(mode, "name", mode_key))
        ui.text("txtTitle", title, font_size=9.0, test_id="map.legend.title")
        ui.text("txtTitle2", "RANK", font_size=9.0, test_id="map.legend.header.rank")
        ui.text("txtTitle3", "COUNTRY", font_size=9.0, test_id="map.legend.header.country")
        ui.text(
            "txtTitle1", "REL", font_size=9.0, test_id="map.legend.header.relations",
            tooltip="Relations with the selected country.",
        )

        ui.frame("frmLegend")
        if mode_key == "empire":
            self._draw_empire_key(ui)
            rows = self._empire_countries(state, selected_tag, player_tag)
        else:
            self._draw_gradient_key(ui, mode)
            rows = self._ranked_countries(state, player_tag, selected_tag, mode)

        with gml_child_frame(
            f"{self.TEMPLATE}/lstCountries",
            padding=(0.0, 0.0),
            bordered=False,
            test_id="map.legend.country_list",
        ) as opened:
            if not opened:
                return
            if not rows:
                message = "Select a country" if mode_key == "empire" else "No country data"
                ui.text_at(
                    "lstCountries", message, offset=(5.0, 6.0), max_width=126.0,
                    color=GAMETHEME.colors.text_dim, test_id="map.legend.empty",
                    font_size=9.0,
                )
                return
            for rank, row in enumerate(rows, start=1):
                with gml_row("lstThematicLegendItem", row.tag) as row_ui:
                    self._render_country_row(row_ui, row, rank)

    def _render_country_row(self, ui: GMLWidgets, row: LegendCountry, rank: int) -> None:
        test_id = f"map.legend.country.{row.tag}"
        start = imgui.get_cursor_screen_pos()
        if row.selected:
            imgui.get_window_draw_list().add_rect_filled(
                start,
                (start.x + 121.0, start.y + 15.0),
                imgui.get_color_u32((0.22, 0.36, 0.48, 0.65)),
            )
        clicked = imgui.invisible_button(
            f"{row.tag}###{test_id}", (121.0, 15.0), test_id=test_id,
        )
        hovered = imgui.is_item_hovered()
        if hovered and not row.selected:
            imgui.get_window_draw_list().add_rect_filled(
                start,
                (start.x + 121.0, start.y + 15.0),
                imgui.get_color_u32((0.25, 0.27, 0.30, 0.48)),
            )
        imgui.set_cursor_screen_pos(start)
        ui.text("txtRank", rank, font_size=9.0,
                test_id=f"map.legend.rank.{row.tag}")
        ui.picture(
            "frmCountry/picFlag",
            lambda width, height: self._draw_flag(row.tag, width, height),
        )
        ui.text(
            "frmCountry/txtCode", row.tag,
            font_size=9.0, test_id=f"map.legend.tag.{row.tag}", tooltip=row.name,
        )
        if row.relation is not None:
            ui.text(
                "frmCountry/lblRelations",
                f"{row.relation:.0f}", color=self._relation_color(row.relation),
                font_size=9.0, test_id=f"map.legend.relation.{row.tag}",
                tooltip=f"Relations with {row.name}.", right=True,
            )
        if hovered:
            imgui.set_tooltip(row.name)
        if clicked:
            focus = getattr(self.viewport, "focus_on_country", None)
            if focus is not None:
                focus(row.tag)

    def _draw_flag(self, tag: str, width: float, height: float) -> None:
        if self.flag_renderer is not None:
            self.flag_renderer.draw_flag(tag, width, height)
            return
        position = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()
        draw_list.add_rect_filled(
            position,
            (position.x + width, position.y + height),
            imgui.get_color_u32((0.34, 0.38, 0.44, 1.0)),
        )

    @staticmethod
    def _draw_gradient_key(ui: GMLWidgets, mode) -> None:
        steps = max(0, int(getattr(mode, "steps", 0) or 0))
        if steps > 1:
            levels = [math.floor(index / steps * steps) / steps for index in range(steps, -1, -1)]
        else:
            levels = [1.0 - index / 31.0 for index in range(32)]

        def draw(width: float, height: float) -> None:
            position = imgui.get_cursor_screen_pos()
            draw_list = imgui.get_window_draw_list()
            for index, value in enumerate(levels):
                top = position.y + height * index / len(levels)
                bottom = position.y + height * (index + 1) / len(levels)
                color = get_heatmap_color(value)
                normalized = tuple(channel / 255.0 for channel in color) + (1.0,)
                draw_list.add_rect_filled(
                    (position.x, top), (position.x + width, bottom),
                    imgui.get_color_u32(normalized),
                )
            draw_list.add_rect(
                position, (position.x + width, position.y + height),
                imgui.get_color_u32((0.7, 0.7, 0.7, 0.75)),
            )

        ui.picture("frmLegend/picGradient", draw)
        ui.text("frmLegend/lblTop", "HIGH", font_size=9.0, test_id="map.legend.key.high")
        ui.text("frmLegend/lblBottom", "LOW", font_size=9.0, test_id="map.legend.key.low")

    @staticmethod
    def _draw_empire_key(ui: GMLWidgets) -> None:
        entries = (
            ("ALLY", EmpireMapMode.ALLY),
            ("SELECTED", EmpireMapMode.SELECTED),
            ("ENEMY", EmpireMapMode.ENEMY),
            ("OCCUPIED", EmpireMapMode.OCCUPIED),
            ("CLAIM", EmpireMapMode.ANNEXATION_PENDING),
        )
        gradient = ui.rect("frmLegend/picGradient")
        session = active_gml_layout()
        origin = session.window_position
        x = origin[0] + gradient.x
        y = origin[1] + gradient.y
        width, height = gradient.width, gradient.height
        draw_list = imgui.get_window_draw_list()
        band_height = height / len(entries)
        for index, (label, color) in enumerate(entries):
            top = y + index * band_height
            draw_list.add_rect_filled(
                (x, top), (x + width, y + (index + 1) * band_height),
                imgui.get_color_u32(tuple(channel / 255.0 for channel in color[:3]) + (color[3] / 255.0,)),
            )
            ui.text_at(
                "frmLegend/lblTop", label,
                offset=(0.0, index * 24.0), max_width=55.0,
                font_size=9.0, test_id=f"map.legend.key.{label.lower()}",
            )
        draw_list.add_rect(
            (x, y), (x + width, y + height),
            imgui.get_color_u32((0.7, 0.7, 0.7, 0.75)),
        )

    def _ranked_countries(self, state, player_tag: str, selected_tag: str, mode) -> list[LegendCountry]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return []

        metric_values = self._country_metric_values(state, mode)
        if not any(value is not None for value in metric_values.values()):
            return []
        names = self._country_names(countries)
        relation_values = self._relation_values(state, player_tag)
        rows = []
        for row in countries.to_dicts():
            tag = self._normalize_tag(row.get("id"))
            value = metric_values.get(tag)
            if not tag or value is None or not self._is_active(row):
                continue
            rows.append((tag, names.get(tag, tag), value))
        rows.sort(key=lambda item: (-item[2], item[1].casefold(), item[0]))
        return [
            LegendCountry(tag, name, relation_values.get(tag), tag == selected_tag)
            for tag, name, _value in rows
        ]

    def _empire_countries(
        self, state, selected_tag: str, player_tag: str,
    ) -> list[LegendCountry]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns or not selected_tag:
            return []

        allowed = {selected_tag}
        allowed.update(self._normalize_tag(tag) for tag in get_military_allies(state, selected_tag))
        names = self._country_names(countries)
        relations = self._relation_values(state, player_tag)
        active = {
            self._normalize_tag(row.get("id"))
            for row in countries.to_dicts()
            if self._is_active(row)
        }
        visible = sorted(allowed & active, key=lambda tag: (tag != selected_tag, tag))
        return [
            LegendCountry(tag, names.get(tag, tag), relations.get(tag), tag == selected_tag)
            for tag in visible
        ]

    @staticmethod
    def _country_metric_values(state, mode) -> dict[str, float | None]:
        column = str(getattr(mode, "column_name", ""))
        countries = state.tables.get("countries")
        regions = state.tables.get("regions")
        if not column:
            return {}

        if regions is not None and column in regions.columns and "owner" in regions.columns:
            values: dict[str, list[float]] = {}
            for row in regions.to_dicts():
                owner = ThematicMapLegend._normalize_tag(row.get("owner"))
                value = ThematicMapLegend._finite_float(row.get(column))
                if owner and value is not None:
                    values.setdefault(owner, []).append(value)
            return {tag: sum(items) / len(items) for tag, items in values.items() if items}

        if countries is not None and column in countries.columns:
            return {
                ThematicMapLegend._normalize_tag(row.get("id")): ThematicMapLegend._finite_float(row.get(column))
                for row in countries.to_dicts()
                if ThematicMapLegend._normalize_tag(row.get("id"))
            }
        return {}

    @staticmethod
    def _country_names(countries) -> dict[str, str]:
        name_column = next(
            (column for column in ("name", "country_name", "display_name") if column in countries.columns),
            "id",
        )
        return {
            ThematicMapLegend._normalize_tag(row.get("id")): str(row.get(name_column) or row.get("id"))
            for row in countries.to_dicts()
            if ThematicMapLegend._normalize_tag(row.get("id"))
        }

    @staticmethod
    def _relation_values(state, source_tag: str) -> dict[str, float]:
        source_tag = ThematicMapLegend._normalize_tag(source_tag)
        relations = state.tables.get("countries_relations")
        required = {"source", "target", "value"}
        if not source_tag or relations is None or not required.issubset(relations.columns):
            return {}
        return {
            ThematicMapLegend._normalize_tag(row.get("target")): value
            for row in relations.to_dicts()
            if ThematicMapLegend._normalize_tag(row.get("source")) == source_tag
            and (value := ThematicMapLegend._finite_float(row.get("value"))) is not None
        }

    def _selected_country_tag(self) -> str:
        tag = getattr(self.viewport, "selected_country_tag", None)
        if tag is None:
            mode = getattr(self.viewport, "map_modes", {}).get("empire")
            tag = getattr(mode, "selected_country", None)
        return self._normalize_tag(tag)

    @staticmethod
    def _is_active(row: dict) -> bool:
        for column in ("is_active", "active"):
            if column in row and row[column] is not None:
                return bool(row[column])
        status = str(row.get("status") or "").strip().casefold()
        return status not in {"inactive", "eliminated", "unavailable", "dead"}

    @staticmethod
    def _normalize_tag(tag) -> str:
        normalized = str(tag or "").strip().upper()
        return "" if normalized == "NONE" else normalized

    @staticmethod
    def _finite_float(value) -> float | None:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) else None

    @staticmethod
    def _relation_color(value: float) -> tuple[float, float, float, float]:
        magnitude = min(1.0, abs(value) / 100.0)
        low, high = 25 / 255.0, 240 / 255.0
        if value > 0:
            return high - (high - low) * magnitude, high, low, 1.0
        return high, high - (high - low) * magnitude, low, 1.0
