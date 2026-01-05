import json
from pathlib import Path
from typing import List

class GameConfig:
    """
    Central configuration handler for the OpenPower engine.
    
    Responsibilities:
    1. Resolve file paths dynamically (removing hardcoded strings).
    2. Manage the Mod Load Order via 'mods.json'.
    3. Provide access to Data and Asset directories.
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        
        # Standard directory structure definitions
        self.modules_dir = project_root / "modules"
        self.cache_dir = project_root / ".cache"
        self.mods_file = project_root / "mods.json"
        
        # Default load order (can be overridden by mods.json)
        self.active_mods: List[str] = ["base"]
        self._load_mods_manifest()

    def _load_mods_manifest(self):
        """Attempts to read the load order from mods.json."""
        if not self.mods_file.exists():
            return

        try:
            with open(self.mods_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Expected format: {"active_mods": ["base", "my_mod"]}
                if "active_mods" in data and isinstance(data["active_mods"], list):
                    self.active_mods = data["active_mods"]
                    print(f"[Config] Active Mods: {self.active_mods}")
        except Exception as e:
            print(f"[Config] Warning: Failed to parse mods.json: {e}")

    def get_data_dirs(self) -> List[Path]:
        """
        Returns a list of data directories for all active mods.
        Used by DataLoader to scan for content.
        """
        paths = []
        for mod in self.active_mods:
            p = self.modules_dir / mod / "data"
            if p.exists():
                paths.append(p)
        return paths

    def get_write_data_dir(self) -> Path:
        """
        Returns the directory where the Editor should save changes.
        For MVP, we save to the 'base' module.
        """
        return self.modules_dir / "base" / "data"

    def get_asset_path(self, relative_path: str) -> Path:
        """
        Finds an asset (image/sound) by searching through active mods.
        """
        # Search in reverse order (Mods override Base)
        for mod in reversed(self.active_mods):
            candidate = self.modules_dir / mod / "assets" / relative_path
            if candidate.exists():
                return candidate
        
        # Fallback
        return self.modules_dir / "base" / "assets" / relative_path