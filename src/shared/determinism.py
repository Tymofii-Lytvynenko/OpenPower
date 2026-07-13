from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, TypeVar


_MASK_64 = (1 << 64) - 1
_NON_ZERO_SEED = 0x9E3779B97F4A7C15
_XORSHIFT_MULTIPLIER = 0x2545F4914F6CDD1D
T = TypeVar("T")


def _normalize_seed(seed: int) -> int:
    normalized = int(seed) & _MASK_64
    return normalized or _NON_ZERO_SEED


@dataclass
class DeterminismState:
    """Persistent state for deterministic randomness and identifier allocation."""

    seed: int = 1
    rng_state: int = 0
    id_sequence: int = 0

    def __post_init__(self) -> None:
        self.seed = _normalize_seed(self.seed)
        self.rng_state = _normalize_seed(self.rng_state or self.seed)
        self.id_sequence = max(0, int(self.id_sequence))

    def reset(self, seed: int) -> None:
        self.seed = _normalize_seed(seed)
        self.rng_state = self.seed
        self.id_sequence = 0


class DeterministicRuntime:
    """Small deterministic service composed over persisted runtime state."""

    def __init__(self, state: DeterminismState):
        self._state = state

    def next_u64(self) -> int:
        value = self._state.rng_state
        value ^= value >> 12
        value ^= (value << 25) & _MASK_64
        value ^= value >> 27
        self._state.rng_state = value & _MASK_64
        return (self._state.rng_state * _XORSHIFT_MULTIPLIER) & _MASK_64

    def random(self) -> float:
        return self.next_u64() / float(1 << 64)

    def uniform(self, lower: float, upper: float) -> float:
        return float(lower) + ((float(upper) - float(lower)) * self.random())

    def choice(self, values: Sequence[T]) -> T:
        if not values:
            raise IndexError("Cannot choose from an empty sequence.")
        return values[self.next_u64() % len(values)]

    def next_id(self, prefix: str, tick: int) -> str:
        self._state.id_sequence += 1
        normalized_prefix = "".join(
            character if character.isalnum() or character in {"-", "_"} else "-"
            for character in str(prefix)
        ).strip("-") or "id"
        return f"{normalized_prefix}-{max(0, int(tick)):09d}-{self._state.id_sequence:09d}"
