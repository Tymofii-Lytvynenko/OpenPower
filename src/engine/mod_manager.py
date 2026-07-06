import importlib
from typing import Dict, List

from src.engine.interfaces import ISystem
from src.shared.config import GameConfig
from src.shared.mods import ModManifest, discover_mods, resolve_mod_load_order


class ModManager:
    """
    Handles the discovery, dependency resolution, and loading of game modules.

    The discovery and load-order logic lives in src.shared.mods so the client,
    server, and tests all resolve the same mod stack instead of each layer
    improvising its own interpretation of mods.json.
    """

    def __init__(self, config: GameConfig):
        self.config = config
        self.modules_dir = config.project_root / "modules"
        self.loaded_mods: List[ModManifest] = []

    def resolve_load_order(self) -> List[ModManifest]:
        """
        Scans, resolves, and sorts mods based on dependencies.
        """
        print("[ModManager] Scanning for modules...")

        available_mods = self._discover_mods()
        if not available_mods:
            print(f"[ModManager] Warning: No mods found in {self.modules_dir}")
            return []

        sorted_mods = self._sort_mods(available_mods)
        self.loaded_mods = sorted_mods
        self.config.active_mods = [manifest.id for manifest in sorted_mods]
        print(f"[ModManager] Resolved Load Order: {self.config.active_mods}")
        return sorted_mods

    def load_systems(self) -> List[ISystem]:
        """
        Loads systems by calling the 'register()' function in each module's registration.py.
        """
        instantiated_systems: List[ISystem] = []

        for mod in self.loaded_mods:
            registration_module = f"modules.{mod.id}.registration"
            registration_path = mod.path / "registration.py"

            try:
                if registration_path.exists():
                    module = importlib.import_module(registration_module)

                    if hasattr(module, "register"):
                        print(f"[ModManager] Loading systems from {mod.id}...")
                        systems = module.register()

                        if isinstance(systems, list):
                            instantiated_systems.extend(systems)
                        else:
                            print(f"[ModManager] Error: {registration_module}.register() must return a list.")
                    else:
                        print(f"[ModManager] Warning: {registration_module} has no 'register()' function.")

            except Exception as e:
                print(f"[ModManager] Critical Error loading {mod.id}: {e}")
                import traceback

                traceback.print_exc()

        return instantiated_systems

    def _discover_mods(self) -> Dict[str, ModManifest]:
        return discover_mods(self.modules_dir)

    def _sort_mods(self, available: Dict[str, ModManifest]) -> List[ModManifest]:
        return resolve_mod_load_order(self.config.active_mods, available)
