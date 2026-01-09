import rtoml
import importlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Set

from src.shared.config import GameConfig
from src.engine.interfaces import ISystem

@dataclass
class ModManifest:
    id: str
    name: str
    version: str
    dependencies: List[str] = field(default_factory=list)
    path: Path = field(default_factory=Path)

class ModManager:
    """
    Handles the discovery, dependency resolution, and loading of game modules.
    
    Refactored Logic:
    - Instead of automatically scanning folders, it looks for a 'registration.py' 
      entry point in each module.
    - Calls the 'register()' function to get the list of Systems.
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
        
        # 1. Discovery
        available_mods = self._discover_mods()
        if not available_mods:
            print(f"[ModManager] Warning: No mods found in {self.modules_dir}")
            return []

        # 2. Topological Sort (Base -> Dependent Mods)
        sorted_mods = self._sort_mods(available_mods)
        
        self.loaded_mods = sorted_mods
        print(f"[ModManager] Resolved Load Order: {[m.id for m in sorted_mods]}")
        return sorted_mods

    def load_systems(self) -> List[ISystem]:
        """
        Loads systems by calling the 'register()' function in each module's registration.py.
        """
        instantiated_systems: List[ISystem] = []

        for mod in self.loaded_mods:
            # Construct the expected python module path (e.g., modules.base.registration)
            registration_module = f"modules.{mod.id}.registration"
            registration_path = mod.path / "registration.py"
            
            try:
                # 1. Check if the file exists before trying to import
                if registration_path.exists():
                    # This relies on the project root being in sys.path
                    module = importlib.import_module(registration_module)
                    
                    # 2. Check for 'register' function
                    if hasattr(module, "register"):
                        print(f"[ModManager] Loading systems from {mod.id}...")
                        
                        # 3. Execute logic (Allows module to instantiate classes with args)
                        systems = module.register()
                        
                        if isinstance(systems, list):
                            instantiated_systems.extend(systems)
                        else:
                            print(f"[ModManager] Error: {registration_module}.register() must return a list.")
                    else:
                        print(f"[ModManager] Warning: {registration_module} has no 'register()' function.")
                
            except Exception as e:
                print(f"[ModManager] Critical Error loading {mod.id}: {e}")
                # Print stack trace for debugging mod errors
                import traceback
                traceback.print_exc()

        return instantiated_systems

    # =========================================================================
    # Internal Discovery & Sorting
    # =========================================================================

    def _discover_mods(self) -> Dict[str, ModManifest]:
        found = {}
        if not self.modules_dir.exists():
            return found

        for mod_dir in self.modules_dir.iterdir():
            if not mod_dir.is_dir(): continue
            
            manifest_path = mod_dir / "mod.toml"
            if manifest_path.exists():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        data = rtoml.load(f)
                        
                    manifest = ModManifest(
                        id=data.get("id", mod_dir.name),
                        name=data.get("name", mod_dir.name),
                        version=data.get("version", "0.0.1"),
                        dependencies=data.get("dependencies", []),
                        path=mod_dir
                    )
                    found[manifest.id] = manifest
                except Exception as e:
                    print(f"[ModManager] Failed to load manifest for {mod_dir.name}: {e}")
        return found

    def _sort_mods(self, available: Dict[str, ModManifest]) -> List[ModManifest]:
        """Topological Sort to ensure base mods load first."""
        sorted_list = []
        visited = set()
        temp_mark = set()

        def visit(mod_id: str):
            if mod_id in temp_mark:
                raise RuntimeError(f"Circular dependency: {mod_id}")
            if mod_id in visited:
                return
            
            if mod_id not in available:
                raise RuntimeError(f"Missing dependency: '{mod_id}'")

            temp_mark.add(mod_id)
            for dep in available[mod_id].dependencies:
                visit(dep)
            temp_mark.remove(mod_id)
            
            visited.add(mod_id)
            sorted_list.append(available[mod_id])

        for mid in available:
            if mid not in visited:
                visit(mid)
                    
        return sorted_list