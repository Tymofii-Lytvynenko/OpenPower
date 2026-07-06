from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, patch

from src.client.services.display_modes import DisplayModeOption, DisplayScreenOption
from src.client.services.game_settings_service import (
    GameSettings,
    GameSettingsRepository,
    GameSettingsService,
    LanguageOption,
)
from src.client.ui.components import settings_content as settings_content_module
from src.client.ui.components.settings_content import GameSettingsContent


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def make_temp_root(prefix: str) -> Path:
    root = PROJECT_ROOT / ".temp" / f"{prefix}-{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


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
                make_mode(1280, 720, 60),
            ],
        ),
        make_screen(
            1,
            2560,
            1440,
            [
                make_mode(1920, 1080, 144),
                make_mode(1600, 900, 60),
            ],
        ),
    )


class FakeDisplayCatalog:
    def __init__(self, screens: tuple[DisplayScreenOption, ...]):
        self._screens = screens

    def list_screens(self) -> tuple[DisplayScreenOption, ...]:
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


class FakeWindow:
    def __init__(self, width: int = 1280, height: int = 720, fullscreen: bool = False):
        self._size = (width, height)
        self.fullscreen = fullscreen
        self.set_size_calls: list[tuple[int, int]] = []
        self.set_fullscreen_calls: list[dict[str, object | None]] = []
        self.center_window_calls = 0

    def get_size(self) -> tuple[int, int]:
        return self._size

    def set_size(self, width: int, height: int) -> None:
        self._size = (int(width), int(height))
        self.set_size_calls.append(self._size)

    def set_fullscreen(self, fullscreen: bool, screen=None, mode=None, width=None, height=None) -> None:
        self.fullscreen = fullscreen
        if fullscreen and mode is not None and hasattr(mode, "width") and hasattr(mode, "height"):
            self._size = (int(mode.width), int(mode.height))
        elif not fullscreen and width is not None and height is not None:
            self._size = (int(width), int(height))
        self.set_fullscreen_calls.append(
            {
                "fullscreen": fullscreen,
                "screen": screen,
                "mode": mode,
                "width": width,
                "height": height,
            }
        )

    def center_window(self) -> None:
        self.center_window_calls += 1


