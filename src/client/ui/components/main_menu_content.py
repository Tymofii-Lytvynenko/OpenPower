from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.client.ui.core.composer import UIComposer
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.testability import semantic_region
from src.client.ui.components.project_credits_content import ProjectCreditsContent
from src.client.ui.components.reference_options_window_content import REFERENCEOptionsWindowContent
from src.client.ui.components.shared.host_multiplayer_window import HostMultiplayerGameWindow
from src.client.ui.components.shared.multiplayer_windows import JoinMultiplayerWindow
from src.client.ui.components.tutorial_guide_content import (
    TutorialGuideContent,
)
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.layouts.gml_layout import active_gml_layout


@dataclass(frozen=True, slots=True)
class MainMenuAction:
    label: str
    test_id: str
    callback: Callable[[], None] | None
    gml_component_id: str
    spacer_after: float = 0.0
    show_settings: bool = False
    show_credits: bool = False
    enabled: bool = True
    tooltip: str = ""
    screen: str = "main"
    opens_screen: str | None = None
    return_to_main: bool = False
    join_mode: str | None = None
    opens_tutorial: str | None = None


def build_main_menu_actions(
    on_singleplayer: Callable[[], None],
    on_load_game: Callable[[], None],
    on_exit: Callable[[], None],
) -> tuple[MainMenuAction, ...]:
    return (
        MainMenuAction(
            "SINGLEPLAYER", "main_menu.singleplayer", None, "btnSingle",
            opens_screen="singleplayer",
        ),
        MainMenuAction(
            "MULTIPLAYER", "main_menu.multiplayer", None, "btnMulti",
            opens_screen="multiplayer",
        ),
        MainMenuAction(
            "SETTINGS", "main_menu.options", None,
            "btnOptions", show_settings=True,
        ),
        MainMenuAction("CREDITS", "main_menu.credits", None, "btnCredits", show_credits=True),
        MainMenuAction("EXIT TO DESKTOP", "main_menu.exit", on_exit, "btnQuit"),
        MainMenuAction(
            "INTERFACE TUTORIAL", "main_menu.interface_tutorial", None,
            "btnTutorial1",
            tooltip="Open the OpenPower guide to the map and interface.",
            screen="singleplayer",
            opens_tutorial="interface",
        ),
        MainMenuAction(
            "MILITARY TUTORIAL", "main_menu.military_tutorial", None,
            "btnTutorial2",
            tooltip="Open the OpenPower guide to supported military panels.",
            screen="singleplayer",
            opens_tutorial="military",
        ),
        MainMenuAction(
            "SCENARIO", "main_menu.scenario", on_singleplayer, "btnScenario",
            screen="singleplayer",
        ),
        MainMenuAction(
            "CUSTOM GAME", "main_menu.custom_game", None, "btnCustom",
            enabled=False,
            tooltip="OpenPower has no equivalent custom-scenario setup workflow.",
            screen="singleplayer",
        ),
        MainMenuAction(
            "LOAD GAME", "main_menu.load_game", on_load_game, "btnLoad",
            screen="singleplayer",
        ),
        MainMenuAction(
            "BACK", "main_menu.singleplayer.back", None, "btnReturn",
            screen="singleplayer", return_to_main=True,
        ),
        MainMenuAction(
            "INTERNET", "main_menu.multiplayer.internet", None, "btnHost",
            tooltip="Opens the server list; server browsing is unavailable in OpenPower.",
            screen="multiplayer",
            join_mode="internet",
        ),
        MainMenuAction(
            "LAN", "main_menu.multiplayer.lan", None, "btnJoin",
            tooltip="Opens the LAN server list; discovery is unavailable in OpenPower.",
            screen="multiplayer",
            join_mode="lan",
        ),
        MainMenuAction(
            "BACK", "main_menu.multiplayer.back", None, "btnReturn",
            screen="multiplayer", return_to_main=True,
        ),
    )


def build_in_game_menu_actions(
    on_resume: Callable[[], None],
    on_quit: Callable[[], None] | None,
    on_stop: Callable[[], None] | None = None,
) -> tuple[MainMenuAction, ...]:
    return (
        MainMenuAction("RETURN TO GAME", "game_menu.resume", on_resume, "btnSingle"),
        MainMenuAction(
            "RESTART GAME", "game_menu.restart", None, "btnMulti",
            enabled=False,
            tooltip="Restart is unavailable because OpenPower has no authoritative restart action.",
        ),
        MainMenuAction(
            "STOP GAME", "game_menu.stop", on_stop, "btnStop",
            enabled=on_stop is not None,
            tooltip="Return to the main menu and start a fresh world session."
            if on_stop is not None else "Stopping a running session is unavailable.",
        ),
        MainMenuAction(
            "SETTINGS", "game_menu.settings", None,
            "btnOptions", show_settings=True,
        ),
        MainMenuAction(
            "CREDITS", "game_menu.credits", None,
            "btnCredits", show_credits=True,
        ),
        MainMenuAction("EXIT TO DESKTOP", "game_menu.quit", on_quit, "btnQuit"),
    )


