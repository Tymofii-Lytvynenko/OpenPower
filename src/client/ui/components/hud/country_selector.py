from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.client.ui.core.instrumented_imgui import imgui

from src.client.renderers.flag_renderer import FlagRenderer
from src.client.ui.core.theme import GAMETHEME
from src.client.utils.diplomacy_utils import get_military_allies


@dataclass(frozen=True)
class CountryOption:
    tag: str
    name: str


class CountryStatus(Enum):
    PLAYER = "PLAYER"
    NEUTRAL = "NEUTRAL"
    ALLIANCE = "ALLIANCE"


def resolve_country_status(state, player_tag: str, target_tag: str) -> CountryStatus:
    if target_tag == player_tag:
        return CountryStatus.PLAYER
    if target_tag in get_military_allies(state, player_tag):
        return CountryStatus.ALLIANCE
    return CountryStatus.NEUTRAL


def country_options_from_state(state) -> tuple[CountryOption, ...]:
    """Return stable, user-facing country options from a game snapshot."""
    tables = getattr(state, "tables", {})
    countries = tables.get("countries")
    if countries is None:
        return ()

    options_by_tag: dict[str, CountryOption] = {}
    columns = [name for name in ("id", "name", "display_name") if name in countries.columns]
    for row in countries.select(columns).iter_rows(named=True):
        raw_tag = row.get("id")
        tag = "" if raw_tag is None else str(raw_tag).strip()
        if not tag:
            continue

        raw_name = row.get("name") or row.get("display_name") or tag
        name = str(raw_name).strip() or tag
        options_by_tag.setdefault(tag, CountryOption(tag=tag, name=name))

    return tuple(
        sorted(options_by_tag.values(), key=lambda option: (option.name.casefold(), option.tag))
    )


class CountrySelector:
    """Popup country picker anchored above the HUD country panel."""

    POPUP_ID = "CountrySelectorPopup"
    MAX_VISIBLE_ROWS = 10

    def __init__(self, flag_renderer: FlagRenderer | None = None) -> None:
        self.flag_renderer = flag_renderer or FlagRenderer()
        self._anchor = (0.0, 0.0)
        self._width = 0.0

    def open(self, anchor: tuple[float, float], width: float) -> None:
        self._anchor = anchor
        self._width = width
        imgui.open_popup(self.POPUP_ID)

    def render(self, state, active_tag: str) -> str | None:
        options = country_options_from_state(state)
        em = imgui.get_font_size()
        padding = em * 0.22
        item_gap = em * 0.08
        row_height = imgui.get_text_line_height() + em * 0.42
        popup_x, popup_bottom = self._anchor
        viewport = imgui.get_main_viewport()
        available_height = max(
            row_height * 3.0,
            popup_bottom - viewport.pos.y - em * 0.5,
        )
        natural_height = max(
            row_height * 2.0,
            min(len(options), self.MAX_VISIBLE_ROWS) * (row_height + item_gap)
            + padding * 2.0,
        )
        popup_height = min(natural_height, available_height)

        imgui.set_next_window_pos(
            (popup_x, popup_bottom - popup_height - item_gap),
            imgui.Cond_.appearing,
        )
        imgui.set_next_window_size((self._width, popup_height), imgui.Cond_.appearing)
        imgui.push_style_var(imgui.StyleVar_.window_padding, (padding, padding))
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (0.0, item_gap))
        imgui.push_style_var(imgui.StyleVar_.popup_rounding, 0.0)
        imgui.push_style_var(imgui.StyleVar_.window_border_size, max(1.0, em * 0.12))
        imgui.push_style_color(imgui.Col_.popup_bg, (0.055, 0.06, 0.065, 0.98))
        imgui.push_style_color(imgui.Col_.border, (0.42, 0.45, 0.46, 1.0))
        imgui.push_style_color(imgui.Col_.header, (0.20, 0.22, 0.22, 1.0))
        imgui.push_style_color(imgui.Col_.header_hovered, (0.32, 0.35, 0.34, 1.0))
        imgui.push_style_color(imgui.Col_.header_active, (0.18, 0.40, 0.18, 1.0))

        selected_tag = None
        if imgui.begin_popup(self.POPUP_ID, imgui.WindowFlags_.no_move):
            if options:
                for option in options:
                    imgui.push_id(option.tag)
                    is_selected = option.tag == active_tag

                    flag_height = row_height * 0.75
                    self.flag_renderer.draw_flag(option.tag, flag_height * 1.5, flag_height)
                    flag_clicked = imgui.is_item_clicked()
                    imgui.same_line(0.0, padding)
                    row_clicked = imgui.selectable(
                        f"{option.name}##country",
                        is_selected,
                        0,
                        (0.0, row_height),
                    )[0]
                    if is_selected:
                        imgui.set_item_default_focus()
                    if imgui.is_item_hovered():
                        imgui.set_tooltip(option.tag)

                    if flag_clicked or row_clicked:
                        selected_tag = option.tag
                        imgui.close_current_popup()
                    imgui.pop_id()
            else:
                imgui.text_colored(GAMETHEME.colors.error, "No country data loaded")

            imgui.end_popup()

        imgui.pop_style_color(5)
        imgui.pop_style_var(4)
        return selected_tag
