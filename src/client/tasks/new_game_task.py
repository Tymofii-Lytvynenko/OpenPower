import time
import polars as pl
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from src.shared.config import GameConfig
from src.server.session import GameSession
from src.client.utils.coords_util import calculate_centroid

@dataclass
class NewGameContext:
    session: GameSession
    player_tag: str
    start_pos: Optional[tuple[float, float]]

class NewGameTask:
    def __init__(self, session: GameSession, config: GameConfig, player_tag: str):
        self.session = session
        self.config = config
        self.player_tag = player_tag
        self.progress: float = 0.0
        self.status_text: str = "Preparing Campaign..."

    def run(self) -> NewGameContext:
        # 1. Start
        self.status_text = f"Initializing {self.player_tag}..."
        self.progress = 0.1
        time.sleep(0.2) 

        # 2. Math (CPU)
        self.status_text = "Calculating strategic positions..."
        self.progress = 0.4
        
        state = self.session.get_state_snapshot()
        start_pos = None
        try:
            if "regions" in state.tables:
                df = state.tables["regions"]
                owned_regions = df.filter(pl.col("owner") == self.player_tag)
                map_height = self.session.map_data.height
                map_width = self.session.map_data.width
                start_pos = calculate_centroid(owned_regions, map_height, map_width)
        except Exception as e:
            print(f"Error: {e}")

        # 3. Disk I/O Warmup (The Performance Trick)
        # We read the heavy map files here in the thread so they are in RAM
        # when the main thread asks for them.
        self.status_text = "Pre-loading map assets..."
        self.progress = 0.7
        
        self._warmup_file("map/regions.png")
        self._warmup_file("map/terrain.png")

        # 4. Done
        self.status_text = "Ready."
        self.progress = 1.0
        # No sleep needed here, LoadingView's new delay will handle the visual transition
        
        return NewGameContext(self.session, self.player_tag, start_pos)

    def _warmup_file(self, asset_path_str: str):
        """Reads a file into void just to force OS caching."""
        path = self.config.get_asset_path(asset_path_str)
        if path and path.exists():
            with open(path, "rb") as f:
                f.read()
