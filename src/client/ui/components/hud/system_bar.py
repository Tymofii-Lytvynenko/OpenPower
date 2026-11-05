"""REFERENCE system shortcuts rendered in their source GML coordinate slots."""
from __future__ import annotations

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.components.shared.gml_slide_transition import GMLSlideTransition
from src.client.ui.layouts.gml_layout import (
    create_gml_layout_session,
    get_gml_layout,
    gml_style,
    use_gml_layout,
)


class SystemBar:
    """Right-anchored 577x38 REFERENCE shortcut bar with its source collapse control."""

    _TEMPLATE = "System_Bar_Window"
    _COLLAPSED_WIDTH = 36.0

    def __init__(
        self,
        open_help_cb=None,
        open_objectives_cb=None,
        open_console_cb=None,
        open_history_cb=None,
        open_menu_cb=None,
        open_save_cb=None,
        open_load_cb=None,
    ) -> None:
        self._open_help_cb = open_help_cb
        self._open_objectives_cb = open_objectives_cb
        self._open_console_cb = open_console_cb
        self._open_history_cb = open_history_cb
        self._open_menu_cb = open_menu_cb
        self._open_save_cb = open_save_cb
        self._open_load_cb = open_load_cb
        self._expanded = True
        self._slide = GMLSlideTransition()
        self._slide_initialized = False
        self._expanded_width = 0.0
        self._collapsed_width = self._COLLAPSED_WIDTH

    def render(self, net_client, nav_service, hud_summary=None):
        self._consume_shortcuts(net_client, nav_service)

        viewport = imgui.get_main_viewport()
        source_layout = get_gml_layout(self._TEMPLATE)
        self._expanded_width = min(float(source_layout.width), float(viewport.size.x))
        self._collapsed_width = min(self._COLLAPSED_WIDTH, self._expanded_width)
        now = float(imgui.get_time())
        if not self._slide_initialized:
            self._slide.snap(self._expanded_width)
            self._slide_initialized = True
        else:
            self._slide.advance(now)
            if not self._slide.active:
                target = self._expanded_width if self._expanded else self._collapsed_width
                self._slide.snap(target)

        visible_width = self._slide.value
        x = float(viewport.pos.x + viewport.size.x - visible_width)
        y = float(viewport.pos.y)
        imgui.set_next_window_pos((x, y), imgui.Cond_.always)
        imgui.set_next_window_size((visible_width, float(source_layout.height)), imgui.Cond_.always)

        flags = (
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_saved_settings
            | imgui.WindowFlags_.no_scroll_with_mouse
            | imgui.WindowFlags_.no_background
        )

        with gml_style():
            imgui.push_style_var(imgui.StyleVar_.window_padding, (0.0, 0.0))
            opened, _ = imgui.begin("System_Bar", None, flags, test_id="hud.system_bar")
            imgui.pop_style_var()
            try:
                if not opened:
                    return
                position = imgui.get_window_pos()
                session = create_gml_layout_session(
                    self._TEMPLATE,
                    (float(position.x), float(position.y)),
                    (float(source_layout.width), float(source_layout.height)),
                )
                with use_gml_layout(session):
                    ui = GMLWidgets(self._TEMPLATE)
                    ui.frame("")
                    if self._render_toggle(ui):
                        return
                    if self._expanded or self._slide.active:
                        self._render_shortcuts(ui, net_client, nav_service)
            finally:
                imgui.end()

    def _render_toggle(self, ui: GMLWidgets) -> bool:
        changed, self._expanded = ui.toggle(
            "togMain",
            self._expanded,
            "hud.system.toggle",
            icon="‹" if self._expanded else "›",
            color=GAMETHEME.colors.accent,
            tooltip="Collapse system shortcuts" if self._expanded else "Expand system shortcuts",
        )
        if changed:
            target = self._expanded_width if self._expanded else self._collapsed_width
            self._slide.begin(target, float(imgui.get_time()))
        return changed

    def _render_shortcuts(self, ui: GMLWidgets, net_client, nav_service) -> None:
        shortcuts = (
            ("btnF1", "txtF1", "F1", "Help", "help", self._open_help_cb, True,
             "Open help"),
            # OpenPower has no multiplayer lobby route, so this source slot is explicitly unavailable.
            ("btnF2", "txtF2", "F2", "Chat", "chat", None, False,
             "Multiplayer lobby chat is unavailable in OpenPower"),
            ("btnF3", "txtF3", "F3", "Save", "save", lambda: self._show_save(net_client), True,
             "Save game"),
            ("btnF4", "txtF4", "F4", "Load", "load", lambda: self._show_load(nav_service, net_client), True,
             "Load saved game"),
            ("btnF5", "txtF5", "F5", "Objectives", "objectives", self._open_objectives_cb, True,
             "Scenario objectives"),
            ("btnF10", "txtF10", "F10", "Menu", "menu", lambda: self._toggle_menu(nav_service, net_client), True,
             "Main menu"),
        )
        style = imgui.get_style()
        font_scale = max(0.1, float(style.font_scale_main) * float(style.font_scale_dpi))
        for button_slot, label_slot, key, label, action_id, callback, enabled, tooltip in shortcuts:
            if ui.button(
                button_slot,
                key,
                f"hud.system.{action_id}",
                enabled=enabled,
                dynamic_enabled=True,
                tooltip=tooltip,
            ):
                self._safe_call(callback)
            # The source's 57 px captions use a 9 pt font; OpenPower's wider UI font needs a smaller logical size.
            imgui.push_font(None, 10.0 / font_scale)
            try:
                ui.text(
                    label_slot,
                    label,
                    color=GAMETHEME.colors.text_main if enabled else GAMETHEME.colors.text_dim,
                    test_id=f"hud.system.{action_id}.label",
                )
            finally:
                imgui.pop_font()

    def _consume_shortcuts(self, net_client, nav_service) -> None:
        if imgui.is_key_pressed(imgui.Key.f1, False):
            self._safe_call(self._open_help_cb)
        if imgui.is_key_pressed(imgui.Key.f3, False):
            self._show_save(net_client)
        if imgui.is_key_pressed(imgui.Key.f4, False):
            self._show_load(nav_service, net_client)
        if imgui.is_key_pressed(imgui.Key.f5, False):
            self._safe_call(self._open_objectives_cb)
        if imgui.is_key_pressed(imgui.Key.f6, False):
            self._safe_call(self._open_history_cb)
        if imgui.is_key_pressed(imgui.Key.f9, False):
            self._safe_call(self._open_console_cb)
        if imgui.is_key_pressed(imgui.Key.f10, False):
            self._toggle_menu(nav_service, net_client)

    def _toggle_menu(self, nav_service, net_client) -> None:
        if self._open_menu_cb is not None:
            self._open_menu_cb()
        else:
            self._show_menu(nav_service, net_client)

    def _show_load(self, nav_service, net_client) -> None:
        if self._open_load_cb is not None:
            self._open_load_cb()
            return
        session, config = self._resolve_session_and_config(nav_service, net_client)
        if session is None or config is None:
            return

        nav_service.show_load_game_screen(config)

    def _show_save(self, net_client) -> None:
        if self._open_save_cb is not None:
            self._open_save_cb()
        else:
            net_client.request_save()

    def _show_menu(self, nav_service, net_client) -> None:
        session, config = self._resolve_session_and_config(nav_service, net_client)
        if session is None or config is None:
            return

        nav_service.show_main_menu(session, config)

    def _resolve_session_and_config(self, nav_service, net_client):
        # The live GameConfig belongs to the window, not the client session
        # proxy. Resolving it here keeps menu navigation aligned with startup
        # configuration and avoids dereferencing a missing session field.
        session = getattr(net_client, "session", None)
        window = getattr(nav_service, "window", None)
        config = getattr(window, "game_config", None)
        if session is None or config is None:
            return None, None
        return session, config

    def _safe_call(self, callback) -> None:
        if callback is not None:
            callback()
