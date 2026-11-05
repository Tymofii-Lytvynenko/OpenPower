from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.theme import GAMETHEME


_OBJECTIVE_ROWS = (
    ("World peace", "frmTog1", "txtGoal1", "cboGoal1"),
    ("Balance resources", "frmTog2", "txtGoal2", "cboGoal2"),
    ("Conquer the world", "frmTog3", "txtGoal3", "cboGoal3"),
    ("Develop the nation", "frmTog4", "txtGoal4", "cboGoal4"),
    ("Raise GDP per capita", "frmTog5", "txtGoal5", "cboGoal5"),
)
_GOAL_TIME_LIMITS = ("No limit", "1 year", "5 years", "10 years")
_GAME_SPEEDS = ("Slowest", "Slow", "Normal", "Fast", "Fastest")
_NUCLEAR_OPTIONS = ("Permitted", "Not permitted")


@dataclass(slots=True)
class HostObjectiveDraft:
    enabled: bool = False
    time_limit_index: int = 0


@dataclass(slots=True)
class HostMultiplayerSettingsDraft:
    server_name: str = ""  # The source default is localized under token 101097.
    password: str = ""
    # These numeric values match the source default port, player count, and time limit.
    port: str = "5555"
    max_players: str = "8"
    time_limit: str = "0"
    dedicated_server: bool = False
    game_speed_index: int = 2
    nuclear_option_index: int = 0
    objectives: list[HostObjectiveDraft] = field(
        default_factory=lambda: [HostObjectiveDraft() for _ in _OBJECTIVE_ROWS]
    )


