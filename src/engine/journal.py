from __future__ import annotations

from src.shared.determinism import DeterministicRuntime
from src.shared.events import DomainGameEvent
from src.shared.state import GameState


class DomainEventJournal:
    """Promotes transient domain signals into deterministic persistent records."""

    def capture(self, state: GameState) -> tuple[dict[str, object], ...]:
        tick = int(state.globals.get("tick", 0))
        runtime = DeterministicRuntime(state.determinism)
        captured: list[dict[str, object]] = []
        for event in state.events:
            if not isinstance(event, DomainGameEvent):
                continue
            captured.append(
                state.journal.append_domain_event(
                    event,
                    event_id=runtime.next_id("event", tick),
                    tick=tick,
                    source="simulation",
                )
            )
        return tuple(captured)
