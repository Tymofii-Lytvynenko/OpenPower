import json
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
        
        self.dev_mode: bool = True  # Default to True for dev-mode fail-fast testing
        
        # Default load order.
        # This will be populated/overwritten by ModManager in GameSession.
        self.active_mods: List[str] = ["base"]
        
        mods_json_path = self.project_root / "mods.json"
        if mods_json_path.exists():
            try:
                with open(mods_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.active_mods = data.get("active_mods", ["base"])
            except Exception as e:
                print(f"[GameConfig] Failed to load mods.json: {e}")

    def get_data_dirs(self) -> List[Path]:
        """
        Returns a list of data directories for all active mods.
        Used by DataLoader to scan for content.
        """
        dirs = []
        for mod_id in self.active_mods:
            mod_data_dir = self.modules_dir / mod_id / "data"
            if mod_data_dir.exists():
                dirs.append(mod_data_dir)
        return dirs

    def get_write_data_dir(self) -> Path:
        """
        Returns the directory where the Editor should save changes.
        Writes to the last active mod's data directory.
        """
        if self.active_mods:
            return self.modules_dir / self.active_mods[-1] / "data"
        return self.modules_dir / "base" / "data"

    def get_asset_path(self, subpath: str) -> Path:
        """
        Finds an asset (image/sound) by searching through active mods.
        """
        for mod_id in reversed(self.active_mods):
            path = self.modules_dir / mod_id / "assets" / subpath
            if path.exists():
                return path
        return self.modules_dir / "base" / "assets" / subpath
