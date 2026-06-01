from pathlib import Path
from typing import List

class GameConfig:
    """
    Central configuration handler for the OpenPower engine.
    
    Responsibilities:
    1. Resolve file paths dynamically (removing hardcoded strings).
    2. Provide access to Data and Asset directories.
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        
        # Standard directory structure definitions
        self.modules_dir = self.project_root / "modules"
        self.cache_dir = self.project_root / ".cache"
        self.user_data_dir = self.project_root / "user_data"
        
        # Default load order.
        # This will be populated/overwritten by ModManager in GameSession.
        self.active_mods: List[str] = ["base"]

    def get_data_dirs(self) -> List[Path]:
        """
        Returns a list of data directories for all active mods.
        Used by DataLoader to scan for content.
        """
        # TODO: Add logic here to include active mods from mods.json
        return [self.project_root / "modules" / "base" / "data"]

    def get_write_data_dir(self) -> Path:
        """
        Returns the directory where the Editor should save changes.
        For MVP, we save to the 'base' module.
        """
        return self.modules_dir / "base" / "data"

    def get_asset_path(self, subpath: str) -> Path:
        """
        Finds an asset (image/sound) by searching through active mods.
        """
        return self.project_root / "modules" / "base" / "assets" / subpath
