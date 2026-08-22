from __future__ import annotations

from datetime import timedelta
from typing import Any

from src.shared.state import GAME_EPOCH


class ClientGameClock:
    """Smooth presentation clock reconciled against authoritative snapshots."""

    MINUTES_PER_SECOND = {
        1: 30.0,
        2: 60.0,
        3: 120.0,
        4: 600.0,
        5: 2400.0,
    }
    CORRECTION_WINDOW_SECONDS = 0.25

    def __init__(self) -> None:
        self._display_minutes: float | None = None
        self._pending_correction = 0.0
        self._speed_level = 1
        self._paused = True

    @property
    def display_minutes(self) -> float | None:
        return self._display_minutes

    def sync(self, time_data: Any) -> None:
        authoritative = max(
            0.0,
            float(getattr(time_data, "total_minutes", 0))
            + float(getattr(time_data, "_accumulator", 0.0)),
        )
        speed_level = max(1, min(5, int(getattr(time_data, "speed_level", 1))))
        paused = bool(getattr(time_data, "is_paused", False))
        control_state_changed = (
            speed_level != self._speed_level or paused != self._paused
        )

        if self._display_minutes is None or control_state_changed:
            self._display_minutes = authoritative
            self._pending_correction = 0.0
        else:
            error = authoritative - self._display_minutes
            hard_reset_threshold = max(
                5.0,
                self.MINUTES_PER_SECOND[speed_level] * 0.5,
            )
            if abs(error) > hard_reset_threshold:
                self._display_minutes = authoritative
                self._pending_correction = 0.0
            else:
                self._pending_correction = error

        self._speed_level = speed_level
        self._paused = paused

    def advance(self, delta_time: float) -> None:
        if self._display_minutes is None:
            return

        frame_seconds = max(0.0, min(float(delta_time), 0.25))
        natural_advance = 0.0
        if not self._paused:
            natural_advance = frame_seconds * self.MINUTES_PER_SECOND[self._speed_level]

        correction_fraction = min(
            1.0,
            frame_seconds / self.CORRECTION_WINDOW_SECONDS,
        )
        correction_step = self._pending_correction * correction_fraction
        if not self._paused:
            # Reconciliation may slow the clock, but an advancing clock must never run backward.
            correction_step = max(correction_step, -natural_advance * 0.95)

        self._display_minutes = max(
            0.0,
            self._display_minutes + natural_advance + correction_step,
        )
        self._pending_correction -= correction_step

    def date_text(self) -> str | None:
        if self._display_minutes is None:
            return None
        display_time = GAME_EPOCH + timedelta(minutes=self._display_minutes)
        return display_time.strftime("%Y-%m-%d %H:%M")