class DummySettingsService:
    def __init__(
        self,
        *,
        fullscreen: bool = False,
        windowed_width: int = 1600,
        windowed_height: int = 900,
        screen_index: int = 1,
        mode_index: int = 0,
        language_index: int = 1,
    ):
        self.settings = GameSettings(
            fullscreen=fullscreen,
            language_code=("en", "uk")[language_index],
            windowed_width=windowed_width,
            windowed_height=windowed_height,
            fullscreen_screen_index=screen_index,
            fullscreen_mode_width=build_catalog()[screen_index].modes[mode_index].width,
            fullscreen_mode_height=build_catalog()[screen_index].modes[mode_index].height,
            fullscreen_mode_rate=build_catalog()[screen_index].modes[mode_index].rate,
        )
        self._screens = build_catalog()
        self._screen_index = screen_index
        self._mode_index = mode_index
        self._language_index = language_index
        self.calls: list[tuple] = []

    @property
    def language_options(self) -> tuple[LanguageOption, ...]:
        return (
            LanguageOption("en", "English", is_stub=False),
            LanguageOption("uk", "Ukrainian (stub)"),
        )

    @property
    def selected_language_index(self) -> int:
        return self._language_index

    @property
    def selected_language(self) -> LanguageOption:
        return self.language_options[self._language_index]

    def fullscreen_screen_options(self) -> tuple[DisplayScreenOption, ...]:
        return self._screens

    @property
    def selected_fullscreen_screen_index(self) -> int:
        return self._screen_index

    def fullscreen_mode_options(self, screen_index: int | None = None) -> tuple[DisplayModeOption, ...]:
        index = self._screen_index if screen_index is None else screen_index
        return self._screens[index].modes

    def selected_fullscreen_mode_index(self, screen_index: int | None = None) -> int:
        return self._mode_index

    def set_fullscreen(self, enabled: bool, window=None) -> None:
        self.calls.append(("fullscreen", enabled, window))
        self.settings = GameSettings(
            fullscreen=enabled,
            language_code=self.settings.language_code,
            windowed_width=self.settings.windowed_width,
            windowed_height=self.settings.windowed_height,
            fullscreen_screen_index=self.settings.fullscreen_screen_index,
            fullscreen_mode_width=self.settings.fullscreen_mode_width,
            fullscreen_mode_height=self.settings.fullscreen_mode_height,
            fullscreen_mode_rate=self.settings.fullscreen_mode_rate,
        )

    def set_windowed_resolution(self, width: int, height: int, window=None) -> None:
        self.calls.append(("windowed", width, height, window))
        self.settings = GameSettings(
            fullscreen=self.settings.fullscreen,
            language_code=self.settings.language_code,
            windowed_width=width,
            windowed_height=height,
            fullscreen_screen_index=self.settings.fullscreen_screen_index,
            fullscreen_mode_width=self.settings.fullscreen_mode_width,
            fullscreen_mode_height=self.settings.fullscreen_mode_height,
            fullscreen_mode_rate=self.settings.fullscreen_mode_rate,
        )

    def set_fullscreen_screen_index(self, index: int, window=None) -> None:
        self.calls.append(("screen", index, window))
        self._screen_index = index
        selected = self.fullscreen_mode_options(index)[self._mode_index]
        self.settings = GameSettings(
            fullscreen=self.settings.fullscreen,
            language_code=self.settings.language_code,
            windowed_width=self.settings.windowed_width,
            windowed_height=self.settings.windowed_height,
            fullscreen_screen_index=index,
            fullscreen_mode_width=selected.width,
            fullscreen_mode_height=selected.height,
            fullscreen_mode_rate=selected.rate,
        )

    def set_fullscreen_mode_by_index(self, index: int, window=None) -> None:
        self.calls.append(("mode", index, window))
        self._mode_index = index
        selected = self.fullscreen_mode_options()[index]
        self.settings = GameSettings(
            fullscreen=self.settings.fullscreen,
            language_code=self.settings.language_code,
            windowed_width=self.settings.windowed_width,
            windowed_height=self.settings.windowed_height,
            fullscreen_screen_index=self._screen_index,
            fullscreen_mode_width=selected.width,
            fullscreen_mode_height=selected.height,
            fullscreen_mode_rate=selected.rate,
        )

    def set_language_by_index(self, index: int) -> None:
        self.calls.append(("language", index))
        self._language_index = index
        self.settings = GameSettings(
            fullscreen=self.settings.fullscreen,
            language_code=self.language_options[index].code,
            windowed_width=self.settings.windowed_width,
            windowed_height=self.settings.windowed_height,
            fullscreen_screen_index=self.settings.fullscreen_screen_index,
            fullscreen_mode_width=self.settings.fullscreen_mode_width,
            fullscreen_mode_height=self.settings.fullscreen_mode_height,
            fullscreen_mode_rate=self.settings.fullscreen_mode_rate,
        )


class TestGameSettingsRepositoryCompatibility(unittest.TestCase):
    def setUp(self):
        self.temp_root = make_temp_root("settings-repo")

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_loads_legacy_payload_and_saves_new_fields(self):
        path = self.temp_root / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "fullscreen": True,
                    "language_code": "uk",
                    "windowed_width": 1600,
                    "windowed_height": 900,
                }
            ),
            encoding="utf-8",
        )

        repo = GameSettingsRepository(path)
        settings = repo.load()

        self.assertTrue(settings.fullscreen)
        self.assertEqual(settings.language_code, "uk")
        self.assertEqual(settings.windowed_width, 1600)
        self.assertEqual(settings.windowed_height, 900)
        self.assertEqual(settings.fullscreen_screen_index, 0)
        self.assertEqual(settings.fullscreen_mode_width, 1280)
        self.assertEqual(settings.fullscreen_mode_height, 720)
        self.assertEqual(settings.fullscreen_mode_rate, 60)

        repo.save(settings)
        saved_payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("fullscreen_screen_index", saved_payload)
        self.assertIn("fullscreen_mode_width", saved_payload)
        self.assertIn("fullscreen_mode_height", saved_payload)
        self.assertIn("fullscreen_mode_rate", saved_payload)

    def test_handles_malformed_json_and_missing_fields(self):
        path = self.temp_root / "settings.json"
        path.write_text("{ definitely not valid json", encoding="utf-8")

        settings = GameSettingsRepository(path).load()

        self.assertEqual(settings, GameSettings())

    def test_clamps_invalid_fullscreen_values(self):
        path = self.temp_root / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "fullscreen_screen_index": -4,
                    "fullscreen_mode_width": 0,
                    "fullscreen_mode_height": -1,
                    "fullscreen_mode_rate": 0,
                    "windowed_width": 320,
                    "windowed_height": 240,
                }
            ),
            encoding="utf-8",
        )

        settings = GameSettingsRepository(path).load()

        self.assertEqual(settings.fullscreen_screen_index, 0)
        self.assertEqual(settings.fullscreen_mode_width, 640)
        self.assertEqual(settings.fullscreen_mode_height, 480)
        self.assertEqual(settings.fullscreen_mode_rate, 1)
        self.assertEqual(settings.windowed_width, 800)
        self.assertEqual(settings.windowed_height, 600)


