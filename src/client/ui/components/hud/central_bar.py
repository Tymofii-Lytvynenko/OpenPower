from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from imgui_bundle import icons_fontawesome_6, imgui

from src.client.renderers.flag_renderer import FlagRenderer
from src.client.ui.components.hud.country_selector import (
    CountrySelector,
    CountryStatus,
    country_options_from_state,
)
from src.client.ui.core.theme import GAMETHEME
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused


@dataclass(frozen=True)
class HudMetrics:
    em: float
    outer_padding: float
    item_gap: float
    section_gap: float
    top_row_height: float
    tab_height: float
    content_height: float
    control_height: float
    ticker_height: float
    country_width: float
    flag_width: float
    country_button_width: float
    country_text_width: float
    status_width: float
    relations_width: float
    more_info_width: float
    action_button_width: float
    quick_actions_width: float
    clock_width: float
    lcd_width: float
    time_width: float
    speed_button_width: float
    ticker_button_size: float
    total_width: float
    total_height: float


class CentralBar:
    """Compact bottom HUD composed from measured ImGui controls."""

    AI_POPUP_ID = "AISettingsStubPopup"

    def __init__(
        self,
        open_ai_cb=None,
        open_statistics_cb=None,
        open_mail_cb=None,
        open_news_cb=None,
        open_relations_cb=None,
        open_more_info_cb=None,
    ) -> None:
        self.flag_renderer = FlagRenderer()
        self.country_selector = CountrySelector(self.flag_renderer)
        self._open_ai_cb = open_ai_cb
        self._open_statistics_cb = open_statistics_cb
        self._open_mail_cb = open_mail_cb
        self._open_news_cb = open_news_cb
        self._open_relations_cb = open_relations_cb
        self._open_more_info_cb = open_more_info_cb

        self.show_speed_controls = False
        self.active_tag = ""
        self.country_status = CountryStatus.NEUTRAL
        self.is_own = False
        self._switch_request: Optional[str] = None

    def render(
        self,
        state,
        net,
        target_tag: str,
        country_status: CountryStatus,
        hud_summary,
    ) -> Optional[str]:
        """Render the command bar and return a newly selected country tag."""
        self.active_tag = target_tag
        self.country_status = country_status
        self.is_own = country_status is CountryStatus.PLAYER
        self._switch_request = None

        country_name = self._country_name(state)
        date_parts = self._date_parts(state, net)
        metrics = self._measure_layout(date_parts)
        viewport = imgui.get_main_viewport()
        bar_width = self._bar_width(viewport.size.x, metrics)
        pos_x = viewport.pos.x + (viewport.size.x - bar_width) / 2.0
        pos_y = viewport.pos.y + viewport.size.y - metrics.total_height - metrics.outer_padding

        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((bar_width, metrics.total_height))
        imgui.push_style_var(imgui.StyleVar_.window_padding, (0.0, 0.0))

        flags = (
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_scroll_with_mouse
            | imgui.WindowFlags_.no_background
        )

        if imgui.begin("CentralBar", True, flags):
            try:
                self._render_background(bar_width, metrics)
                content_y = metrics.outer_padding

                country_x = metrics.outer_padding
                imgui.set_cursor_pos((country_x, content_y))
                self._render_country_section(country_name, metrics)

                quick_x = country_x + metrics.country_width + metrics.section_gap
                controls_y = content_y + (metrics.content_height - metrics.control_height) / 2.0
                imgui.set_cursor_pos((quick_x, controls_y))
                self._render_quick_actions(metrics, hud_summary)

                time_x = quick_x + metrics.quick_actions_width + metrics.section_gap
                imgui.set_cursor_pos((time_x, controls_y))
                self._render_time_section(state, net, date_parts, metrics)

                main_height = metrics.outer_padding * 2.0 + metrics.content_height
                imgui.set_cursor_pos((0.0, main_height))
                self._render_ticker(bar_width, metrics, hud_summary.ticker_text)

                self._switch_request = self.country_selector.render(state, self.active_tag)
            except Exception as exc:
                print(f"[CentralBar] Render Error: {exc}")
            finally:
                imgui.end()

        imgui.pop_style_var()
        return self._switch_request

    def _bar_width(self, viewport_width: float, metrics: HudMetrics) -> float:
        available_width = max(metrics.em, viewport_width - metrics.outer_padding * 2.0)
        return min(metrics.total_width, available_width)

    def _measure_layout(self, date_parts: tuple[str, str]) -> HudMetrics:
        em = max(1.0, imgui.get_font_size())
        style = imgui.get_style()
        outer_padding = em * 0.42
        item_gap = em * 0.22
        section_gap = em * 0.48
        compact_padding = em * 0.34

        top_row_height = max(
            imgui.get_text_line_height() + style.frame_padding.y * 2.0,
            em * 1.7,
        )
        tab_height = imgui.get_text_line_height() + em * 0.18
        content_height = top_row_height + tab_height
        date_block_height = imgui.get_text_line_height() * 2.0 + item_gap * 0.25
        control_height = max(top_row_height, date_block_height + outer_padding)

        news_icon_size = imgui.calc_text_size(icons_fontawesome_6.ICON_FA_NEWSPAPER)
        ticker_button_size = max(news_icon_size.x, news_icon_size.y) + compact_padding * 2.0
        ticker_height = max(
            imgui.get_text_line_height() + outer_padding,
            ticker_button_size + outer_padding * 0.5,
        )

        status_width = self._button_width(
            max(
                (status.value for status in CountryStatus),
                key=lambda label: imgui.calc_text_size(label).x,
            ),
            compact_padding,
        )
        relations_width = self._button_width("RELATIONS", compact_padding)
        more_info_width = self._button_width("MORE INFO", compact_padding)
        country_width = status_width + relations_width + more_info_width + item_gap * 2.0

        flag_width = top_row_height * 1.5
        country_button_width = country_width - flag_width - item_gap
        caret_width = imgui.calc_text_size(icons_fontawesome_6.ICON_FA_CARET_UP).x
        country_text_width = max(
            em,
            country_button_width - style.frame_padding.x * 2.0 - caret_width - item_gap,
        )

        action_icons = (
            icons_fontawesome_6.ICON_FA_BRAIN,
            icons_fontawesome_6.ICON_FA_CHART_LINE,
            icons_fontawesome_6.ICON_FA_ENVELOPE,
        )
        action_button_width = (
            max(imgui.calc_text_size(icon).x for icon in action_icons)
            + style.frame_padding.x * 2.0
        )
        quick_actions_width = action_button_width * len(action_icons) + item_gap * 2.0

        clock_width = (
            imgui.calc_text_size(icons_fontawesome_6.ICON_FA_HOURGLASS_HALF).x
            + style.frame_padding.x * 2.0
        )
        speed_button_width = (
            max(imgui.calc_text_size(label).x for label in ("||", "1", "2", "3", "4", "5"))
            + compact_padding * 2.0
        )
        speed_controls_width = speed_button_width * 6.0 + item_gap * 5.0
        visible_date_parts = tuple(part for part in date_parts if part) or ("N/A",)
        date_width = max(imgui.calc_text_size(part).x for part in visible_date_parts)
        lcd_width = max(speed_controls_width, date_width + style.frame_padding.x * 2.0)
        time_width = clock_width + item_gap + lcd_width

        total_width = (
            outer_padding * 2.0
            + country_width
            + section_gap
            + quick_actions_width
            + section_gap
            + time_width
        )
        total_height = outer_padding * 2.0 + content_height + ticker_height

        return HudMetrics(
            em=em,
            outer_padding=outer_padding,
            item_gap=item_gap,
            section_gap=section_gap,
            top_row_height=top_row_height,
            tab_height=tab_height,
            content_height=content_height,
            control_height=control_height,
            ticker_height=ticker_height,
            country_width=country_width,
            flag_width=flag_width,
            country_button_width=country_button_width,
            country_text_width=country_text_width,
            status_width=status_width,
            relations_width=relations_width,
            more_info_width=more_info_width,
            action_button_width=action_button_width,
            quick_actions_width=quick_actions_width,
            clock_width=clock_width,
            lcd_width=lcd_width,
            time_width=time_width,
            speed_button_width=speed_button_width,
            ticker_button_size=ticker_button_size,
            total_width=total_width,
            total_height=total_height,
        )

    def _button_width(self, label: str, horizontal_padding: float) -> float:
        return imgui.calc_text_size(label).x + horizontal_padding * 2.0

    def _country_name(self, state) -> str:
        for option in country_options_from_state(state):
            if option.tag == self.active_tag:
                return option.name
        return self.active_tag

    def _date_parts(self, state, net) -> tuple[str, str]:
        date_text = net.get_display_date_text() or state.time.date_str
        parts = date_text.split(" ", maxsplit=1)
        return parts[0] if parts else "N/A", parts[1] if len(parts) > 1 else ""

    def _ellipsize(self, text: str, max_width: float) -> str:
        if imgui.calc_text_size(text).x <= max_width:
            return text

        ellipsis = "..."
        if imgui.calc_text_size(ellipsis).x >= max_width:
            return ellipsis
        visible = text
        while visible and imgui.calc_text_size(f"{visible}{ellipsis}").x > max_width:
            visible = visible[:-1]
        return f"{visible.rstrip()}{ellipsis}"

    def _render_background(self, width: float, metrics: HudMetrics) -> None:
        draw_list = imgui.get_window_draw_list()
        origin = imgui.get_cursor_screen_pos()
        main_height = metrics.outer_padding * 2.0 + metrics.content_height
        bevel = max(1.0, metrics.em * 0.12)
        shadow_offset = metrics.em * 0.24

        shadow = (origin.x + shadow_offset, origin.y + shadow_offset)
        draw_list.add_rect_filled(
            shadow,
            (shadow[0] + width, shadow[1] + metrics.total_height),
            imgui.get_color_u32((0.0, 0.0, 0.0, 0.65)),
            bevel,
        )
        draw_list.add_rect_filled(
            origin,
            (origin.x + width, origin.y + main_height),
            imgui.get_color_u32((0.075, 0.085, 0.085, 0.97)),
            bevel,
            imgui.ImDrawFlags_.round_corners_top,
        )
        draw_list.add_rect_filled(
            (origin.x, origin.y + main_height),
            (origin.x + width, origin.y + metrics.total_height),
            imgui.get_color_u32((0.025, 0.03, 0.03, 0.98)),
            bevel,
            imgui.ImDrawFlags_.round_corners_bottom,
        )
        draw_list.add_rect(
            origin,
            (origin.x + width, origin.y + metrics.total_height),
            imgui.get_color_u32((0.48, 0.50, 0.49, 1.0)),
            bevel,
            0,
            bevel,
        )
        draw_list.add_line(
            (origin.x + bevel, origin.y + main_height),
            (origin.x + width - bevel, origin.y + main_height),
            imgui.get_color_u32((0.38, 0.40, 0.39, 1.0)),
            max(1.0, bevel * 0.6),
        )

    def _render_country_section(self, country_name: str, metrics: HudMetrics) -> None:
        section_local_x = imgui.get_cursor_pos_x()
        section_screen_pos = imgui.get_cursor_screen_pos()
        self.flag_renderer.draw_flag(
            self.active_tag,
            metrics.flag_width,
            metrics.top_row_height,
        )
        imgui.same_line(0.0, metrics.item_gap)

        display_name = self._ellipsize(country_name, metrics.country_text_width)
        button_label = f"{display_name} {icons_fontawesome_6.ICON_FA_CARET_UP}##country"
        imgui.push_style_color(imgui.Col_.button, (0.20, 0.21, 0.21, 1.0))
        imgui.push_style_color(imgui.Col_.button_hovered, (0.30, 0.32, 0.31, 1.0))
        if imgui.button(button_label, (metrics.country_button_width, metrics.top_row_height)):
            self.country_selector.open(
                (section_screen_pos.x, section_screen_pos.y),
                metrics.country_width,
            )
        imgui.pop_style_color(2)
        if imgui.is_item_hovered():
            imgui.set_tooltip(f"Select country ({self.active_tag})")

        imgui.set_cursor_pos_x(section_local_x)
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (metrics.item_gap, 0.0))
        imgui.push_style_var(
            imgui.StyleVar_.frame_padding,
            (metrics.em * 0.34, metrics.em * 0.04),
        )
        status_color = {
            CountryStatus.PLAYER: (0.20, 0.43, 0.18, 1.0),
            CountryStatus.ALLIANCE: (0.18, 0.35, 0.52, 1.0),
            CountryStatus.NEUTRAL: (0.29, 0.30, 0.29, 1.0),
        }[self.country_status]
        self._draw_status_label(
            self.country_status.value,
            status_color,
            metrics.status_width,
            metrics.tab_height,
        )
        imgui.same_line()
        if imgui.button("RELATIONS", (metrics.relations_width, metrics.tab_height)):
            if self._open_relations_cb:
                self._open_relations_cb()
        imgui.same_line()
        if imgui.button("MORE INFO", (metrics.more_info_width, metrics.tab_height)):
            if self._open_more_info_cb:
                self._open_more_info_cb()
        imgui.pop_style_var(2)

    def _render_quick_actions(self, metrics: HudMetrics, hud_summary) -> None:
        button_size = (metrics.action_button_width, metrics.control_height)
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (metrics.item_gap, 0.0))
        imgui.push_style_color(imgui.Col_.button, (0.11, 0.12, 0.12, 1.0))

        if not self.is_own:
            imgui.begin_disabled()
        ai_clicked = imgui.button(icons_fontawesome_6.ICON_FA_BRAIN, button_size)
        if not self.is_own:
            imgui.end_disabled()
        if ai_clicked:
            if self._open_ai_cb:
                self._open_ai_cb()
            else:
                imgui.open_popup(self.AI_POPUP_ID)
        if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
            tooltip = (
                "AI delegation settings (coming soon)"
                if self.is_own
                else "AI delegation is available for the player country"
            )
            imgui.set_tooltip(tooltip)

        imgui.same_line()
        if imgui.button(icons_fontawesome_6.ICON_FA_CHART_LINE, button_size):
            if self._open_statistics_cb:
                self._open_statistics_cb()
        if imgui.is_item_hovered():
            imgui.set_tooltip("Statistics")

        imgui.same_line()
        if imgui.button(icons_fontawesome_6.ICON_FA_ENVELOPE, button_size):
            if self._open_mail_cb:
                self._open_mail_cb()
        if imgui.is_item_hovered():
            imgui.set_tooltip(f"Messages ({hud_summary.unread_messages} unread)")

        imgui.pop_style_color()
        imgui.pop_style_var()
        self._render_ai_stub()

    def _render_ai_stub(self) -> None:
        if not imgui.begin_popup(self.AI_POPUP_ID):
            return

        imgui.text("AI DELEGATION")
        imgui.separator()
        imgui.text_disabled("Choose which player-country areas AI may manage.")
        imgui.begin_disabled()
        for label in ("Economy", "Diplomacy", "Military", "Research"):
            imgui.checkbox(f"{label}##ai-delegation", False)
        imgui.end_disabled()
        imgui.text_disabled("Coming soon")
        imgui.end_popup()

    def _render_time_section(
        self,
        state,
        net,
        date_parts: tuple[str, str],
        metrics: HudMetrics,
    ) -> None:
        imgui.push_style_color(imgui.Col_.button, (0.11, 0.12, 0.12, 1.0))
        if imgui.button(
            icons_fontawesome_6.ICON_FA_HOURGLASS_HALF,
            (metrics.clock_width, metrics.control_height),
        ):
            self.show_speed_controls = not self.show_speed_controls
        imgui.pop_style_color()

        imgui.same_line(0.0, metrics.item_gap)
        screen_pos = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()
        border_width = max(1.0, metrics.em * 0.1)
        draw_list.add_rect_filled(
            screen_pos,
            (screen_pos.x + metrics.lcd_width, screen_pos.y + metrics.control_height),
            imgui.get_color_u32((0.008, 0.025, 0.012, 0.98)),
        )
        draw_list.add_rect(
            screen_pos,
            (screen_pos.x + metrics.lcd_width, screen_pos.y + metrics.control_height),
            imgui.get_color_u32((0.40, 0.43, 0.40, 1.0)),
            0.0,
            0,
            border_width,
        )

        imgui.begin_child(
            "TimeScreen",
            (metrics.lcd_width, metrics.control_height),
            False,
            imgui.WindowFlags_.no_background,
        )
        if self.show_speed_controls:
            self._draw_speed_controls(state, net, metrics)
        else:
            self._draw_date_display(date_parts, metrics)
        imgui.end_child()

    def _draw_speed_controls(self, state, net, metrics: HudMetrics) -> None:
        button_height = metrics.tab_height
        total_width = metrics.speed_button_width * 6.0 + metrics.item_gap * 5.0
        start_x = (metrics.lcd_width - total_width) / 2.0
        start_y = (metrics.control_height - button_height) / 2.0
        imgui.set_cursor_pos((start_x, start_y))

        current_speed = getattr(state.time, "speed_level", 1)
        is_paused = getattr(state.time, "is_paused", False)
        button_size = (metrics.speed_button_width, button_height)
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (metrics.item_gap, 0.0))
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (0.0, 0.0))
        imgui.push_style_var(imgui.StyleVar_.frame_rounding, 0.0)

        if is_paused:
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.interaction_active)
            imgui.push_style_color(imgui.Col_.button_hovered, GAMETHEME.colors.interaction_active)
        if imgui.button("||", button_size):
            net.send_action(ActionSetPaused("local", not is_paused))
        if is_paused:
            imgui.pop_style_color(2)

        for speed in range(1, 6):
            imgui.same_line()
            is_active = current_speed == speed and not is_paused
            if is_active:
                imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.interaction_active)
                imgui.push_style_color(imgui.Col_.button_hovered, GAMETHEME.colors.interaction_active)
            if imgui.button(str(speed), button_size):
                net.send_action(ActionSetPaused("local", False))
                net.send_action(ActionSetGameSpeed("local", speed))
            if is_active:
                imgui.pop_style_color(2)

        imgui.pop_style_var(3)

    def _draw_date_display(self, date_parts: tuple[str, str], metrics: HudMetrics) -> None:
        date_part, time_part = date_parts
        line_height = imgui.get_text_line_height()
        gap = metrics.item_gap * 0.25
        line_count = 2 if time_part else 1
        block_height = line_height * line_count + (gap if time_part else 0.0)
        start_y = (metrics.control_height - block_height) / 2.0
        imgui.set_cursor_pos(
            (
                (metrics.lcd_width - imgui.calc_text_size(date_part).x) / 2.0,
                start_y,
            )
        )
        lcd_green = (0.48, 1.0, 0.46, 1.0)
        imgui.text_colored(lcd_green, date_part)
        if time_part:
            imgui.set_cursor_pos_x(
                (metrics.lcd_width - imgui.calc_text_size(time_part).x) / 2.0
            )
            imgui.set_cursor_pos_y(start_y + line_height + gap)
            imgui.text_colored(lcd_green, time_part)

    def _render_ticker(self, width: float, metrics: HudMetrics, ticker_text: str) -> None:
        current_y = imgui.get_cursor_pos_y()
        text_y = (metrics.ticker_height - imgui.get_text_line_height()) / 2.0
        text_width = max(
            metrics.em,
            width
            - metrics.ticker_button_size
            - metrics.outer_padding * 3.0,
        )
        imgui.set_cursor_pos((metrics.outer_padding, current_y))
        imgui.begin_child(
            "TickerText",
            (text_width, metrics.ticker_height),
            False,
            imgui.WindowFlags_.no_background
            | imgui.WindowFlags_.no_scrollbar
            | imgui.WindowFlags_.no_scroll_with_mouse,
        )
        imgui.set_cursor_pos((0.0, text_y))
        imgui.text_colored((0.74, 0.78, 0.74, 1.0), ticker_text)
        imgui.end_child()

        button_size = metrics.ticker_button_size
        imgui.set_cursor_pos(
            (
                width - button_size - metrics.outer_padding,
                current_y + (metrics.ticker_height - button_size) / 2.0,
            )
        )
        imgui.push_style_color(imgui.Col_.button, (0.09, 0.10, 0.10, 1.0))
        if imgui.button(icons_fontawesome_6.ICON_FA_NEWSPAPER, (button_size, button_size)):
            if self._open_news_cb:
                self._open_news_cb()
        imgui.pop_style_color()
        if imgui.is_item_hovered():
            imgui.set_tooltip("Event feed")

    def _draw_status_label(
        self,
        label: str,
        color: tuple,
        width: float,
        height: float,
    ) -> None:
        imgui.push_style_color(imgui.Col_.button, color)
        imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_main)
        imgui.push_style_var(imgui.StyleVar_.frame_rounding, 0.0)
        imgui.button(label, (width, height))
        imgui.pop_style_var()
        imgui.pop_style_color(2)
