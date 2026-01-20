from typing import Protocol, List, runtime_checkable
from src.server.state import GameState
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