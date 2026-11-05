from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.layouts.gml_layout import active_gml_layout, gml_child_frame


@dataclass(frozen=True, slots=True)
class MultiplayerServerInfo:
    name: str
    ip_address: str
    players: int
    max_players: int
    mod_name: str
    scenario_name: str
    password_required: bool = False


@dataclass(frozen=True, slots=True)
class _InputRequest:
    message: str
    on_submit: Callable[[str], None]
    on_cancel: Callable[[], None] | None
    initial_value: str
    password: bool


class GenericInputDialog:
    """Reusable input prompt that keeps the caller acknowledgement one-shot."""

    def __init__(self) -> None:
        self._request: _InputRequest | None = None
        self._value = ""
        self._focus_requested = False

    @property
    def is_open(self) -> bool:
        return self._request is not None

    def show(
        self,
        message: str,
        on_submit: Callable[[str], None],
        on_cancel: Callable[[], None] | None = None,
        *,
        initial_value: str = "",
        password: bool = False,
    ) -> bool:
        prompt = str(message or "").strip()
        if self.is_open or not prompt:
            return False
        self._request = _InputRequest(
            prompt, on_submit, on_cancel, str(initial_value or ""), bool(password)
        )
        self._value = self._request.initial_value
        self._focus_requested = True
        return True

    def close(self, *, submit: bool) -> None:
        request = self._request
        value = self._value
        self._request = None
        self._value = ""
        self._focus_requested = False
        if request is None:
            return
        if submit:
            request.on_submit(value)
        elif request.on_cancel is not None:
            request.on_cancel()

    def render(self, screen_width: float, screen_height: float) -> bool:
        request = self._request
        if request is None:
            return False

        width, height = 301.0, 62.0
        opened = True
        flags = (
            imgui.WindowFlags_.no_title_bar
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_collapse
            | imgui.WindowFlags_.no_scrollbar
            | imgui.WindowFlags_.no_scroll_with_mouse
        )
        with WindowManager.window(
            "##generic_input_window",
            x=(screen_width - width) / 2.0,
            y=(screen_height - height) / 2.0,
            w=width,
            h=height,
            closable=False,
            flags=flags,
            padding=(0.0, 0.0),
            size_override=(width, height),
            test_id="multiplayer.input.dialog",
            gml_template="Generic_Input_Window",
            follow_position=True,
        ) as opened:
            if opened:
                ui = GMLWidgets("Generic_Input_Window")
                ui.text("lblMessage", request.message, tooltip=request.message)
                if self._focus_requested:
                    imgui.set_keyboard_focus_here()
                    self._focus_requested = False
                flags = (
                    imgui.InputTextFlags_.password
                    if request.password else imgui.InputTextFlags_.none
                )
                _, self._value = imgui.input_text(
                    "##generic-input-answer",
                    self._value,
                    int(flags),
                    test_id="multiplayer.input.answer",
                    gml_id=ui.path("edtAnswer"),
                )
                if ui.button("btnOk", "OK", "multiplayer.input.ok"):
                    self.close(submit=True)
                if ui.button("btnCancel", "CANCEL", "multiplayer.input.cancel"):
                    self.close(submit=False)

        return self.is_open


