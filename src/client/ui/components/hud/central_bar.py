"""Bottom command bar composed exclusively in Main_Bar source coordinates."""
from __future__ import annotations

from imgui_bundle import icons_fontawesome_6 as icons

from src.client.renderers.flag_renderer import FlagRenderer
from src.client.ui.components.hud.country_selector import (
    CountrySelector,
    CountryStatus,
    country_status_label,
)
from src.client.ui.components.hud.main_bar_geometry import main_bar_bounds
from src.client.ui.components.hud.sphere_metrics import main_bar_sphere_metrics
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives
from src.client.ui.layouts.gml_layout import (
    GMLRect, create_gml_layout_session, get_gml_layout, gml_child_frame,
    active_gml_layout, gml_style, use_gml_layout,
)
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused


class CentralBar:
    """Keep all fixed HUD fields in one coordinate system, including its background."""

    def __init__(self, open_ai_cb=None, open_statistics_cb=None, open_mail_cb=None,
                 open_news_cb=None, open_relations_cb=None, open_more_info_cb=None,
                 panel_visible_cb=None, open_locate_cb=None,
                 focus_country_cb=None) -> None:
        self.flag_renderer = FlagRenderer()
        self.country_selector = CountrySelector(self.flag_renderer)
        self._open_ai_cb = open_ai_cb
        self._open_statistics_cb = open_statistics_cb
        self._open_mail_cb = open_mail_cb
        self._open_news_cb = open_news_cb
        self._open_relations_cb = open_relations_cb
        self._open_more_info_cb = open_more_info_cb
        self._panel_visible_cb = panel_visible_cb
        self._open_locate_cb = open_locate_cb
        self._focus_country_cb = focus_country_cb
        self.show_speed_controls = False
        self.active_tag = ""
        self.country_status = CountryStatus.NEUTRAL
        self.is_own = False

    def render(self, state, net, target_tag, country_status, hud_summary):
        self.active_tag = target_tag
        self.country_status = country_status
        self.is_own = country_status is CountryStatus.PLAYER
        viewport = imgui.get_main_viewport()
        bounds = main_bar_bounds(viewport.size.x, viewport.size.y, viewport.pos.x, viewport.pos.y)
        imgui.set_next_window_pos((bounds.x, bounds.y))
        imgui.set_next_window_size((bounds.width, bounds.height))
        flags = (imgui.WindowFlags_.no_decoration | imgui.WindowFlags_.no_move
                 | imgui.WindowFlags_.no_scroll_with_mouse | imgui.WindowFlags_.no_background
                 | imgui.WindowFlags_.no_saved_settings)
        selected = None
        with gml_style():
            imgui.push_style_var(imgui.StyleVar_.window_padding, (0.0, 0.0))
            expanded, _ = imgui.begin("CentralBar", None, flags, test_id="hud.central_bar")
            imgui.pop_style_var()
            try:
                if expanded:
                    position, size = imgui.get_window_pos(), imgui.get_window_size()
                    # ImGui rounds window positions; share its actual origin with
                    # the flag and every bound field to keep pixel alignment exact.
                    actual = GMLRect(position.x, position.y, size.x, size.y)
                    session = create_gml_layout_session(
                        "Main_Bar", (actual.x, actual.y),
                        (get_gml_layout("Main_Bar").width, actual.height))
                    with use_gml_layout(session):
                        ui = GMLWidgets("Main_Bar")
                        self._render_background(actual, ui)
                        self._render_sphere_meters(state, ui)
                        self._render_country_section(state, ui)
                        self._render_quick_actions(hud_summary, ui)
                        self._render_time_section(state, net, ui)
                        self._render_ticker(hud_summary, ui)
                        selected = self.country_selector.render(state, self.active_tag)
            finally:
                imgui.end()
        return selected

    @staticmethod
    def _render_background(bounds, ui):
        draw = imgui.get_window_draw_list()
        news = ui.rect("frmNews")
        divider = news.y - 3.0
        draw.add_rect_filled((bounds.x, bounds.y), (bounds.x + bounds.width, bounds.y + bounds.height),
                             imgui.get_color_u32((0.055, 0.065, 0.065, 0.97)))
        draw.add_rect_filled((bounds.x, bounds.y + divider),
                             (bounds.x + bounds.width, bounds.y + bounds.height),
                             imgui.get_color_u32((0.025, 0.03, 0.03, 0.98)))
        draw.add_rect((bounds.x, bounds.y), (bounds.x + bounds.width, bounds.y + bounds.height),
                      imgui.get_color_u32((0.48, 0.50, 0.49, 1.0)), thickness=1.0)
        draw.add_line((bounds.x, bounds.y + divider),
                      (bounds.x + bounds.width, bounds.y + divider),
                      imgui.get_color_u32((0.38, 0.40, 0.39, 1.0)))

    def _render_sphere_meters(self, state, ui):
        metrics = main_bar_sphere_metrics(state, self.active_tag)
        colors = {
            "frmMeterPolitic": GAMETHEME.colors.politics,
            "frmMeterMilitary": GAMETHEME.colors.military,
            "frmMeterEconomic": GAMETHEME.colors.economy,
        }
        for slot, metric in metrics.items():
            value = metric.value
            ui.segmented_meter(
                slot,
                (value or 0.0) / 100.0,
                colors[slot],
                f"hud.{slot.removeprefix('frmMeter').lower()}",
                tooltip=(
                    f"{metric.label}: unavailable"
                    if value is None else f"{metric.label}: {value:.1f}%"
                ),
            )

    def _render_country_section(self, state, ui):
        slot = ui.rect("btnFlag")
        origin = active_gml_layout().window_position
        imgui.set_cursor_screen_pos((origin[0] + slot.x, origin[1] + slot.y))
        self.flag_renderer.draw_flag(self.active_tag, slot.width, slot.height)
        name = next((option.name for option in self.country_selector.options(state)
                     if option.tag == self.active_tag), self.active_tag)
        if ui.hitbox(
            "btnFlag",
            "hud.country_focus",
            enabled=bool(self.active_tag and self._focus_country_cb is not None),
            tooltip=f"Focus map on {name} ({self.active_tag})",
        ):
            self._focus_country_cb(self.active_tag)
        # Reserve padding and the caret inside the source country field.
        display = UIPrimitives.fit_text(name, ui.rect("cboCountry").width - 24.0)
        if ui.button("cboCountry", f"{display} {icons.ICON_FA_CARET_UP}", "hud.country",
                     tooltip=f"Select country: {name} ({self.active_tag})"):
            minimum, maximum = imgui.get_item_rect_min(), imgui.get_item_rect_max()
            self.country_selector.open((minimum.x, maximum.y), maximum.x - minimum.x)
        status_color = {
            CountryStatus.PLAYER: (76 / 255, 143 / 255, 69 / 255, 1.0),
            CountryStatus.ALLIANCE: (76 / 255, 143 / 255, 69 / 255, 1.0),
            CountryStatus.NEUTRAL: (168 / 255, 164 / 255, 64 / 255, 1.0),
            CountryStatus.HOSTILE: (143 / 255, 69 / 255, 69 / 255, 1.0),
            CountryStatus.MILITARY_ACCESS: (69 / 255, 107 / 255, 143 / 255, 1.0),
        }[self.country_status]
        imgui.push_style_color(imgui.Col_.button, status_color)
        status_text = country_status_label(self.country_status)
        status_description = self.country_status.value.replace("_", " ")
        ui.button(
            "btnStatus",
            status_text,
            "hud.country_status",
            tooltip=f"{status_description.title()}: {name} ({self.active_tag})",
        )
        imgui.pop_style_color()
        for slot, label, test_id, callback in (
            ("btnRelations", "RELATIONS", "hud.relations", self._open_relations_cb),
            ("btnMoreInfo", "MORE INFO", "hud.more_info", self._open_more_info_cb),
        ):
            if ui.button(slot, label, test_id, enabled=callback is not None):
                callback()

    def _render_quick_actions(self, summary, ui):
        for slot, icon, test_id, panel_id, callback, allowed, tooltip in (
            ("togAdvisor", icons.ICON_FA_BRAIN, "hud.advisor", "ADVISOR_SETTINGS",
             self._open_ai_cb, self.is_own, "Advisor preferences"),
            ("togHistory", icons.ICON_FA_CHART_LINE, "hud.history", "HISTORY",
             self._open_statistics_cb, True, "History & analytics"),
            ("togMail", icons.ICON_FA_ENVELOPE, "hud.mail", "MAIL",
             self._open_mail_cb, True, f"Messages ({summary.unread_messages} unread)"),
        ):
            is_open = bool(self._panel_visible_cb(panel_id)) if self._panel_visible_cb else False
            changed, _ = ui.toggle(
                slot, is_open, test_id, icon=icon, color=GAMETHEME.colors.accent,
                tooltip=tooltip, enabled=allowed and callback is not None,
            )
            if changed:
                callback()

    def _render_time_section(self, state, net, ui):
        if ui.button("btnTime", icons.ICON_FA_HOURGLASS_HALF, "hud.clock", tooltip="Time controls"):
            self.show_speed_controls = not self.show_speed_controls
        if self.show_speed_controls:
            self._draw_speed_controls(state, net, ui)
        else:
            date_text = net.get_display_date_text() or state.time.date_str
            date, _, time = date_text.partition(" ")
            color = (0.48, 1.0, 0.46, 1.0)
            ui.text("lblDate", date, color=color, right=True, test_id="hud.date")
            ui.text("lblTime", time, color=color, right=True, test_id="hud.time")

    def _draw_speed_controls(self, state, net, ui):
        # Preserve the five REFERENCE child slots; OpenPower speed 5 occupies the unused root-edge gutter.
        controls = (
            ("||", "hud.pause", (2.0, 2.0), state.time.is_paused, None),
            ("1", "hud.speed.1", (20.0, 2.0), state.time.speed_level == 1 and not state.time.is_paused, 1),
            ("2", "hud.speed.2", (38.0, 2.0), state.time.speed_level == 2 and not state.time.is_paused, 2),
            ("3", "hud.speed.3", (56.0, 2.0), state.time.speed_level == 3 and not state.time.is_paused, 3),
            ("4", "hud.speed.4", (74.0, 2.0), state.time.speed_level == 4 and not state.time.is_paused, 4),
            ("5", "hud.speed.5", (94.0, 2.0), state.time.speed_level == 5 and not state.time.is_paused, 5),
        )
        for label, test_id, offset, active, speed_level in controls:
            if active:
                imgui.push_style_color(imgui.Col_.button, (0.20, 0.43, 0.18, 1.0))
            clicked = ui.button_at("frmTimeSelection", label, test_id,
                                   offset=offset, size=(16.0, 18.0),
                                   padding=(0.0, 0.0))
            if active:
                imgui.pop_style_color()
            if clicked:
                if speed_level is None:
                    net.send_action(ActionSetPaused("local", not state.time.is_paused))
                else:
                    net.send_action(ActionSetPaused("local", False))
                    net.send_action(ActionSetGameSpeed("local", speed_level))

    def _render_ticker(self, summary, ui):
        # The ticker and its news button have independent, adjacent source slots.
        with gml_child_frame(
            ui.path("frmNews"), padding=(0.0, 0.0), bordered=False,
            window_flags=imgui.WindowFlags_.no_mouse_inputs,
        ) as opened:
            if opened:
                width = imgui.get_content_region_avail().x
                display = UIPrimitives.fit_text(summary.ticker_text, width)
                imgui.text_colored((0.74, 0.78, 0.74, 1.0), display, test_id="hud.ticker")
        # GML places btnLocate over frmNews with a one-pixel bleed on each edge.
        # Keep the exact source-sized target in the parent; a mouse-transparent
        # child lets the parent action receive clicks across that full rectangle.
        region_id = summary.ticker_region_id
        if ui.hitbox(
            "btnLocate",
            "hud.locate",
            enabled=region_id is not None and self._open_locate_cb is not None,
            tooltip=(
                "No map location for latest bulletin"
                if region_id is None else
                f"{summary.ticker_text}\n\nFocus the region linked to the latest bulletin"
            ),
        ) and region_id is not None:
            self._open_locate_cb(region_id)
        is_open = bool(self._panel_visible_cb("NEWS_LOG")) if self._panel_visible_cb else False
        changed, _ = ui.toggle(
            "togNews", is_open, "hud.news", icon=icons.ICON_FA_NEWSPAPER,
            color=GAMETHEME.colors.accent, tooltip="Event feed",
            enabled=self._open_news_cb is not None,
        )
        if changed:
            self._open_news_cb()
