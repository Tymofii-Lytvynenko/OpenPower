from __future__ import annotations

from imgui_bundle import imgui


class SystemBar:
    def __init__(
        self,
        open_help_cb=None,
        open_objectives_cb=None,
        open_console_cb=None,
        open_mail_cb=None,
        open_news_cb=None,
    ):
        self._open_help_cb = open_help_cb
        self._open_objectives_cb = open_objectives_cb
        self._open_console_cb = open_console_cb
        self._open_mail_cb = open_mail_cb
        self._open_news_cb = open_news_cb

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
            button_specs = [
                ("F1 HELP", lambda: self._safe_call(self._open_help_cb)),
                ("F3 SAVE", lambda: net_client.request_save()),
                ("F4 LOAD", lambda: self._show_load(nav_service, net_client)),
                (f"F5 OBJ {hud_summary.active_objectives}", lambda: self._safe_call(self._open_objectives_cb)),
                (f"MAIL {hud_summary.unread_messages}", lambda: self._safe_call(self._open_mail_cb)),
                (f"NEWS {hud_summary.unread_news}", lambda: self._safe_call(self._open_news_cb)),
                ("F9 CON", lambda: self._safe_call(self._open_console_cb)),
                ("F10 MENU", lambda: self._show_menu(nav_service, net_client)),
            ]

            for index, (label, callback) in enumerate(button_specs):
                if index > 0:
                    imgui.same_line()

                if imgui.button(label):
                    callback()

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

    def _show_load(self, nav_service, net_client) -> None:
        if hasattr(net_client, "session"):
            nav_service.show_load_game_screen(net_client.session.config)

    def _show_menu(self, nav_service, net_client) -> None:
        if hasattr(net_client, "session"):
            nav_service.show_main_menu(net_client.session, net_client.session.config)

    def _safe_call(self, callback) -> None:
        if callback is not None:
            callback()
