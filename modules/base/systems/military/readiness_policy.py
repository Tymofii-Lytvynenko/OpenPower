"""Pure rules for military unit readiness postures."""

from __future__ import annotations

from dataclasses import dataclass


READINESS_PARKED = "parked"
READINESS_READY = "ready"
READINESS_FORTIFIED = "fortified"
READINESS_STATUSES = frozenset({READINESS_PARKED, READINESS_READY, READINESS_FORTIFIED})


@dataclass(frozen=True, slots=True)
class ReadinessTransition:
    stage: str
    from_status: str
    target_status: str
    duration_minutes: int


class ReadinessPolicy:
    """Keeps posture names, transition timings, and combat modifiers deterministic."""

    # These durations are intentionally coarse strategic-time values. They are
    # easy to rebalance without changing persistence or system orchestration.
    PARKED_TO_READY_MINUTES = 2 * 24 * 60
    READY_TO_FORTIFIED_MINUTES = 2 * 24 * 60
    PARKED_TO_FORTIFIED_MINUTES = 4 * 24 * 60

    _WEIGHTS = {
        READINESS_PARKED: 0.25,
        READINESS_READY: 1.0,
        READINESS_FORTIFIED: 1.5,
    }

    def normalize(self, value: object) -> str:
        status = str(value or "").strip().lower()
        return status if status in READINESS_STATUSES else READINESS_READY

    def combat_weight(self, status: object) -> float:
        return self._WEIGHTS[self.normalize(status)]

    def transition(self, current: object, target: object) -> ReadinessTransition | None:
        source = self.normalize(current)
        destination = self.normalize(target)
        if source == destination:
            return None
        if source == READINESS_PARKED and destination == READINESS_FORTIFIED:
            # This request is persisted as two visible stages: garrison to
            # ready, then ready to fortified. The first stage is two days.
            return ReadinessTransition("parked_to_fortified", source, destination, self.PARKED_TO_READY_MINUTES)
        if source == READINESS_PARKED and destination == READINESS_READY:
            return ReadinessTransition("parked_to_ready", source, destination, self.PARKED_TO_READY_MINUTES)
        if source == READINESS_READY and destination == READINESS_FORTIFIED:
            return ReadinessTransition("ready_to_fortified", source, destination, self.READY_TO_FORTIFIED_MINUTES)
        # Returning from a defensive posture is immediate in the MVP: the unit
        # can leave prepared positions without creating another hidden queue.
        return ReadinessTransition("direct", source, destination, 0)

    def progress(self, started_at: int, completes_at: int, now: int) -> float:
        duration = max(1, completes_at - started_at)
        return max(0.0, min(1.0, (now - started_at) / duration))
