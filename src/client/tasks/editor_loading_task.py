import time
from dataclasses import dataclass
from pathlib import Path
from src.server.session import GameSession
from src.shared.config import GameConfig
from src.shared.map.region_atlas import RegionAtlas
from src.client.services.network_client_service import NetworkClient

@dataclass
class EditorContext:
    """
    Container for assets loaded in the background thread.
    Passed to EditorView so it doesn't have to load them again.
    """
    map_path: Path
    atlas: RegionAtlas
    net_client: NetworkClient

class EditorLoadingTask:
    """
    Handles the heavy lifting of preparing the Editor.
    
    Why this is needed:
        The RegionAtlas uses OpenCV and NumPy to process the map image.
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
        # 1. Locate Map File
        self.status_text = "Locating map assets..."
        self.progress = 0.1
        
        map_path = self._resolve_map_path()
        time.sleep(0.1) # Brief pause to let UI render the text update

        # 2. Load Region Data (Heavy CPU Work)
        self.status_text = "Processing Region Atlas (CV2)..."
        self.progress = 0.3
        
        # We perform the heavy CV2/NumPy analysis here.
        # This is safe to do in a thread because it doesn't touch OpenGL.
        atlas = RegionAtlas(str(map_path), str(self.config.cache_dir))
        
        # 3. Initialize Network
        self.status_text = "Connecting to Session..."
        self.progress = 0.8
        
        net_client = NetworkClient(self.session)
        
        # 4. Finalize
        self.status_text = "Finalizing..."
        self.progress = 1.0
        
        return EditorContext(
            map_path=map_path,
            atlas=atlas,
            net_client=net_client
        )

    def _resolve_map_path(self) -> Path:
        """Logic extracted from EditorView to find the map file."""
        # Try Data Dirs first
        for data_dir in self.config.get_data_dirs():
            candidate = data_dir / "regions" / "regions.png"
            if candidate.exists():
                return candidate
        
        # Fallback to internal assets
        candidate = self.config.get_asset_path("map/regions.png")
        if candidate and candidate.exists():
            return candidate
            
        # Fallback to root (Critical error usually, but we return a path to fail gracefully later)
        return self.config.project_root / "missing_map_placeholder.png"