class TestGameSettingsServiceDisplayFlow(unittest.TestCase):
    def setUp(self):
        self.catalog = FakeDisplayCatalog(build_catalog())

    def test_apply_display_restores_windowed_resolution_on_startup(self):
        repository = RecordingRepository(
            GameSettings(
                fullscreen=False,
                language_code="en",
                windowed_width=1600,
                windowed_height=900,
                fullscreen_screen_index=0,
                fullscreen_mode_width=1280,
                fullscreen_mode_height=720,
                fullscreen_mode_rate=60,
            )
        )
        service = GameSettingsService(repository, self.catalog)
        window = FakeWindow(1280, 720, fullscreen=False)

        service.apply_display(window)

        self.assertEqual(window.get_size(), (1600, 900))
        self.assertEqual(window.set_size_calls, [(1600, 900)])
        self.assertEqual(window.center_window_calls, 1)
        self.assertFalse(window.set_fullscreen_calls)

    def test_apply_display_restores_exact_fullscreen_mode(self):
        repository = RecordingRepository(
            GameSettings(
                fullscreen=True,
                language_code="en",
                windowed_width=1600,
                windowed_height=900,
                fullscreen_screen_index=1,
                fullscreen_mode_width=1920,
                fullscreen_mode_height=1080,
                fullscreen_mode_rate=144,
            )
        )
        service = GameSettingsService(repository, self.catalog)
        window = FakeWindow(1600, 900, fullscreen=False)

        service.apply_display(window)

        self.assertTrue(window.fullscreen)
        self.assertEqual(window.get_size(), (1920, 1080))
        self.assertTrue(window.set_fullscreen_calls)
        last_call = window.set_fullscreen_calls[-1]
        self.assertEqual(last_call["screen"].name, "screen-1")
        self.assertEqual(last_call["mode"].name, "1920x1080 @ 144Hz")

    def test_falls_back_to_nearest_available_mode(self):
        repository = RecordingRepository(
            GameSettings(
                fullscreen=True,
                language_code="en",
                windowed_width=1600,
                windowed_height=900,
                fullscreen_screen_index=1,
                fullscreen_mode_width=2560,
                fullscreen_mode_height=1440,
                fullscreen_mode_rate=60,
            )
        )

        service = GameSettingsService(repository, self.catalog)
        window = FakeWindow(1600, 900, fullscreen=False)

        self.assertEqual(service.settings.fullscreen_screen_index, 1)
        self.assertEqual(service.settings.fullscreen_mode_width, 1920)
        self.assertEqual(service.settings.fullscreen_mode_height, 1080)
        self.assertEqual(service.settings.fullscreen_mode_rate, 144)

        service.apply_display(window)

        self.assertEqual(window.get_size(), (1920, 1080))
        self.assertEqual(window.set_fullscreen_calls[-1]["mode"].name, "1920x1080 @ 144Hz")

    def test_screen_and_mode_changes_apply_immediately_when_fullscreen(self):
        repository = RecordingRepository(
            GameSettings(
                fullscreen=False,
                language_code="en",
                windowed_width=1600,
                windowed_height=900,
                fullscreen_screen_index=0,
                fullscreen_mode_width=1280,
                fullscreen_mode_height=720,
                fullscreen_mode_rate=60,
            )
        )
        service = GameSettingsService(repository, self.catalog)
        window = FakeWindow(1600, 900, fullscreen=False)

        service.set_fullscreen(True, window)
        service.set_fullscreen_screen_index(1, window)
        service.set_fullscreen_mode_by_index(0, window)

        self.assertTrue(window.fullscreen)
        self.assertEqual(service.settings.fullscreen_screen_index, 1)
        self.assertEqual(service.settings.fullscreen_mode_width, 1920)
        self.assertEqual(service.settings.fullscreen_mode_height, 1080)
        self.assertEqual(service.settings.fullscreen_mode_rate, 144)
        self.assertEqual(window.set_fullscreen_calls[-1]["screen"].name, "screen-1")
        self.assertEqual(window.set_fullscreen_calls[-1]["mode"].name, "1920x1080 @ 144Hz")

    def test_resize_changes_are_persisted_and_restored_when_leaving_fullscreen(self):
        repository = RecordingRepository(
            GameSettings(
                fullscreen=False,
                language_code="en",
                windowed_width=1280,
                windowed_height=720,
                fullscreen_screen_index=0,
                fullscreen_mode_width=1280,
                fullscreen_mode_height=720,
                fullscreen_mode_rate=60,
            )
        )
        service = GameSettingsService(repository, self.catalog)
        service.remember_windowed_size(1600, 900)

        self.assertEqual(service.settings.windowed_width, 1600)
        self.assertEqual(service.settings.windowed_height, 900)
        self.assertTrue(repository.saved_settings)

        window = FakeWindow(1600, 900, fullscreen=False)
        service.set_fullscreen(True, window)
        service.set_fullscreen(False, window)

        self.assertFalse(window.fullscreen)
        self.assertEqual(window.get_size(), (1600, 900))
        self.assertEqual(window.set_fullscreen_calls[-1]["fullscreen"], False)

    def test_noop_when_values_do_not_change(self):
        repository = RecordingRepository(
            GameSettings(
                fullscreen=False,
                language_code="en",
                windowed_width=1280,
                windowed_height=720,
                fullscreen_screen_index=0,
                fullscreen_mode_width=1280,
                fullscreen_mode_height=720,
                fullscreen_mode_rate=60,
            )
        )
        service = GameSettingsService(repository, self.catalog)

        service.set_language_by_index(0)
        service.set_windowed_resolution(1280, 720)
        service.set_fullscreen(False)
        service.set_fullscreen_screen_index(0)
        service.set_fullscreen_mode_by_index(service.selected_fullscreen_mode_index())
        service.remember_windowed_size(1280, 720)

        self.assertEqual(repository.saved_settings, [])


