"""Hold-repeat timing for source GML updatable-value arrows.

The cadence follows the source `GUpdatableValue` update loop; see
docs/ui/reference/source_links.md for attribution.
"""
from dataclasses import dataclass, field


@dataclass(slots=True)
class GMLValueRepeat:
    active: bool = False
    direction: int = 0
    repeat_count: int = 0
    next_repeat_at: float = 0.0

    def advance(
        self,
        value: int,
        *,
        active: bool,
        clicked: bool,
        direction: int,
        now: float,
        minimum: int,
        maximum: int,
        step_tiers: tuple[tuple[int, int], ...] = ((9, 10), (99, 100)),
    ) -> tuple[int, bool]:
        if direction not in {-1, 1}:
            raise ValueError("GML value repeat direction must be -1 or 1.")

        if active:
            if not self.active or self.direction != direction:
                self.active = True
                self.direction = direction
                self.repeat_count = 0
                self.next_repeat_at = now + 0.5
                return self._change(value, direction, minimum, maximum)
            if now > self.next_repeat_at:
                step = self._step_for_count(self.repeat_count, step_tiers)
                updated, changed = self._change(value, direction * step, minimum, maximum)
                self.repeat_count += 1
                self.next_repeat_at = now + self._repeat_interval(self.repeat_count)
                return updated, changed
            return value, False

        if clicked and not self.active:
            updated, changed = self._change(value, direction, minimum, maximum)
            self.reset()
            return updated, changed

        self.reset()
        return value, False

    def reset(self) -> None:
        self.active = False
        self.direction = 0
        self.repeat_count = 0
        self.next_repeat_at = 0.0

    @staticmethod
    def _change(value: int, delta: int, minimum: int, maximum: int) -> tuple[int, bool]:
        updated = min(maximum, max(minimum, value + delta))
        return updated, updated != value

    @staticmethod
    def _step_for_count(count: int, step_tiers: tuple[tuple[int, int], ...]) -> int:
        for threshold, step in reversed(step_tiers):
            if count >= threshold:
                return step
        return 1

    @staticmethod
    def _repeat_interval(count: int) -> float:
        if count > 75:
            return 0.005
        if count > 50:
            return 0.01
        if count > 35:
            return 0.05
        if count > 22:
            return 0.1
        if count > 12:
            return 0.15
        if count > 5:
            return 0.2
        return 0.25


@dataclass(slots=True)
class GMLValueRepeatPair:
    """Independent hold-repeat state for the two arrows of a value control."""

    down: GMLValueRepeat = field(default_factory=GMLValueRepeat)
    up: GMLValueRepeat = field(default_factory=GMLValueRepeat)

    def __getitem__(self, direction: str) -> GMLValueRepeat:
        if direction == "down":
            return self.down
        if direction == "up":
            return self.up
        raise KeyError(direction)

    def reset(self) -> None:
        self.down.reset()
        self.up.reset()
