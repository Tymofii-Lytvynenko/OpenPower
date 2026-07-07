from typing import Any, List, Mapping, Protocol, runtime_checkable
from src.shared.state import GameState
from src.shared.actions import GameAction


@runtime_checkable
class ISystem(Protocol):
    """
    Interface for all ECS systems with Dependency Graph support.
    """

    @property
    def id(self) -> str:
        """
        Unique identifier for the system (e.g., 'base.economy').
        Namespace convention: 'mod_id.system_name'
        """
        ...

    @property
    def dependencies(self) -> List[str]:
        """
        List of system IDs that must execute BEFORE this system.
        Example: ['base.territory', 'base.time']
        """
        ...

    def update(self, state: GameState, delta_time: float) -> None:
        """
        Performs the logic for a single tick.
        """
        ...


@runtime_checkable
class ICheckpointedSystem(Protocol):
    """
    Optional protocol for systems with mutable runtime state that must survive save/load.
    """

    def export_persistent_state(self) -> dict[str, Any]:
        ...

    def import_persistent_state(self, data: Mapping[str, Any]) -> None:
        ...