class MainMenuContent:
    """Shared menu overlay used by the production main-menu view and UI journeys."""

    def __init__(self, composer: UIComposer, settings_content, actions: tuple[MainMenuAction, ...],
                 test_id_prefix: str = "main_menu", in_game: bool = False):
        self._composer = composer
        self._actions = actions
        self._test_id_prefix = test_id_prefix
        self._settings_content = REFERENCEOptionsWindowContent(settings_content, test_id_prefix)
        self._in_game = in_game
        self._show_settings = False
        self._show_credits = False
        self._active_submenu: str | None = None
        self._tutorial_guide = TutorialGuideContent()
        self._credits_content = ProjectCreditsContent()
        self._host_window = HostMultiplayerGameWindow(on_cancel=lambda: None)
        load_game = next(
            (action.callback for action in actions if action.test_id == "main_menu.load_game"),
            None,
        )
        self._join_window = JoinMultiplayerWindow(
            on_cancel=lambda: setattr(self, "_active_submenu", "multiplayer"),
            on_load_game=load_game,
            on_host_game=self._host_window.show,
        )

    def render(self, screen_width: float, screen_height: float) -> None:
        if self._host_window.is_open:
            self._host_window.render(screen_width, screen_height)
            return
        if self._join_window.is_open:
            self._join_window.render(screen_width, screen_height)
            return

        page = self._current_page()
        panel_title, gml_template, test_id, size_override = self._page_layout(page)

        if not self._composer.begin_centered_panel(
            panel_title, screen_width, screen_height,
            test_id=test_id, gml_template=gml_template,
            size_override=size_override,
            force_size=page == "tutorial",
        ):
            return

        if not self._in_game:
            self._apply_source_runtime_geometry(gml_template)

        if self._show_settings:
            self._render_settings()
        elif self._show_credits:
            self._render_credits()
        elif page == "tutorial":
            self._tutorial_guide.render(
                self._close_tutorial,
                window_width=size_override[0] if size_override else 400.0,
            )
        else:
            self._render_actions(page, gml_template)

        self._composer.end_panel()

    def _current_page(self) -> str:
        if self._tutorial_guide.is_open:
            return "tutorial"
        if self._show_settings:
            return "settings"
        if self._show_credits:
            return "credits"
        return self._active_submenu or "main"

    def _page_layout(self, page: str) -> tuple[str, str, str, tuple[float, float] | None]:
        layouts = {
            "main": (
                "MAIN MENU", "Main_Menu", f"{self._test_id_prefix}.window",
                (273.0, 223.0) if self._in_game else (273.0, 196.0),
            ),
            "singleplayer": (
                "SINGLEPLAYER", "Submenu_Single",
                f"{self._test_id_prefix}.singleplayer.window", None,
            ),
            "multiplayer": (
                "MULTIPLAYER", "Submenu_Multi",
                f"{self._test_id_prefix}.multiplayer.window", (273.0, 139.0),
            ),
            "settings": (
                "SETTINGS", "Options_Window",
                f"{self._test_id_prefix}.window", None,
            ),
            "credits": (
                "CREDITS", "Credits_Window",
                f"{self._test_id_prefix}.window", None,
            ),
            "tutorial": (
                self._tutorial_guide.title, "",
                f"{self._test_id_prefix}.tutorial.window",
                self._tutorial_guide.window_size(),
            ),
        }
        return layouts[page]

    @staticmethod
    def _apply_source_runtime_geometry(gml_template: str) -> None:
        """Mirror the source OnShow size adjustments for disconnected menus."""
        from src.client.ui.layouts.gml_layout import active_gml_layout

        layout = active_gml_layout()
        if layout is None:
            return

        if gml_template == "Main_Menu":
            layout.resize_component("Main_Menu/frmInner", height=163.0)
            layout.resize_component("Main_Menu/picShadowGradient", height=189.0)
            layout.resize_component("Main_Menu/picWhiteGradient", height=189.0)
            for component in (
                "Main_Menu/frmInner/picSep",
                "Main_Menu/frmInner/btnOptions",
                "Main_Menu/frmInner/btnCredits",
                "Main_Menu/frmInner/btnQuit",
            ):
                layout.move_component(component, y=-27.0)
        elif gml_template == "Submenu_Multi":
            layout.resize_component("Submenu_Multi/frmInner", height=106.0)
            layout.resize_component("Submenu_Multi/picShadowGradient", height=132.0)
            layout.resize_component("Submenu_Multi/picWhiteGradient", height=132.0)
            layout.move_component("Submenu_Multi/frmInner/picSep", y=-28.0)
            layout.move_component("Submenu_Multi/frmInner/btnReturn", y=-28.0)

    def _render_actions(self, page: str, gml_template: str) -> None:
        for action in self._actions:
            if action.screen != page:
                continue
            if self._composer.draw_menu_button(
                action.label,
                test_id=action.test_id,
                gml_id=f"{gml_template}/frmInner/{action.gml_component_id}",
                enabled=action.enabled,
                tooltip=action.tooltip,
            ):
                if action.opens_tutorial is not None:
                    self._tutorial_guide.open(action.opens_tutorial)
                    self._show_settings = False
                    self._show_credits = False
                elif action.join_mode is not None:
                    self._join_window.show(action.join_mode)
                elif action.opens_screen is not None:
                    self._active_submenu = action.opens_screen
                    self._show_settings = False
                    self._show_credits = False
                elif action.return_to_main:
                    self._active_submenu = None
                elif action.show_settings:
                    self._show_settings = True
                    self._show_credits = False
                    self._active_submenu = None
                    begin_session = getattr(self._settings_content, "begin_session", None)
                    if callable(begin_session):
                        begin_session()
                elif action.show_credits:
                    self._show_settings = False
                    self._show_credits = True
                    self._active_submenu = None
                elif action.callback is not None:
                    action.callback()
            if action.spacer_after:
                self._composer.dummy((0, action.spacer_after))

    def _close_tutorial(self) -> None:
        self._tutorial_guide.close()

    def _render_settings(self) -> None:
        with semantic_region(f"{self._test_id_prefix}.options_screen", "Settings"):
            available_height = float(imgui.get_content_region_avail().y)
            self._settings_content.render(max_height=max(120.0, available_height - 34.0))

        title_ui = GMLWidgets("Options_Window/frmTitle")
        previous_cursor = imgui.get_cursor_screen_pos()
        close_clicked = title_ui.button_at(
            "btnExit",
            "×",
            f"{self._test_id_prefix}.close",
            size=(17.0, 17.0),
            padding=(0.0, 0.0),
        )
        imgui.set_cursor_screen_pos(previous_cursor)
        if close_clicked:
            discard_settings = getattr(self._settings_content, "discard", None)
            if callable(discard_settings):
                discard_settings()
            self._show_settings = False

        options_ui = GMLWidgets("Options_Window/frmInner")
        if options_ui.button("btnConfirm", "APPLY", f"{self._test_id_prefix}.apply"):
            apply_settings = getattr(self._settings_content, "apply", None)
            applied = None
            if callable(apply_settings):
                applied = apply_settings()
            if applied is not False:
                self._show_settings = False

        if options_ui.button("btnCancel", "BACK", f"{self._test_id_prefix}.back"):
            discard_settings = getattr(self._settings_content, "discard", None)
            if callable(discard_settings):
                discard_settings()
            self._show_settings = False

    def _render_credits(self) -> None:
        with semantic_region(f"{self._test_id_prefix}.credits_screen", "Credits"):
            if imgui.begin_child(
                "##project_credits",
                (0.0, 0.0),
                True,
                test_id=f"{self._test_id_prefix}.credits_content",
                gml_id="Credits_Window/frmInner/frmCredits",
            ):
                self._credits_content.render(f"{self._test_id_prefix}.credits")
            imgui.end_child()

        layout_session = active_gml_layout()
        close_component = (
            layout_session.layout.component("Credits_Window/frmTitle/btnExit")
            if layout_session else None
        )
        if layout_session is not None and close_component is not None:
            close_rect = layout_session.rect_for(close_component)
            window_position = imgui.get_window_pos()
            imgui.set_cursor_screen_pos((
                float(window_position.x) + close_rect.x,
                float(window_position.y) + close_rect.y,
            ))
            close_size = (close_rect.width, close_rect.height)
        else:
            close_size = (24.0, 24.0)
        if imgui.button("×", close_size, test_id=f"{self._test_id_prefix}.credits_back"):
            self._show_credits = False