class TestGameSettingsContentWiring(unittest.TestCase):
    def setUp(self):
        self.window = FakeWindow(1600, 900, fullscreen=False)

    def _make_content_service(self) -> DummySettingsService:
        return DummySettingsService(
            fullscreen=False,
            windowed_width=1600,
            windowed_height=900,
            screen_index=1,
            mode_index=0,
            language_index=1,
        )

    def test_reflects_current_state_in_widget_defaults(self):
        service = self._make_content_service()
        content = GameSettingsContent(service, self.window)

        checkbox_mock = MagicMock(return_value=(False, False))
        input_int2_mock = MagicMock(return_value=(False, [1600, 900]))
        combo_mock = MagicMock(side_effect=[(False, 1), (False, 0), (False, 1)])

        with patch.object(settings_content_module.Prims, "header", return_value=None), patch.multiple(
            settings_content_module.imgui,
            checkbox=checkbox_mock,
            input_int2=input_int2_mock,
            combo=combo_mock,
            dummy=MagicMock(),
            same_line=MagicMock(),
            text=MagicMock(),
            text_disabled=MagicMock(),
            text_colored=MagicMock(),
            align_text_to_frame_padding=MagicMock(),
            set_next_item_width=MagicMock(),
            get_content_region_avail=MagicMock(return_value=SimpleNamespace(x=320)),
        ):
            content.render()

        combo_calls = combo_mock.call_args_list
        self.assertEqual(combo_calls[0].args[1], 1)
        self.assertEqual(combo_calls[1].args[1], 0)
        self.assertEqual(combo_calls[2].args[1], 1)
        self.assertEqual(input_int2_mock.call_args.args[1], [1600, 900])

    def test_routes_display_and_language_changes_to_service(self):
        service = DummySettingsService(
            fullscreen=False,
            windowed_width=1600,
            windowed_height=900,
            screen_index=0,
            mode_index=0,
            language_index=0,
        )
        content = GameSettingsContent(service, self.window)

        with patch.object(settings_content_module.Prims, "header", return_value=None), patch.multiple(
            settings_content_module.imgui,
            checkbox=MagicMock(return_value=(True, True)),
            input_int2=MagicMock(return_value=(True, [1920, 1080])),
            combo=MagicMock(side_effect=[(True, 1), (True, 1), (True, 1)]),
            dummy=MagicMock(),
            same_line=MagicMock(),
            text=MagicMock(),
            text_disabled=MagicMock(),
            text_colored=MagicMock(),
            align_text_to_frame_padding=MagicMock(),
            set_next_item_width=MagicMock(),
            get_content_region_avail=MagicMock(return_value=SimpleNamespace(x=320)),
        ):
            content.render()

        self.assertEqual(
            service.calls,
            [
                ("fullscreen", True, self.window),
                ("windowed", 1920, 1080, self.window),
                ("screen", 1, self.window),
                ("mode", 1, self.window),
                ("language", 1),
            ],
        )


if __name__ == "__main__":
    unittest.main()
