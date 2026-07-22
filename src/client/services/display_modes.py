from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence


@dataclass(frozen=True, slots=True)
class DisplayModeOption:
    width: int
    height: int
    rate: int
    label: str
    mode: Any


@dataclass(frozen=True, slots=True)
class DisplayScreenOption:
    index: int
    label: str
    width: int
    height: int
    modes: tuple[DisplayModeOption, ...]
    screen: Any


class DisplayCatalog(Protocol):
    def list_screens(self) -> tuple[DisplayScreenOption, ...]:
        ...


def clamp_index(index: int, count: int) -> int:
    if count <= 0:
        return 0
    return max(0, min(int(index), count - 1))


def choose_best_mode(
    modes: Sequence[DisplayModeOption],
    target_width: int,
    target_height: int,
    target_rate: int,
) -> DisplayModeOption | None:
    if not modes:
        return None

    width = max(1, int(target_width))
    height = max(1, int(target_height))
    rate = max(1, int(target_rate))

    exact = next(
        (
            mode
            for mode in modes
            if mode.width == width and mode.height == height and mode.rate == rate
        ),
        None,
    )
    if exact is not None:
        return exact

    same_resolution = [
        mode for mode in modes if mode.width == width and mode.height == height
    ]
    if same_resolution:
        return min(same_resolution, key=lambda mode: abs(mode.rate - rate))

    return min(
        modes,
        key=lambda mode: (
            abs(mode.width - width) * 1000
            + abs(mode.height - height) * 1000
            + abs(mode.rate - rate)
        ),
    )


class ArcadeDisplayCatalog:
    def list_screens(self) -> tuple[DisplayScreenOption, ...]:
        import arcade

        screens = tuple(arcade.get_screens())
        return tuple(
            self._build_screen_option(index, screen)
            for index, screen in enumerate(screens)
        )

    def _build_screen_option(self, index: int, screen: Any) -> DisplayScreenOption:
        return DisplayScreenOption(
            index=index,
            label=self._build_screen_label(index, screen),
            width=max(1, int(getattr(screen, "width", 0))),
            height=max(1, int(getattr(screen, "height", 0))),
            modes=self._build_mode_options(screen),
            screen=screen,
        )

    def _build_screen_label(self, index: int, screen: Any) -> str:
        width = max(1, int(getattr(screen, "width", 0)))
        height = max(1, int(getattr(screen, "height", 0)))
        return f"Display {index + 1} ({width}x{height})"

    def _build_mode_options(self, screen: Any) -> tuple[DisplayModeOption, ...]:
        # The OS often reports the same resolution multiple times for the same
        # refresh rate. We collapse those duplicates so the combo box stays readable.
        seen: set[tuple[int, int, int]] = set()
        modes: list[DisplayModeOption] = []
        for mode in screen.get_modes():
            width = max(1, int(getattr(mode, "width", 0)))
            height = max(1, int(getattr(mode, "height", 0)))
            rate = max(1, int(getattr(mode, "rate", 60) or 60))
            key = (width, height, rate)
            if key in seen:
                continue
            seen.add(key)
            modes.append(
                DisplayModeOption(
                    width=width,
                    height=height,
                    rate=rate,
                    label=self._build_mode_label(width, height, rate),
                    mode=mode,
                )
            )

        modes.sort(key=lambda option: (-option.width * option.height, -option.rate))
        return tuple(modes)

    def _build_mode_label(self, width: int, height: int, rate: int) -> str:
        return f"{width}x{height} @ {rate}Hz"
