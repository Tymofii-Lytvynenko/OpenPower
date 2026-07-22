from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FixedStepClock:
    """Converts wall-clock elapsed time into deterministic simulation steps."""

    step_seconds: float = 0.1
    max_catch_up_steps: int = 5
    accumulator: float = 0.0

    def __post_init__(self) -> None:
        if self.step_seconds <= 0:
            raise ValueError("Fixed step duration must be positive.")
        if self.max_catch_up_steps < 1:
            raise ValueError("max_catch_up_steps must be at least one.")

    def consume(self, elapsed_seconds: float) -> tuple[float, ...]:
        elapsed = max(0.0, float(elapsed_seconds))
        max_accumulator = self.step_seconds * self.max_catch_up_steps
        self.accumulator = min(self.accumulator + elapsed, max_accumulator)

        steps = min(
            int((self.accumulator + 1e-12) / self.step_seconds),
            self.max_catch_up_steps,
        )
        if steps:
            self.accumulator -= steps * self.step_seconds
            if self.accumulator < 1e-12:
                self.accumulator = 0.0
        return (self.step_seconds,) * steps
