from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from imgui_bundle import imgui, icons_fontawesome_6


@dataclass(frozen=True, slots=True)
class SystemBarAction:
    id: str
    icon: str
    tooltip: str
    callback: Callable[[], None]
    shortcut: str = ""
    badge: int | None = None


class SystemBar:
    def __init__(
        self,
        open_help_cb=None,
        open_objectives_cb=None,
        open_console_cb=None,
        open_mail_cb=None,
        open_news_cb=None,
        open_settings_cb=None,
    ):
        self._open_help_cb = open_help_cb
        self._open_objectives_cb = open_objectives_cb
        self._open_console_cb = open_console_cb
        self._open_mail_cb = open_mail_cb
        self._open_news_cb = open_news_cb
        self._open_settings_cb = open_settings_cb

    def render(self, net_client, nav_service, hud_summary):
        self._consume_shortcuts(net_client, nav_service)

        viewport = imgui.get_main_viewport()
        pad_x, pad_y = 10.0, 10.0

        imgui.set_next_window_pos(
            imgui.ImVec2(viewport.size.x - pad_x, pad_y),
            imgui.Cond_.always,
            imgui.ImVec2(1.0, 0.0),
        )

        flags = (
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.always_auto_resize
            | imgui.WindowFlags_.no_background
        )

        if imgui.begin("##System_Bar", True, flags):
            self._render_actions(self._build_actions(net_client, nav_service, hud_summary))
            imgui.end()

    def _consume_shortcuts(self, net_client, nav_service) -> None:
        if imgui.is_key_pressed(imgui.Key.f1, False):
            self._safe_call(self._open_help_cb)
        if imgui.is_key_pressed(imgui.Key.f3, False):
            net_client.request_save()
        if imgui.is_key_pressed(imgui.Key.f4, False):
            self._show_load(nav_service, net_client)
        if imgui.is_key_pressed(imgui.Key.f5, False):
            self._safe_call(self._open_objectives_cb)
        if imgui.is_key_pressed(imgui.Key.f9, False):
            self._safe_call(self._open_console_cb)
        if imgui.is_key_pressed(imgui.Key.f10, False):
            self._show_menu(nav_service, net_client)

    def _build_actions(self, net_client, nav_service, hud_summary) -> list[SystemBarAction]:
        return [
            SystemBarAction(
                id="help",
                icon=icons_fontawesome_6.ICON_FA_CIRCLE_QUESTION,
                tooltip="Help",
                shortcut="F1",
                callback=lambda: self._safe_call(self._open_help_cb),
            ),
            SystemBarAction(
                id="save",
                icon=icons_fontawesome_6.ICON_FA_FLOPPY_DISK,
                tooltip="Save",
                shortcut="F3",
                callback=lambda: net_client.request_save(),
            ),
            SystemBarAction(
                id="load",
                icon=icons_fontawesome_6.ICON_FA_FOLDER_OPEN,
                tooltip="Load",
                shortcut="F4",
                callback=lambda: self._show_load(nav_service, net_client),
            ),
            SystemBarAction(
                id="objectives",
                icon=icons_fontawesome_6.ICON_FA_BULLSEYE,
                tooltip="Objectives",
                shortcut="F5",
                callback=lambda: self._safe_call(self._open_objectives_cb),
                badge=hud_summary.active_objectives,
            ),
            SystemBarAction(
                id="mail",
                icon=icons_fontawesome_6.ICON_FA_ENVELOPE,
                tooltip="Mail",
                callback=lambda: self._safe_call(self._open_mail_cb),
                badge=hud_summary.unread_messages,
            ),
            SystemBarAction(
                id="news",
                icon=icons_fontawesome_6.ICON_FA_NEWSPAPER,
                tooltip="News",
                callback=lambda: self._safe_call(self._open_news_cb),
                badge=hud_summary.unread_news,
            ),
            SystemBarAction(
                id="console",
                icon=icons_fontawesome_6.ICON_FA_TERMINAL,
                tooltip="Console",
                shortcut="F9",
                callback=lambda: self._safe_call(self._open_console_cb),
            ),
            SystemBarAction(
                id="settings",
                icon=icons_fontawesome_6.ICON_FA_GEAR,
                tooltip="Settings",
                callback=lambda: self._safe_call(self._open_settings_cb),
            ),
            SystemBarAction(
                id="menu",
                icon=icons_fontawesome_6.ICON_FA_HOUSE,
                tooltip="Main menu",
                shortcut="F10",
                callback=lambda: self._show_menu(nav_service, net_client),
            ),
        ]

    def _render_actions(self, actions: list[SystemBarAction]) -> None:
        for index, action in enumerate(actions):
            if index > 0:
                imgui.same_line()

            label = self._button_label(action)
            if imgui.button(label, (self._button_width(action), 30)):
                action.callback()

            if imgui.is_item_hovered():
                tooltip = action.tooltip
                if action.shortcut:
                    tooltip = f"{tooltip} ({action.shortcut})"
                imgui.set_tooltip(tooltip)

    def _button_label(self, action: SystemBarAction) -> str:
        badge = "" if not action.badge else f" {action.badge}"
        return f"{action.icon}{badge}##{action.id}"

    def _button_width(self, action: SystemBarAction) -> float:
        if not action.badge:
            return 34.0
        return 42.0 + (8.0 * max(0, len(str(action.badge)) - 1))

    def _show_load(self, nav_service, net_client) -> None:
        if hasattr(net_client, "session"):
            nav_service.show_load_game_screen(net_client.session.config)

    def _show_menu(self, nav_service, net_client) -> None:
        if hasattr(net_client, "session"):
            nav_service.show_main_menu(net_client.session, net_client.session.config)

    def _safe_call(self, callback) -> None:
        if callback is not None:
            callback()
