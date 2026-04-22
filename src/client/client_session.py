import multiprocessing as mp
from typing import Optional
from pathlib import Path

from src.server.state import GameState
from src.shared.actions import GameAction
from src.server.server_process import run_server_process

from src.core.map_data import RegionMapData
from src.shared.config import GameConfig

class ClientSessionProxy:
    """
    A proxy object that lives in the main UI thread.
    It handles communication with the background Simulation Process.
    """
    
    def __init__(self, config: GameConfig):
        # Create Communication Pipes
        self.action_queue = mp.Queue()
        self.state_queue = mp.Queue()
        self.progress_queue = mp.Queue()
        
        self.state: Optional[GameState] = None
        
        map_path = None
        for data_dir in config.get_data_dirs():
            candidate = data_dir / "regions" / "regions.png"
            if candidate.exists():
                map_path = candidate
                break
        if not map_path:
            map_path = config.get_asset_path("map/regions.png")
            
        print(f"[ClientProxy] Loading UI map data from: {map_path}")
        self.map_data = RegionMapData(str(map_path))
        # ----------------------------------------------------

        # Spawn the Background Process
        self.process = mp.Process(
            target=run_server_process,
            args=(str(config.project_root), self.action_queue, self.state_queue, self.progress_queue),
            daemon=True # Ensures process dies if window is closed abruptly
        )
        self.process.start()

    def receive_action(self, action: GameAction):
        """Sends an action to the background server."""
        self.action_queue.put(action)

    def tick(self, delta_time: float):
        """
        Called by the Window. Grabs the latest pre-calculated state from the server.
        """
        try:
            latest_ipc = None
            while not self.state_queue.empty():
                latest_ipc = self.state_queue.get_nowait()
                
            if latest_ipc:
                old_tables = self.state.tables if self.state else {}
                self.state = GameState.from_ipc(latest_ipc)
                for name, df in old_tables.items():
                    if name not in self.state.tables:
                        self.state.tables[name] = df
        except Exception:
            pass

    def get_state_snapshot(self) -> Optional[GameState]:
        return self.state

    def shutdown(self):
        self.action_queue.put("SHUTDOWN")
        self.process.join(timeout=2.0)
        if self.process.is_alive():
            self.process.terminate()