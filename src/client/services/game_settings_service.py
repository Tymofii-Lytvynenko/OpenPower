from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import orjson

from src.client.services.display_modes import (
    ArcadeDisplayCatalog,
    DisplayCatalog,
    DisplayModeOption,
    DisplayScreenOption,
    choose_best_mode,
    clamp_index,
)
from src.shared.geo_names import (
    DEFAULT_GEO_LANGUAGE_CODE,
    GEO_LANGUAGE_CHOICES,
    normalize_geo_language_code,
)

@dataclass(frozen=True, slots=True)
class LanguageOption:
    code: str
    label: str
    is_stub: bool = True


@dataclass(frozen=True, slots=True)
class GameSettings:
    fullscreen: bool = False
    language_code: str = "en"
    geo_language_code: str = DEFAULT_GEO_LANGUAGE_CODE
    windowed_width: int = 1280
    windowed_height: int = 720
    fullscreen_screen_index: int = 0
    fullscreen_mode_width: int = 1280
    fullscreen_mode_height: int = 720
    fullscreen_mode_rate: int = 60


class GameSettingsRepository:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> GameSettings:
        if not self.path.exists():
            return GameSettings()

        try:
            payload = orjson.loads(self.path.read_bytes())
        except orjson.JSONDecodeError:
            return GameSettings()

        if not isinstance(payload, dict):
            return GameSettings()

        return GameSettings(
            fullscreen=self._read_bool(payload, "fullscreen", False),
            language_code=self._read_str(payload, "language_code", "en"),
            geo_language_code=self._read_str(payload, "geo_language_code", DEFAULT_GEO_LANGUAGE_CODE),
            windowed_width=self._read_int(payload, "windowed_width", 1280, minimum=800),
            windowed_height=self._read_int(payload, "windowed_height", 720, minimum=600),
            fullscreen_screen_index=self._read_int(
                payload,
                "fullscreen_screen_index",
                0,
                minimum=0,
            ),
            fullscreen_mode_width=self._read_int(
                payload,
                "fullscreen_mode_width",
                1280,
                minimum=640,
            ),
            fullscreen_mode_height=self._read_int(
                payload,
                "fullscreen_mode_height",
                720,
                minimum=480,
            ),
            fullscreen_mode_rate=self._read_int(
                payload,
                "fullscreen_mode_rate",
                60,
                minimum=1,
            ),
        )

    def save(self, settings: GameSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(orjson.dumps(asdict(settings), option=orjson.OPT_INDENT_2))

    def _read_str(self, payload: dict[str, Any], key: str, fallback: str) -> str:
        value = payload.get(key)
        return value if isinstance(value, str) and value else fallback

    def _read_bool(self, payload: dict[str, Any], key: str, fallback: bool) -> bool:
        value = payload.get(key)
        return value if isinstance(value, bool) else fallback

    def _read_int(self, payload: dict[str, Any], key: str, fallback: int, minimum: int) -> int:
        try:
            value = int(payload.get(key, fallback))
        except (TypeError, ValueError):
            return fallback
        return max(minimum, value)


class GameSettingsService:
    LANGUAGE_OPTIONS = (
        LanguageOption("en", "English", is_stub=False),
        LanguageOption("uk", "Ukrainian (stub)"),
    )
    GEO_LANGUAGE_OPTIONS = tuple(
        LanguageOption(code, label, is_stub=False)
        for code, label in GEO_LANGUAGE_CHOICES
    )

    def __init__(
        self,
        repository: GameSettingsRepository,
        display_catalog: DisplayCatalog | None = None,
    ):
        self._repository = repository
        self._display_catalog = display_catalog or ArcadeDisplayCatalog()
        self._screen_options_cache: tuple[DisplayScreenOption, ...] | None = None
        loaded_settings = repository.load()
        self._settings = self._normalize(loaded_settings)
        if self._settings != loaded_settings:
            self._save()

    @classmethod
    def from_path(
        cls,
        path: Path,
        display_catalog: DisplayCatalog | None = None,
    ) -> "GameSettingsService":
        return cls(GameSettingsRepository(path), display_catalog=display_catalog)

    @property
    def settings(self) -> GameSettings:
        return self._settings

    @property
    def language_options(self) -> tuple[LanguageOption, ...]:
        return self.LANGUAGE_OPTIONS

    @property
    def geo_language_options(self) -> tuple[LanguageOption, ...]:
        return self.GEO_LANGUAGE_OPTIONS

    def fullscreen_screen_options(self) -> tuple[DisplayScreenOption, ...]:
        # Display enumeration can be expensive on some systems, and the
        # settings UI queries it every frame while open. Cache the catalog so
        # the menu stays responsive in fullscreen.
        if self._screen_options_cache is None:
            self._screen_options_cache = tuple(self._display_catalog.list_screens())
        return self._screen_options_cache

    def fullscreen_mode_options(self, screen_index: int | None = None) -> tuple[DisplayModeOption, ...]:
        screens = self.fullscreen_screen_options()
        if not screens:
            return ()

        resolved_index = self._resolve_screen_index(screen_index, screens)
        return screens[resolved_index].modes

    @property
    def selected_language_index(self) -> int:
        for index, option in enumerate(self.LANGUAGE_OPTIONS):
            if option.code == self._settings.language_code:
                return index
        return 0

    @property
    def selected_language(self) -> LanguageOption:
        return self.LANGUAGE_OPTIONS[self.selected_language_index]

    @property
    def selected_geo_language_index(self) -> int:
        for index, option in enumerate(self.GEO_LANGUAGE_OPTIONS):
            if option.code == self._settings.geo_language_code:
                return index
        return 0

    @property
    def selected_geo_language(self) -> LanguageOption:
        return self.GEO_LANGUAGE_OPTIONS[self.selected_geo_language_index]

    @property
    def selected_fullscreen_screen_index(self) -> int:
        return self._resolve_screen_index()

    def selected_fullscreen_mode_index(self, screen_index: int | None = None) -> int:
        modes = self.fullscreen_mode_options(screen_index)
        if not modes:
            return 0

        best = choose_best_mode(
            modes,
            self._settings.fullscreen_mode_width,
            self._settings.fullscreen_mode_height,
            self._settings.fullscreen_mode_rate,
        )
        if best is None:
            return 0
        return modes.index(best)

    def set_language_by_index(self, index: int) -> None:
        if not 0 <= index < len(self.LANGUAGE_OPTIONS):
            return

        option = self.LANGUAGE_OPTIONS[index]
        if option.code == self._settings.language_code:
            return

        self._settings = replace(self._settings, language_code=option.code)
        self._save()

    def set_geo_language_by_index(self, index: int) -> None:
        if not 0 <= index < len(self.GEO_LANGUAGE_OPTIONS):
            return

        option = self.GEO_LANGUAGE_OPTIONS[index]
        normalized_code = normalize_geo_language_code(option.code)
        if normalized_code == self._settings.geo_language_code:
            return

        self._settings = replace(self._settings, geo_language_code=normalized_code)
        self._save()

    def set_windowed_resolution(self, width: int, height: int, window=None) -> None:
        updated = self._with_windowed_resolution(self._settings, width, height)
        if updated == self._settings:
            return

        self._settings = updated
        self._save()

        if window is not None and not self._settings.fullscreen:
            self.apply_display(window)

    def set_fullscreen(self, enabled: bool, window=None) -> None:
        updated = self._settings
        if enabled and window is not None and not getattr(window, "fullscreen", False):
            width, height = self._read_window_size(window)
            updated = self._with_windowed_resolution(updated, width, height)

        updated = replace(updated, fullscreen=enabled)
        updated = self._normalize(updated)
        if updated == self._settings:
            return

        self._settings = updated
        self._save()

        if window is not None:
            self.apply_display(window)

    def toggle_fullscreen(self, window) -> None:
        self.set_fullscreen(not self._settings.fullscreen, window)

    def set_fullscreen_screen_index(self, index: int, window=None) -> None:
        updated = replace(self._settings, fullscreen_screen_index=max(0, int(index)))
        updated = self._normalize_fullscreen_preferences(updated)
        if updated == self._settings:
            return

        self._settings = updated
        self._save()

        if window is not None and self._settings.fullscreen:
            self.apply_display(window)

    def set_fullscreen_mode_by_index(self, index: int, window=None) -> None:
        modes = self.fullscreen_mode_options()
        if not modes:
            return

        resolved_index = clamp_index(index, len(modes))
        mode = modes[resolved_index]
        updated = replace(
            self._settings,
            fullscreen_mode_width=mode.width,
            fullscreen_mode_height=mode.height,
            fullscreen_mode_rate=mode.rate,
        )
        updated = self._normalize_fullscreen_preferences(updated)
        if updated == self._settings:
            return

        self._settings = updated
        self._save()

        if window is not None and self._settings.fullscreen:
            self.apply_display(window)

    def apply_display(self, window) -> None:
        if self._settings.fullscreen:
            screen, mode = self._resolve_fullscreen_choice()
            if screen is None:
                return

            if mode is None:
                window.set_fullscreen(True, screen=screen.screen)
            else:
                window.set_fullscreen(True, screen=screen.screen, mode=mode.mode)
            return

        width = self._settings.windowed_width
        height = self._settings.windowed_height

        if getattr(window, "fullscreen", False):
            window.set_fullscreen(False, width=width, height=height)
        else:
            current_size = tuple(window.get_size()) if hasattr(window, "get_size") else None
            if current_size != (width, height) and hasattr(window, "set_size"):
                window.set_size(width, height)

        if hasattr(window, "center_window"):
            window.center_window()

    def remember_windowed_size(self, width: int, height: int) -> None:
        if self._settings.fullscreen:
            return

        updated = self._with_windowed_resolution(self._settings, width, height)
        if updated == self._settings:
            return

        self._settings = updated
        self._save()

    def _normalize(self, settings: GameSettings) -> GameSettings:
        settings = self._normalize_language(settings)
        settings = self._normalize_geo_language(settings)
        settings = self._with_windowed_resolution(settings, settings.windowed_width, settings.windowed_height)
        return self._normalize_fullscreen_preferences(settings)

    def _normalize_language(self, settings: GameSettings) -> GameSettings:
        known_codes = {option.code for option in self.LANGUAGE_OPTIONS}
        if settings.language_code in known_codes:
            return settings
        return replace(settings, language_code="en")

    def _normalize_geo_language(self, settings: GameSettings) -> GameSettings:
        normalized_code = normalize_geo_language_code(settings.geo_language_code)
        if normalized_code == settings.geo_language_code:
            return settings
        return replace(settings, geo_language_code=normalized_code)

    def _normalize_fullscreen_preferences(self, settings: GameSettings) -> GameSettings:
        screens = self.fullscreen_screen_options()
        if not screens:
            return replace(
                settings,
                fullscreen_screen_index=max(0, int(settings.fullscreen_screen_index)),
                fullscreen_mode_width=max(640, int(settings.fullscreen_mode_width)),
                fullscreen_mode_height=max(480, int(settings.fullscreen_mode_height)),
                fullscreen_mode_rate=max(1, int(settings.fullscreen_mode_rate)),
            )

        resolved_screen_index = self._resolve_screen_index(settings.fullscreen_screen_index, screens)
        screen = screens[resolved_screen_index]
        mode = choose_best_mode(
            screen.modes,
            settings.fullscreen_mode_width,
            settings.fullscreen_mode_height,
            settings.fullscreen_mode_rate,
        )
        if mode is None:
            return replace(settings, fullscreen_screen_index=resolved_screen_index)

        return replace(
            settings,
            fullscreen_screen_index=resolved_screen_index,
            fullscreen_mode_width=mode.width,
            fullscreen_mode_height=mode.height,
            fullscreen_mode_rate=mode.rate,
        )

    def _resolve_fullscreen_choice(self) -> tuple[DisplayScreenOption | None, DisplayModeOption | None]:
        screens = self.fullscreen_screen_options()
        if not screens:
            return None, None

        screen_index = self._resolve_screen_index(None, screens)
        screen = screens[screen_index]
        mode = choose_best_mode(
            screen.modes,
            self._settings.fullscreen_mode_width,
            self._settings.fullscreen_mode_height,
            self._settings.fullscreen_mode_rate,
        )
        return screen, mode

    def _resolve_screen_index(
        self,
        value: int | None = None,
        screens: tuple[DisplayScreenOption, ...] | None = None,
    ) -> int:
        if screens is None:
            screens = self.fullscreen_screen_options()
        if value is None:
            value = self._settings.fullscreen_screen_index
        return clamp_index(value, len(screens))

    def _with_windowed_resolution(self, settings: GameSettings, width: int, height: int) -> GameSettings:
        return replace(
            settings,
            windowed_width=max(800, int(width)),
            windowed_height=max(600, int(height)),
        )

    def _read_window_size(self, window) -> tuple[int, int]:
        if hasattr(window, "get_size"):
            width, height = window.get_size()
            return int(width), int(height)
        return self._settings.windowed_width, self._settings.windowed_height

    def _save(self) -> None:
        self._repository.save(self._settings)
