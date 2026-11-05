"""Reusable linear slide timing for source GML panels."""
from dataclasses import dataclass


@dataclass(slots=True)
class GMLSlideTransition:
    """Track a delayed linear transition between two layout measurements.

    The source animation holds its initial position
    for a delay, then moves linearly for the configured duration.
    See docs/ui/reference/source_links.md for attribution.
    """

    value: float = 0.0
    target: float = 0.0
    start_value: float = 0.0
    start_at: float = 0.0
    duration: float = 0.5
    active: bool = False

    def snap(self, value: float) -> None:
        self.value = value
        self.target = value
        self.start_value = value
        self.active = False

    def begin(
        self,
        target: float,
        now: float,
        *,
        delay: float = 0.26,
        duration: float = 0.5,
    ) -> None:
        if delay < 0.0 or duration <= 0.0:
            raise ValueError("Slide delay must be non-negative and duration must be positive.")

        self.advance(now)
        self.start_value = self.value
        self.target = target
        self.start_at = now + delay
        self.duration = duration
        self.active = self.value != self.target

    def advance(self, now: float) -> float:
        if not self.active:
            return self.value
        if now <= self.start_at:
            return self.value

        progress = min(1.0, (now - self.start_at) / self.duration)
        self.value = self.start_value + (self.target - self.start_value) * progress
        if progress >= 1.0:
            self.value = self.target
            self.active = False
        return self.value