class ServerInfoWindow:
    """Read-only server details using the source information slots."""

    def __init__(self) -> None:
        self._open = False
        self._server: MultiplayerServerInfo | None = None
        self._on_join: Callable[[], None] | None = None

    @property
    def is_open(self) -> bool:
        return self._open

    def show(
        self,
        server: MultiplayerServerInfo | None,
        on_join: Callable[[], None] | None = None,
    ) -> None:
        self._server = server
        self._on_join = on_join
        self._open = True

    def close(self) -> None:
        self._open = False
        self._server = None
        self._on_join = None

    def render(self, screen_width: float, screen_height: float) -> bool:
        if not self._open:
            return False

        width, height = 346.0, 179.0
        is_open = True
        with WindowManager.window(
            "SERVER INFO",
            x=(screen_width - width) / 2.0,
            y=(screen_height - height) / 2.0,
            w=width,
            h=height,
            test_id="multiplayer.server_info.dialog",
            gml_template="Server_Info_Window",
            follow_position=True,
        ) as is_open:
            if is_open:
                self._render_content()
        if not is_open:
            self.close()
        return self._open

    def _render_content(self) -> None:
        ui = GMLWidgets("Server_Info_Window")
        server = self._server
        unavailable = "Unavailable"
        ui.text("frmInner/frmInfo/lblName", "SERVER NAME")
        ui.text("frmInner/frmInfo/lblIp", "IP ADDRESS")
        ui.text("frmInner/frmInfo/lblName3", "PLAYERS")
        ui.text("frmInner/frmInfo/lblMod", "MOD")
        ui.text("frmInner/frmInfo/lblScenario", "SCENARIO")
        ui.text("frmInner/frmInfo/lblPassword", "PASSWORD")
        ui.text("frmInner/frmInfo/txtName", server.name if server else unavailable,
                test_id="multiplayer.server_info.name")
        ui.text("frmInner/frmInfo/txtIpAddress", server.ip_address if server else unavailable,
                test_id="multiplayer.server_info.address")
        ui.text(
            "frmInner/frmInfo/txtPlayers",
            f"{server.players}/{server.max_players}" if server else unavailable,
            test_id="multiplayer.server_info.players",
        )
        ui.text("frmInner/frmInfo/txtMods", server.mod_name if server else unavailable,
                test_id="multiplayer.server_info.mod")
        ui.text(
            "frmInner/frmInfo/txtScenario",
            server.scenario_name if server else unavailable,
            test_id="multiplayer.server_info.scenario",
        )

        password_slot = ui.rect("frmInner/frmInfo/togPassword")
        session = active_gml_layout()
        if password_slot is not None and session is not None:
            x = session.window_position[0] + password_slot.x
            y = session.window_position[1] + password_slot.y
            draw_list = imgui.get_window_draw_list()
            draw_list.add_rect(
                (x, y), (x + password_slot.width, y + password_slot.height),
                imgui.get_color_u32((0.6, 0.62, 0.64, 1.0)),
            )
            if server is not None and server.password_required:
                draw_list.add_rect_filled(
                    (x + 2.0, y + 2.0),
                    (x + max(3.0, password_slot.width - 2.0),
                     y + max(3.0, password_slot.height - 2.0)),
                    imgui.get_color_u32((0.7, 0.72, 0.74, 1.0)),
                )

        can_join = server is not None and self._on_join is not None
        tooltip = (
            "No server metadata or multiplayer connection service is available."
            if not can_join else None
        )
        if ui.button("frmInner/btnJoinGame", "JOIN GAME", "multiplayer.server_info.join",
                     enabled=can_join, tooltip=tooltip):
            callback = self._on_join
            self.close()
            if callback is not None:
                callback()


