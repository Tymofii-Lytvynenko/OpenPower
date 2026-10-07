from typing import Optional, Protocol, runtime_checkable

from src.shared.actions import GameAction
from src.shared.state import GameState


@runtime_checkable
class SessionPort(Protocol):
    def receive_action(self, action: GameAction) -> str:
        ...

    def get_state_snapshot(self) -> Optional[GameState]:
        ...

    def save_map_changes(self) -> None:
        ...
