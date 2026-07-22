from pathlib import Path
from typing import List

from src.shared.mods import load_requested_mods, resolve_project_mods


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

        # Keep both the user-requested list and the resolved dependency stack.
        # The client needs the same mod order as the server so layered data and
        # assets resolve consistently during startup.
        self.requested_mods: List[str] = ["base"]
        self.active_mods: List[str] = ["base"]

        try:
            self.requested_mods = load_requested_mods(self.project_root)
            self.active_mods = [manifest.id for manifest in resolve_project_mods(self.project_root)]
            if not self.active_mods:
                self.active_mods = self.requested_mods
        except Exception as e:
            # Fall back to the raw mods.json order so tooling can still inspect
            # project paths while the startup error is surfaced elsewhere.
            print(f"[GameConfig] Failed to resolve active mods: {e}")
            try:
                self.requested_mods = load_requested_mods(self.project_root)
                self.active_mods = self.requested_mods
            except Exception as load_error:
                print(f"[GameConfig] Failed to load mods.json: {load_error}")

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
