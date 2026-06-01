import multiprocessing as mp
from dataclasses import dataclass
from typing import Protocol, Optional
from src.shared.actions import GameAction
from src.shared.state import GameState
from src.core.map_data import RegionMapData

@dataclass
class ServerProcessBundle:
    map_data: RegionMapData
    action_queue: mp.Queue
    state_queue: mp.Queue
    progress_queue: mp.Queue
    process: mp.Process

class SessionPort(Protocol):
    def receive_action(self, action: GameAction) -> None:
        ...

    def get_state_snapshot(self) -> Optional[GameState]:
        ...

    def save_map_changes(self) -> None:
        ...