class JoinMultiplayerWindow:
    """Source-sized server browser with explicit offline states for OpenPower."""

    def __init__(
        self,
        on_cancel: Callable[[], None],
        on_load_game: Callable[[], None] | None = None,
        on_host_game: Callable[[str], None] | None = None,
    ) -> None:
        self._on_cancel = on_cancel
        self._on_load_game = on_load_game
        self._on_host_game = on_host_game
        self._open = False
        self._mode = "internet"
        self.server_info = ServerInfoWindow()
        self.input_dialog = GenericInputDialog()
        self._selected_server: MultiplayerServerInfo | None = None

    @property
    def is_open(self) -> bool:
        return self._open

    def show(self, mode: str) -> None:
        self._mode = "lan" if str(mode).casefold() == "lan" else "internet"
        self._selected_server = None
        self._open = True

    def close(self) -> None:
        self._open = False
        self._selected_server = None
        self._on_cancel()

    def render(self, screen_width: float, screen_height: float) -> None:
        if not self._open:
            return

        width, height = 566.0, 454.0
        flags = (
            imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_scrollbar
            | imgui.WindowFlags_.no_scroll_with_mouse
        )
        with WindowManager.window(
            "JOIN GAME",
            x=(screen_width - width) / 2.0,
            y=(screen_height - height) / 2.0,
            w=width,
            h=height,
            closable=False,
            flags=flags,
            test_id="multiplayer.join.window",
            gml_template="Join_Multiplayer_Game",
            size_override=(width, height),
            follow_position=True,
        ) as opened:
            if opened:
                self._apply_source_runtime_geometry()
                self._render_content()
        if not self._open:
            return
        self.server_info.render(screen_width, screen_height)
        self.input_dialog.render(screen_width, screen_height)

    @staticmethod
    def _apply_source_runtime_geometry() -> None:
        """Mirror the verified frame growth and bottom-control shifts in OnCreate."""
        layout = active_gml_layout()
        if layout is None:
            return
        layout.resize_component("Join_Multiplayer_Game/frmInner", height=421.0)
        layout.resize_component("Join_Multiplayer_Game/picWhiteBar", height=447.0)

    def _render_content(self) -> None:
        ui = GMLWidgets("Join_Multiplayer_Game")
        page = "Tab2" if self._mode == "lan" else "Tab1"
        unavailable = "Multiplayer server discovery is not available in OpenPower."

        ui.text(f"frmInner/tabGames/{page}/lblServerName", "SERVER NAME", font_size=10.0)
        # The source's 43 px players header is sized for a smaller caption font.
        ui.text(f"frmInner/tabGames/{page}/lblPlayers", "PLAYERS", font_size=10.0)
        ui.text(f"frmInner/tabGames/{page}/lblMods", "MOD", font_size=10.0)
        ui.text(f"frmInner/tabGames/{page}/lblScenarios", "SCENARIO", font_size=10.0)

        list_path = f"Join_Multiplayer_Game/frmInner/tabGames/{page}/lstServer"
        with gml_child_frame(list_path, padding=(5.0, 5.0), bordered=True) as list_open:
            if list_open:
                imgui.text_wrapped(
                    unavailable,
                    test_id="multiplayer.join.empty_state",
                )
                imgui.text_disabled("Server, player count, mod and scenario data are unavailable.")

        ui.text_at(
            "frmInner",
            "MULTIPLAYER ACCOUNT: UNAVAILABLE",
            offset=(136.0, 403.0),
            max_width=400.0,
        )

        if self._mode == "lan":
            ui.button_at(
                "frmInner/btnUpdate", "UPDATE", "multiplayer.join.update",
                offset=(0.0, 22.0),
                size=(116.0, 18.0), enabled=False,
                tooltip="OpenPower has no multiplayer LAN discovery service.",
            )

        if self._on_host_game is not None and ui.button_at(
            "frmInner/btnJoinGame", "HOST GAME", "multiplayer.join.host",
            offset=(-40.0, 0.0), size=(156.0, 18.0),
            enabled=True,
            tooltip="Open the host settings. Starting a multiplayer server is unavailable.",
        ):
            self._on_host_game(self._mode)
        ui.button_at(
            "frmInner/btnJoinGame", "JOIN GAME", "multiplayer.join.connect",
            offset=(-40.0, 22.0), size=(156.0, 18.0), enabled=False,
            tooltip="Select a listed server after a multiplayer service is connected.",
        )
        ui.button_at(
            "frmInner/btnServerInfo", "SERVER INFO", "multiplayer.join.server_info",
            offset=(0.0, 22.0), size=(116.0, 18.0), enabled=False,
            tooltip="Server details are unavailable because no servers can be listed.",
        )
        if ui.button_at(
            "frmInner/btnCancel", "CANCEL", "multiplayer.join.cancel",
            offset=(0.0, 22.0), size=(116.0, 18.0),
        ):
            self.close()

        if self._on_load_game is not None and ui.button_at(
            "frmInner/btnCancel", "LOAD GAME", "multiplayer.join.load_game",
            size=(116.0, 18.0),
        ):
            self._on_load_game()
