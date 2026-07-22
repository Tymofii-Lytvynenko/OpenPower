from typing import Optional, Protocol

from src.shared.actions import GameAction
from src.shared.state import GameState


class SessionPort(Protocol):
    def receive_action(self, action: GameAction) -> str:
        ...

    def get_state_snapshot(self) -> Optional[GameState]:
        ...

    def save_map_changes(self) -> None:
        ...
