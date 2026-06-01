from typing import List, Optional, Callable, TYPE_CHECKING
import polars as pl

from src.shared.config import GameConfig
from src.shared.actions import GameAction
from src.server.state_bootstrap import ensure_ui_support_tables

# Logic & Data Systems
from src.engine.mod_manager import ModManager
from src.server.io.data_load_manager import DataLoader
from src.server.io.data_export_manager import DataExporter
from src.engine.simulator import Engine
from src.core.map_data import RegionMapData

if TYPE_CHECKING:
    from src.shared.state import GameState

class GameSession:
    """
    The 'Host' of the game. It manages the lifecycle of the simulation.
    """

    def __init__(self, 
                 config: GameConfig, 
                 loader: DataLoader, 
                 exporter: DataExporter, 
                 engine: Engine,
                 map_data: RegionMapData,
                 initial_state: 'GameState'):
        self.config = config
        self.root_dir = config.project_root
        
        # Subsystems
        self.loader = loader
        self.exporter = exporter
        self.engine = engine
        self.map_data = map_data
        
        # Game Data
        self.state = initial_state
        ensure_ui_support_tables(self.state)
        self.action_queue: List[GameAction] = []
        
        print("[GameSession] Session initialized successfully.")

    @classmethod
    def create_local(cls, config: GameConfig, progress_cb: Optional[Callable[[float, str], None]] = None, save_name: Optional[str] = None) -> 'GameSession':
        """
        Factory Method: Orchestrates the full startup sequence for a Local Game.
        """
        def report(p: float, text: str):
            if progress_cb: progress_cb(p, text)

        try:
            # --- Step 1: Mod System (10%) ---
            report(0.1, "Server: Scanning and resolving mods...")
            mod_manager = ModManager(config)
            active_mods = mod_manager.resolve_load_order()
            config.active_mods = [m.id for m in active_mods]

            # --- Step 2: IO Initialization (20%) ---
            report(0.2, "Server: Initializing IO subsystems...")
            loader = DataLoader(config)
            exporter = DataExporter(config)

            # --- Step 3: World Data Loading (50%) ---
            report(0.3, "Server: Loading world database...")
            if save_name:
                initial_state = loader.load_save(save_name)
            else:
                initial_state = loader.load_initial_state()

            # --- Step 4: Map Data Processing (70%) ---
            report(0.6, "Server: Processing map data...")
            map_path = None
            for data_dir in config.get_data_dirs():
                candidate = data_dir / "regions" / "regions.png"
                if candidate.exists():
                    map_path = candidate
                    break
            
            if not map_path:
                map_path = config.get_asset_path("map/regions.png")

            map_data = RegionMapData(str(map_path))

            # --- Step 5: Engine & Systems (90%) ---
            report(0.8, "Server: Registering game systems...")
            engine = Engine(dev_mode=config.dev_mode)
            
            systems = mod_manager.load_systems()
            engine.register_systems(systems)

            # --- Step 6: Final Assembly (100%) ---
            report(1.0, "Server: Ready.")
            return cls(config, loader, exporter, engine, map_data, initial_state)

        except Exception as e:
            print(f"[GameSession] Critical Startup Error: {e}")
            raise e

    def tick(self, delta_time: float):
        if not self.action_queue and delta_time <= 0:
            return

        # Intercept ActionSaveGame on the server side
        from src.shared.actions import ActionSaveGame
        save_actions = [a for a in self.action_queue if isinstance(a, ActionSaveGame)]
        if save_actions:
            from src.server.io.save_writer import SaveWriter
            writer = SaveWriter(self.config)
            for action in save_actions:
                writer.save_game(self.state, action.save_name)
            self.action_queue = [a for a in self.action_queue if not isinstance(a, ActionSaveGame)]

        # Pass the instance method of the engine
        self.engine.step(self.state, self.action_queue, delta_time)
        self.action_queue.clear()

    def receive_action(self, action: GameAction):
        """
        Endpoint for Clients to submit commands.
        """
        self.action_queue.append(action)

    def get_state_snapshot(self) -> 'GameState':
        """
        Returns the data for rendering.
        """
        return self.state

    def save_map_changes(self):
        """
        Special command for the Editor to force a disk write.
        """
        self.exporter.save_regions(self.state)
