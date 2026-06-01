import time
import polars as pl
import arcade
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Any

from src.shared.config import GameConfig
from src.client.utils.coords_util import calculate_centroid

@dataclass
class NewGameContext:
    session: Any
    player_tag: str
    start_pos: Optional[tuple[float, float]]

class NewGameTask:
    def __init__(self, window: arcade.Window, config: GameConfig, player_tag: str):
        self.window = window
        self.config = config
        self.player_tag = player_tag
        self.progress: float = 0.0
        self.status_text: str = "Preparing Campaign..."

    def run(self) -> NewGameContext:
        # 1. Shutdown the old session if it exists
        self.status_text = "Stopping previous session..."
        self.progress = 0.05
        if hasattr(self.window, "session") and self.window.session:
            self.window.session.shutdown()
            
        # 2. Spawn a new clean server process via the launcher factory
        self.status_text = "Starting simulation server..."
        self.progress = 0.1
        from src.server.launcher import spawn_local_server
        from src.client.client_session import ClientSessionProxy
        bundle = spawn_local_server(self.config, save_name=None)
        new_session = ClientSessionProxy(
            map_data=bundle.map_data,
            action_queue=bundle.action_queue,
            state_queue=bundle.state_queue,
            progress_queue=bundle.progress_queue,
            process=bundle.process,
        )
        
        # 3. Monitor the progress queue until READY or ERROR
        while True:
            try:
                status, p, text = new_session.progress_queue.get(timeout=10.0)
                if status == "PROGRESS":
                    self.progress = 0.1 + p * 0.6
                    self.status_text = f"Server: {text}"
                elif status == "READY":
                    self.progress = 0.7
                    self.status_text = "Server process ready."
                    break
                elif status == "ERROR":
                    raise RuntimeError(text)
            except Exception as e:
                raise RuntimeError(f"Failed to initialize simulation server: {e}")
                
        # 4. Wait for first state update to populate starting pos
        self.status_text = "Synchronizing game state..."
        self.progress = 0.8
        
        start_time = time.perf_counter()
        while new_session.get_state_snapshot() is None:
            new_session.tick(0.0)
            if time.perf_counter() - start_time > 5.0:
                raise TimeoutError("Timed out waiting for initial game state.")
            time.sleep(0.05)
            
        state = new_session.get_state_snapshot()
        start_pos = None
        try:
            if "regions" in state.tables:
                df = state.tables["regions"]
                owned_regions = df.filter(pl.col("owner") == self.player_tag)
                map_height = new_session.map_data.height
                map_width = new_session.map_data.width
                start_pos = calculate_centroid(owned_regions, map_height, map_width)
        except Exception as e:
            print(f"Error calculating centroid: {e}")
            
        # 5. Warm up files
        self.status_text = "Pre-loading map assets..."
        self.progress = 0.9
        self._warmup_file("map/regions.png")
        self._warmup_file("map/terrain.png")
        
        self.progress = 1.0
        self.status_text = "Ready."
        
        return NewGameContext(new_session, self.player_tag, start_pos)

    def _warmup_file(self, asset_path_str: str):
        """Reads a file into void just to force OS caching."""
        path = self.config.get_asset_path(asset_path_str)
        if path and path.exists():
            with open(path, "rb") as f:
                f.read()