class HostMultiplayerGameWindow:
    """Source-sized host settings form with local draft state."""

    _ROOT = "Host_Multiplayer_Game"

    def __init__(self, on_cancel: Callable[[], None]) -> None:
        self._on_cancel = on_cancel
        self._open = False
        self._mode = "internet"
        self._draft = HostMultiplayerSettingsDraft()

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def draft(self) -> HostMultiplayerSettingsDraft:
        return self._draft

    def show(self, mode: str) -> None:
        self._mode = "lan" if str(mode).casefold() == "lan" else "internet"
        self._open = True

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        self._on_cancel()

    def render(self, screen_width: float, screen_height: float) -> None:
        if not self._open:
            return

        width, height = 341.0, 342.0
        is_open = True
        flags = (
            imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_collapse
            | imgui.WindowFlags_.no_scrollbar
            | imgui.WindowFlags_.no_scroll_with_mouse
        )
        with WindowManager.window(
            "HOST MULTIPLAYER GAME",
            x=(float(screen_width) - width) / 2.0,
            y=(float(screen_height) - height) / 2.0,
            w=width,
            h=height,
            closable=False,
            flags=flags,
            test_id="multiplayer.host.window",
            gml_template=self._ROOT,
            size_override=(width, height),
            follow_position=True,
        ) as is_open:
            if is_open:
                self._render_content()
        if not is_open:
            self.close()

    def _render_content(self) -> None:
        ui = GMLWidgets(self._ROOT)
        for slot in (
            "frmInner",
            "frmInner/frmGameInfo",
            "frmInner/frmGameSettings",
            "frmInner/frmGoals",
            *(f"frmInner/frmGoals/frmTog{index}" for index in range(1, 6)),
        ):
            ui.frame(slot)

        self._render_server_identity(ui)
        self._render_server_settings(ui)
        self._render_game_settings(ui)
        self._render_objectives(ui)

        if ui.button(
            "frmInner/btnStart",
            "START GAME",
            "multiplayer.host.start",
            enabled=False,
            tooltip="OpenPower has no authoritative multiplayer host service.",
        ):
            return
        if ui.button("frmInner/btnCancel", "CANCEL", "multiplayer.host.cancel"):
            self.close()

    def _render_server_identity(self, ui: GMLWidgets) -> None:
        ui.text("frmInner/frmGameInfo/lblServerName", "SERVER NAME")
        ui.text("frmInner/frmGameInfo/lblPassword", "PASSWORD")
        _, self._draft.server_name = imgui.input_text(
            "##host_server_name",
            self._draft.server_name,
            64,
            test_id="multiplayer.host.server_name",
            gml_id=ui.path("frmInner/frmGameInfo/edtServerName"),
        )
        _, self._draft.password = imgui.input_text(
            "##host_password",
            self._draft.password,
            int(imgui.InputTextFlags_.password),
            test_id="multiplayer.host.password",
            gml_id=ui.path("frmInner/frmGameInfo/edtPassword"),
        )

    def _render_server_settings(self, ui: GMLWidgets) -> None:
        for slot, label in (
            ("lblMaxPlayers", "MAX PLAYERS"),
            ("lblPort", "PORT"),
            ("lblTimeLimit", "TIME LIMIT"),
            ("lblDedicatedServer", "DEDICATED SERVER"),
        ):
            ui.text(f"frmInner/frmGameSettings/{slot}", label)

        for control, test_id, value in (
            ("edtMaxPlayers", "multiplayer.host.max_players", "max_players"),
            ("edtPort", "multiplayer.host.port", "port"),
            ("edtTimeLimit", "multiplayer.host.time_limit", "time_limit"),
        ):
            _, updated = imgui.input_text(
                f"##{test_id.replace('.', '_')}",
                getattr(self._draft, value),
                8,
                test_id=test_id,
                gml_id=ui.path(f"frmInner/frmGameSettings/{control}"),
            )
            setattr(self._draft, value, updated)

        _, self._draft.dedicated_server = ui.toggle(
            "frmInner/frmGameSettings/togDedicatedServer",
            self._draft.dedicated_server,
            "multiplayer.host.dedicated_server",
            icon="✓" if self._draft.dedicated_server else "",
            color=GAMETHEME.colors.accent,
        )

    def _render_game_settings(self, ui: GMLWidgets) -> None:
        ui.text("frmInner/frmGoals/lblGameSettings", "GAME SETTINGS")
        ui.text("frmInner/frmGoals/txtGameSpeed", "GAME SPEED")
        ui.text("frmInner/frmGoals/txtNukes", "NUCLEAR WARFARE")

        changed, selected = ui.combo_at(
            "frmInner/frmGoals/cboGameSpeed",
            "##host_game_speed",
            self._draft.game_speed_index,
            _GAME_SPEEDS,
            "multiplayer.host.game_speed",
        )
        if changed:
            self._draft.game_speed_index = selected

        changed, selected = ui.combo_at(
            "frmInner/frmGoals/cboGameSpeed1",
            "##host_nuclear_option",
            self._draft.nuclear_option_index,
            _NUCLEAR_OPTIONS,
            "multiplayer.host.nuclear_option",
        )
        if changed:
            self._draft.nuclear_option_index = selected

    def _render_objectives(self, ui: GMLWidgets) -> None:
        ui.text("frmInner/frmGoals/lblGoals", "OBJECTIVES")
        ui.text("frmInner/frmGoals/lblTimeLimit", "TIME LIMIT")

        for index, (label, toggle_slot, label_slot, combo_slot) in enumerate(_OBJECTIVE_ROWS):
            objective = self._draft.objectives[index]
            ui.text(f"frmInner/frmGoals/{label_slot}", label)
            _, objective.enabled = ui.toggle(
                f"frmInner/frmGoals/{toggle_slot}/togGoal",
                objective.enabled,
                f"multiplayer.host.objective.{index + 1}",
                icon="✓" if objective.enabled else "",
                color=GAMETHEME.colors.accent,
            )
            changed, selected = ui.combo_at(
                f"frmInner/frmGoals/{combo_slot}",
                f"##host_goal_time_{index + 1}",
                objective.time_limit_index,
                _GOAL_TIME_LIMITS,
                f"multiplayer.host.objective_time.{index + 1}",
                enabled=objective.enabled,
            )
            if changed:
                objective.time_limit_index = selected
