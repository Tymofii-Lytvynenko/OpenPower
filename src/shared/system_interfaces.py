from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, List, Mapping, Protocol, runtime_checkable

from src.shared.actions import GameAction
from src.shared.state import GameState


class SystemPhase(IntEnum):
    CLOCK = 10
    BOOTSTRAP = 20
    POPULATION = 30
    TERRITORY = 31
    STRATEGY = 40
    RANDOM_EVENTS = 41
    DIPLOMACY = 50
    POLITICS = 60
    RESEARCH = 61
    TRADE = 62
    ECONOMY = 70
    MILITARY = 80
    BUDGET = 81
    COMBAT = 82
    POST_PROCESS = 90


@dataclass(frozen=True)
class SystemAccess:
    """Required system resources, command routes, and scheduling phase."""

    reads: frozenset[str] = field(default_factory=frozenset)
    writes: frozenset[str] = field(default_factory=frozenset)
    handles: frozenset[type[GameAction]] = field(default_factory=frozenset)
    phase: int = 100


@runtime_checkable
class ISystem(Protocol):
    access: SystemAccess

    @property
    def id(self) -> str:
        ...

    @property
    def dependencies(self) -> List[str]:
        ...

    def update(self, state: GameState, delta_time: float) -> None:
        ...


@runtime_checkable
class ICheckpointedSystem(Protocol):
    def export_persistent_state(self) -> dict[str, Any]:
        ...

    def import_persistent_state(self, data: Mapping[str, Any]) -> None:
        ...


def system_access(system: object) -> SystemAccess:
    system_id = getattr(system, "id", type(system).__name__)
    declaration = getattr(system, "access", None)
    if declaration is None:
        raise RuntimeError(f"System '{system_id}' must declare a SystemAccess contract.")
    if not isinstance(declaration, SystemAccess):
        raise TypeError(
            f"System '{system_id}' access must be SystemAccess, "
            f"got {type(declaration).__name__}."
        )
    invalid_actions = [
        action_type
        for action_type in declaration.handles
        if not isinstance(action_type, type) or not issubclass(action_type, GameAction)
    ]
    if invalid_actions:
        raise TypeError(
            f"System '{system_id}' handles contains non-GameAction types: "
            f"{invalid_actions}."
        )
    return declaration
