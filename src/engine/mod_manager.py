import json
import importlib.util
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Set, Type

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
    
    This class implements a Topological Sort to ensure that base mods are 
    loaded before the mods that depend on them.
    """
    
    def __init__(self, config: GameConfig):
        self.config = config
        self.modules_dir = config.project_root / "modules"
        self.loaded_mods: List[ModManifest] = []

    def resolve_load_order(self) -> List[ModManifest]:
        """
        Scans the modules directory and returns a list of mods sorted by dependency order.
        Raises an error if dependencies are missing or circular.
        """
        print("[ModManager] Scanning for modules...")
        available_mods: Dict[str, ModManifest] = {}
        
        # 1. Discovery
        if not self.modules_dir.exists():
            print(f"[ModManager] Warning: Modules directory not found at {self.modules_dir}")
            return []

        for mod_dir in self.modules_dir.iterdir():
            if not mod_dir.is_dir(): continue
            
            manifest_path = mod_dir / "mod.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        manifest = ModManifest(
                            id=data.get("id", mod_dir.name),
                            name=data.get("name", mod_dir.name),
                            version=data.get("version", "0.0.1"),
                            dependencies=data.get("dependencies", []),
                            path=mod_dir
                        )
                        available_mods[manifest.id] = manifest
                except Exception as e:
                    print(f"[ModManager] Failed to load manifest for {mod_dir.name}: {e}")

        # 2. Dependency Resolution (Topological Sort)
        sorted_mods: List[ModManifest] = []
        visited: Set[str] = set()
        temp_mark: Set[str] = set() # Used for cycle detection

        def visit(mod_id: str):
            if mod_id in temp_mark:
                raise RuntimeError(f"Circular dependency detected involving '{mod_id}'")
            if mod_id in visited:
                return
            
            if mod_id not in available_mods:
                raise RuntimeError(f"Missing dependency: '{mod_id}' required but not found.")

            temp_mark.add(mod_id)
            
            # Visit dependencies first
            for dep_id in available_mods[mod_id].dependencies:
                visit(dep_id)
            
            temp_mark.remove(mod_id)
            visited.add(mod_id)
            sorted_mods.append(available_mods[mod_id])

        # We prioritize 'active_mods' from config if specified, otherwise load all
        # For now, let's load everything we found to ensure the graph is complete.
        # Ideally, you'd start 'visit' only for mods enabled in user config.
        for mod_id in available_mods:
            if mod_id not in visited:
                try:
                    visit(mod_id)
                except RuntimeError as e:
                    print(f"[ModManager] CRITICAL: {e}")
                    # In production, we might want to halt or skip this mod tree
                    raise e

        self.loaded_mods = sorted_mods
        print(f"[ModManager] Resolved Load Order: {[m.id for m in sorted_mods]}")
        return sorted_mods

    def load_systems(self) -> List[ISystem]:
        """
        Instantiates System classes defined in the loaded mods.
        
        Convention:
        Mods must have a 'systems' subpackage or file (e.g., modules/base/systems/*.py).
        Any class in these files implementing ISystem will be instantiated.
        """
        instantiated_systems: List[ISystem] = []

        for mod in self.loaded_mods:
            systems_dir = mod.path / "systems"
            if not systems_dir.exists():
                continue

            # Scan python files in the systems directory
            for py_file in systems_dir.glob("*.py"):
                if py_file.name.startswith("_"): continue

                module_name = f"modules.{mod.id}.systems.{py_file.stem}"
                
                try:
                    # Dynamic Import
                    spec = importlib.util.spec_from_file_location(module_name, py_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)
                        
                        # Inspect for ISystem classes
                        for attr_name in dir(module):
                            cls = getattr(module, attr_name)
                            # Check if it's a class, implements ISystem, and isn't the abstract protocol itself
                            if (isinstance(cls, type) and 
                                issubclass(cls, ISystem) and 
                                cls is not ISystem and 
                                cls.__module__ == module_name): # Ensure we don't pick up imported classes
                                
                                print(f"[ModManager] Registering system: {cls.__name__} from {mod.id}")
                                instantiated_systems.append(cls())
                                
                except Exception as e:
                    print(f"[ModManager] Error loading system from {py_file}: {e}")

        return instantiated_systems