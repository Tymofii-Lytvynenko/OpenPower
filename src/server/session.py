from typing import List, Optional, Callable, TYPE_CHECKING

import polars as pl

from src.shared.config import GameConfig
from src.shared.actions import ActionUpdateResourcePolicy, GameAction

# Logic & Data Systems
from src.engine.mod_manager import ModManager
from src.server.io.data_load_manager import DataLoader
from src.server.io.data_export_manager import DataExporter
from src.engine.simulator import Engine

# UPDATED: Import the headless map data handler from Core
from src.core.map_data import RegionMapData

if TYPE_CHECKING:
    from src.server.state import GameState

class GameSession:
    """
    The 'Host' of the game. It manages the lifecycle of the simulation.

    Architecture Note:
        This class uses the Factory Method pattern (`create_local`).
        The `__init__` method is lightweight and strictly for Dependency Injection.
        Heavy loading logic is handled in `create_local`.
    """

    def __init__(self, 
                 config: GameConfig, 
                 loader: DataLoader, 
                 exporter: DataExporter, 
                 engine: Engine,
                 map_data: RegionMapData, # UPDATED Type Hint
                 initial_state: 'GameState'):
        """
        Internal Constructor.
        Receives fully initialized subsystems. Do not call directly.
        Use `GameSession.create_local()` instead.
        """
        self.config = config
        self.root_dir = config.project_root
        
        # Subsystems (Injected)
        self.loader = loader
        self.exporter = exporter
        self.engine = engine
        self.map_data = map_data # UPDATED Attribute
        
        # Game Data
        self.state = initial_state
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
            
            # Build dependency graph and load order
            active_mods = mod_manager.resolve_load_order()
            
            # Update config so subsequent systems know which mods are active
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
            # UPDATED: We now load the map using OpenCV via Core (Headless safe)
            report(0.6, "Server: Processing map data...")
            
            # Resolve map path logic
            map_path = None
            for data_dir in config.get_data_dirs():
                candidate = data_dir / "regions" / "regions.png"
                if candidate.exists():
                    map_path = candidate
                    break
            
            if not map_path:
                map_path = config.get_asset_path("map/regions.png")

            # Initialize the Core MapData component
            map_data = RegionMapData(str(map_path))

            # --- Step 5: Engine & Systems (90%) ---
            report(0.8, "Server: Registering game systems...")
            engine = Engine()
            
            # Load Python logic defined in mods
            systems = mod_manager.load_systems()
            engine.register_systems(systems)

            # --- Step 6: Final Assembly (100%) ---
            report(1.0, "Server: Ready.")
            
            # Create the instance with all prepared data
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
        # TODO: Add validation here (e.g., "Is Player X allowed to move Unit Y?")
        # Apply these edits immediately because the current ruleset has no
        # simulation system that consumes ActionUpdateResourcePolicy yet.
        if isinstance(action, ActionUpdateResourcePolicy):
            self._apply_resource_policy_action(action)
            return

        self.action_queue.append(action)

    def _apply_resource_policy_action(self, action: ActionUpdateResourcePolicy) -> None:
        if "domestic_production" not in self.state.tables:
            return

        df = self.state.get_table("domestic_production")
        expressions = []
        if "is_gov_controlled" not in df.columns:
            expressions.append(pl.lit(False).alias("is_gov_controlled"))
        if "is_legal" not in df.columns:
            expressions.append(pl.lit(True).alias("is_legal"))
        if "tax_rate" not in df.columns:
            expressions.append(pl.lit(0.0).alias("tax_rate"))
        if expressions:
            df = df.with_columns(expressions)

        tax_rate = max(0.0, min(1.0, float(action.tax_rate)))
        target = (
            (pl.col("country_id") == action.country_tag)
            & (pl.col("game_resource_id") == action.resource_id)
        )

        updated = df.with_columns([
            pl.when(target)
            .then(pl.lit(bool(action.is_gov_controlled)))
            .otherwise(pl.col("is_gov_controlled"))
            .alias("is_gov_controlled"),
            pl.when(target)
            .then(pl.lit(bool(action.is_legal)))
            .otherwise(pl.col("is_legal"))
            .alias("is_legal"),
            pl.when(target)
            .then(pl.lit(tax_rate))
            .otherwise(pl.col("tax_rate"))
            .alias("tax_rate"),
        ])
        self.state.update_table("domestic_production", updated)

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
