from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import orjson


@dataclass(frozen=True, slots=True)
class LanguageOption:
    code: str
    label: str
    is_stub: bool = True


@dataclass(frozen=True, slots=True)
class GameSettings:
    fullscreen: bool = False
    language_code: str = "en"
    windowed_width: int = 1280
    windowed_height: int = 720


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
            windowed_width=self._read_int(payload, "windowed_width", 1280, minimum=800),
            windowed_height=self._read_int(payload, "windowed_height", 720, minimum=600),
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

    def __init__(self, repository: GameSettingsRepository):
        self._repository = repository
        self._settings = self._normalize(repository.load())

    @classmethod
    def from_path(cls, path: Path) -> "GameSettingsService":
        return cls(GameSettingsRepository(path))

    @property
    def settings(self) -> GameSettings:
        return self._settings

    @property
    def language_options(self) -> tuple[LanguageOption, ...]:
        return self.LANGUAGE_OPTIONS

    @property
    def selected_language_index(self) -> int:
        for index, option in enumerate(self.LANGUAGE_OPTIONS):
            if option.code == self._settings.language_code:
                return index
        return 0

    @property
    def selected_language(self) -> LanguageOption:
        return self.LANGUAGE_OPTIONS[self.selected_language_index]

    def set_language_by_index(self, index: int) -> None:
        if not 0 <= index < len(self.LANGUAGE_OPTIONS):
            return

        option = self.LANGUAGE_OPTIONS[index]
        self._settings = replace(self._settings, language_code=option.code)
        self._save()

    def set_fullscreen(self, enabled: bool, window=None) -> None:
        self._settings = replace(self._settings, fullscreen=enabled)
        if window is not None:
            self.apply_display(window)
        self._save()

    def toggle_fullscreen(self, window) -> None:
        self.set_fullscreen(not self._settings.fullscreen, window)

    def apply_display(self, window) -> None:
        is_fullscreen = bool(getattr(window, "fullscreen", False))
        if self._settings.fullscreen == is_fullscreen:
            return

        if self._settings.fullscreen:
            width, height = window.get_size()
            self._settings = replace(
                self._settings,
                windowed_width=max(800, int(width)),
                windowed_height=max(600, int(height)),
            )
            window.set_fullscreen(True)
            return

        window.set_fullscreen(
            False,
            width=float(self._settings.windowed_width),
            height=float(self._settings.windowed_height),
        )
        if hasattr(window, "center_window"):
            window.center_window()

    def remember_windowed_size(self, width: int, height: int) -> None:
        if self._settings.fullscreen:
            return

        self._settings = replace(
            self._settings,
            windowed_width=max(800, int(width)),
            windowed_height=max(600, int(height)),
        )

    def _normalize(self, settings: GameSettings) -> GameSettings:
        known_codes = {option.code for option in self.LANGUAGE_OPTIONS}
        if settings.language_code in known_codes:
            return settings
        return replace(settings, language_code="en")

    def _save(self) -> None:
        self._repository.save(self._settings)
