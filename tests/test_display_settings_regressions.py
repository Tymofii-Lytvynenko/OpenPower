from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.services.display_modes import DisplayModeOption, DisplayScreenOption
from src.client.services.game_settings_service import GameSettings, GameSettingsService
from src.client.ui.components.hud.system_bar import SystemBar


def make_mode(width: int, height: int, rate: int) -> DisplayModeOption:
    label = f"{width}x{height} @ {rate}Hz"
    raw_mode = SimpleNamespace(name=label, width=width, height=height, rate=rate)
    return DisplayModeOption(width=width, height=height, rate=rate, label=label, mode=raw_mode)


def make_screen(index: int, width: int, height: int, modes: list[DisplayModeOption]) -> DisplayScreenOption:
    label = f"Display {index + 1} ({width}x{height})"
    raw_screen = SimpleNamespace(name=f"screen-{index}", width=width, height=height)
    return DisplayScreenOption(
        index=index,
        label=label,
        width=width,
        height=height,
        modes=tuple(modes),
        screen=raw_screen,
    )


def build_catalog() -> tuple[DisplayScreenOption, ...]:
    return (
        make_screen(
            0,
            1920,
            1080,
            [
                make_mode(1920, 1080, 60),
                make_mode(1600, 900, 60),
            ],
        ),
        make_screen(
            1,
            2560,
            1440,
            [
                make_mode(2560, 1440, 144),
                make_mode(1920, 1080, 144),
            ],
        ),
    )


class CountingDisplayCatalog:
    def __init__(self, screens: tuple[DisplayScreenOption, ...]):
        self._screens = screens
        self.calls = 0

    def list_screens(self) -> tuple[DisplayScreenOption, ...]:
        self.calls += 1
        return self._screens


class RecordingRepository:
    def __init__(self, settings: GameSettings):
        self._settings = settings
        self.saved_settings: list[GameSettings] = []

    def load(self) -> GameSettings:
        return self._settings

    def save(self, settings: GameSettings) -> None:
        self._settings = settings
        self.saved_settings.append(settings)


class TestGameSettingsServiceDisplayCache(unittest.TestCase):
    def test_reuses_screen_enumeration_across_settings_queries(self):
        catalog = CountingDisplayCatalog(build_catalog())
        repository = RecordingRepository(
            GameSettings(
                fullscreen=False,
                language_code="en",
                windowed_width=1280,
                windowed_height=720,
                fullscreen_screen_index=0,
                fullscreen_mode_width=1920,
                fullscreen_mode_height=1080,
                fullscreen_mode_rate=60,
            )
        )

        service = GameSettingsService(repository, catalog)
        first = service.fullscreen_screen_options()
        second = service.fullscreen_screen_options()
        service.selected_fullscreen_screen_index
        service.fullscreen_mode_options()
        service.fullscreen_mode_options(1)
        service.selected_fullscreen_mode_index()

        self.assertIs(first, second)
        self.assertEqual(catalog.calls, 1)


class TestSystemBarNavigationRegression(unittest.TestCase):
    def test_menu_and_load_transitions_use_window_config(self):
        bar = SystemBar()
        config = object()
        session = SimpleNamespace()
        net_client = SimpleNamespace(session=session)
        nav_service = SimpleNamespace(
            window=SimpleNamespace(game_config=config),
            show_main_menu=Mock(),
            show_load_game_screen=Mock(),
        )

        bar._show_load(nav_service, net_client)
        bar._show_menu(nav_service, net_client)

        nav_service.show_load_game_screen.assert_called_once_with(config)
        nav_service.show_main_menu.assert_called_once_with(session, config)

    def test_menu_and_load_transitions_noop_without_window_config(self):
        bar = SystemBar()
        net_client = SimpleNamespace(session=SimpleNamespace())
        nav_service = SimpleNamespace(
            window=SimpleNamespace(),
            show_main_menu=Mock(),
            show_load_game_screen=Mock(),
        )

        bar._show_load(nav_service, net_client)
        bar._show_menu(nav_service, net_client)

        nav_service.show_load_game_screen.assert_not_called()
        nav_service.show_main_menu.assert_not_called()


if __name__ == "__main__":
    unittest.main()