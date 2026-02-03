import time
from dataclasses import dataclass
from pathlib import Path
from src.server.session import GameSession
from src.shared.config import GameConfig
from src.core.paths import ProjectPaths
# UPDATED: Import Core Data class instead of Shared Atlas
from src.core.map_data import RegionMapData
from src.client.services.network_client_service import NetworkClient

@dataclass
class EditorContext:
    """
    Container for assets loaded in the background thread.
    Passed to EditorView so it doesn't have to load them again.
    """
    map_path: Path
    terrain_path: Path      # Path to the artistic background (terrain)
    map_data: RegionMapData # Pre-calculated OpenCV/NumPy data (CPU Only)
    net_client: NetworkClient

class EditorLoadingTask:
    """
    Handles the heavy lifting of preparing the Editor.
    
    Why this is needed:
        The RegionMapData uses OpenCV and NumPy to process the map image.
        On large maps (4k+), this can take 1-5 seconds. Doing this on the
        main thread would freeze the UI. 
    """

    def __init__(self, session: GameSession, config: GameConfig):
        self.session = session
        self.config = config
        
        # LoadingTask Protocol
        self.progress: float = 0.0
        self.status_text: str = "Preparing Editor..."

    def run(self) -> EditorContext:
        """
        Executed in background thread by LoadingView.
        """
        # 1. Locate Map Assets
        self.status_text = "Locating map assets..."
        self.progress = 0.1
        
        map_path = self._resolve_map_path()
        terrain_path = self._resolve_terrain_path()
        
        # Brief sleep ensures the UI thread has a chance to render the text update
        # before the heavy CPU blocking operation starts.
        time.sleep(0.1) 

        # 2. Load Region Data (Heavy CPU Work)
        self.status_text = "Processing Region Data (CV2)..."
        self.progress = 0.3
        
        # UPDATED: We use the Core class. 
        # This is safe to run in a thread because it touches no OpenGL context.
        # It just does math on pixels.
        map_data = RegionMapData(str(map_path))
        
        # 3. Initialize Network
        self.status_text = "Connecting to Session..."
        self.progress = 0.8
        
        net_client = NetworkClient(self.session)
        
        # 4. Finalize
        self.status_text = "Finalizing..."
        self.progress = 1.0
        
        return EditorContext(
            map_path=map_path,
            terrain_path=terrain_path,
            map_data=map_data,
            net_client=net_client
        )

    def _resolve_map_path(self) -> Path:
        """
        Finds the technical region map (defined by specific RGB colors).
        """
        # Try Data Dirs first (User modded content)
        for data_dir in self.config.get_data_dirs():
            candidate = data_dir / "regions" / "regions.png"
            if candidate.exists():
                return candidate
        
        # Fallback to internal assets (Core game content)
        candidate = self.config.get_asset_path("map/regions.png")
        if candidate and candidate.exists():
            return candidate
            
        # Fallback to root (Critical error usually, but we return a path to fail gracefully later)
        return self.config.project_root / "missing_map_placeholder.png"

    def _resolve_terrain_path(self) -> Path:
        """
        Finds the artistic terrain background.
        Convention: It lives in the same folder as regions.png usually.
        """
        # Check standard location in assets
        candidate = self.config.get_asset_path("map/terrain.png")
        if candidate and candidate.exists():
            return candidate

        # Return a non-existent path if not found; the renderer handles this gracefully.
        return self.config.project_root / "missing_terrain_placeholder.png"