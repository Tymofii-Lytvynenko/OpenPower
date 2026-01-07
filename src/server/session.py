from typing import List, Optional, Callable, TYPE_CHECKING
from pathlib import Path

from src.shared.config import GameConfig
from src.shared.actions import GameAction

# Logic & Data Systems
# (Adjusted imports to match your project structure provided in the snippet)
from src.engine.mod_manager import ModManager
from src.server.io.data_load_manager import DataLoader
from src.server.io.data_export_manager import DataExporter
from src.engine.simulator import Engine
from src.shared.map.region_atlas import RegionAtlas

if TYPE_CHECKING:
    from src.server.state import GameState

class GameSession:
    """
    The 'Host' of the game. It manages the lifecycle of the simulation.

    Architecture Note:
        This class uses the Factory Method pattern (`create_local`).
        The `__init__` method is lightweight and strictly for Dependency Injection.
        Heavy loading logic is handled in `create_local` to allow the Client UI
        to display a progress bar.
    """

    def __init__(self, 
                 config: GameConfig, 
                 loader: DataLoader, 
                 exporter: DataExporter, 
                 engine: Engine,
                 atlas: RegionAtlas,
                 initial_state: 'GameState'):
        """
        Internal Constructor.
        Receives fully initialized subsystems. Do not call this directly to load a game.
        Use `GameSession.create_local()` instead.
        """
        self.config = config
        self.root_dir = config.project_root
        
        # Subsystems (Injected)
        self.loader = loader
        self.exporter = exporter
        self.engine = engine
        self.atlas = atlas
        
        # Game Data
        self.state = initial_state
        self.action_queue: List[GameAction] = []
        
        print("[GameSession] Session initialized successfully.")

    @classmethod
    def create_local(cls, config: GameConfig, progress_cb: Optional[Callable[[float, str], None]] = None) -> 'GameSession':
        """
        Factory Method: Orchestrates the full startup sequence for a Local Single-Player Game.
        
        Responsibilities:
            1. Resolve Mods.
            2. Initialize IO (Loader/Exporter).
            3. Parse Data (TSV tables).
            4. Compile Graphics (Atlas).
            5. Initialize Engine & Systems.
        
        Args:
            config: Game paths and settings.
            progress_cb: Callback(fraction, text) for the Loading Screen UI.
        """
        def report(p: float, text: str):
            if progress_cb: progress_cb(p, text)

        try:
            # --- Step 1: Mod System (10%) ---
            report(0.1, "Server: Scanning and resolving mods...")
            mod_manager = ModManager(config)
            
            # Build dependency graph and load order
            active_mods = mod_manager.resolve_load_order()
            
            # Update config so subsequent systems know which mods are active
            config.active_mods = [m.id for m in active_mods]

            # --- Step 2: IO Initialization (20%) ---
            report(0.2, "Server: Initializing IO subsystems...")
            loader = DataLoader(config)
            exporter = DataExporter(config)

            # --- Step 3: World Data Loading (50%) ---
            # This is usually the heaviest IO step (parsing TSVs)
            report(0.3, "Server: Loading world database...")
            initial_state = loader.load_initial_state()

            # --- Step 4: Map/Atlas Compilation (70%) ---
            # Heavy CPU/GPU operation (processing the regions.png image)
            report(0.6, "Server: Compiling region atlas...")
            
            # Resolve map path logic
            map_path = None
            for data_dir in config.get_data_dirs():
                candidate = data_dir / "regions" / "regions.png"
                if candidate.exists():
                    map_path = candidate
                    break
            
            if not map_path:
                map_path = config.get_asset_path("map/regions.png")

            atlas = RegionAtlas(str(map_path), str(config.cache_dir))

            # --- Step 5: Engine & Systems (90%) ---
            report(0.8, "Server: Registering game systems...")
            engine = Engine()
            
            # Load Python logic defined in mods
            systems = mod_manager.load_systems()
            engine.register_systems(systems)

            # --- Step 6: Final Assembly (100%) ---
            report(1.0, "Server: Ready.")
            
            # Create the instance with all prepared data
            return cls(config, loader, exporter, engine, atlas, initial_state)

        except Exception as e:
            print(f"[GameSession] Critical Startup Error: {e}")
            raise e

    def tick(self, delta_time: float):
        if not self.action_queue and delta_time <= 0:
            return

        # Pass the instance method of the engine
        self.engine.step(self.state, self.action_queue, delta_time)
        
        self.action_queue.clear()

    def receive_action(self, action: GameAction):
        """
        Endpoint for Clients to submit commands.
        In the future, this will be connected to a TCP/UDP socket.
        """
        # TODO: Add validation here (e.g., "Is Player X allowed to move Unit Y?")
        self.action_queue.append(action)

    def get_state_snapshot(self) -> GameState:
        """
        Returns the data for rendering.
        
        Network Note:
            In a real network implementation, this would serialise 
            the GameState (or a delta) to Apache Arrow bytes.
            For local single-player, we just return the object reference (Zero-Copy).
        """
        return self.state

    def save_map_changes(self):
        """
        Special command for the Editor to force a disk write.
        """
        self.exporter.save_regions(self.state)
