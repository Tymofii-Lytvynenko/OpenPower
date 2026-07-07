from typing import List, Optional, Callable, TYPE_CHECKING

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

    def __init__(
        self,
        config: GameConfig,
        loader: DataLoader,
        exporter: DataExporter,
        engine: Engine,
        map_data: RegionMapData | None,
        initial_state: 'GameState',
        player_tag: str | None = None,
    ):
        self.config = config
        self.root_dir = config.project_root

        # Subsystems
        self.loader = loader
        self.exporter = exporter
        self.engine = engine
        self.map_data = map_data

        # Game Data
        self.state = initial_state
        if player_tag:
            self.state.globals["player_tag"] = player_tag
        self.player_tag = self.state.globals.get("player_tag")
        self.engine.restore_system_state(self.state)
        self.engine.snapshot_system_state(self.state)
        ensure_ui_support_tables(self.state)
        self.action_queue: List[GameAction] = []

        print("[GameSession] Session initialized successfully.")

    @classmethod
    def create_local(
        cls,
        config: GameConfig,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        save_name: Optional[str] = None,
        load_map_data: bool = True,
        player_tag: str | None = None,
    ) -> 'GameSession':
        """
        Factory Method: Orchestrates the full startup sequence for a Local Game.
        """

        def report(progress: float, text: str) -> None:
            if progress_cb:
                progress_cb(progress, text)

        try:
            # --- Step 1: Mod System (10%) ---
            report(0.1, "Server: Scanning and resolving mods...")
            mod_manager = ModManager(config)
            active_mods = mod_manager.resolve_load_order()
            config.active_mods = [mod.id for mod in active_mods]

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

            # --- Step 4: Runtime Preparation (70%) ---
            report(0.6, "Server: Preparing simulation runtime...")
            map_data = cls._load_map_data(config) if load_map_data else None

            # --- Step 5: Engine & Systems (90%) ---
            report(0.8, "Server: Registering game systems...")
            engine = Engine(dev_mode=config.dev_mode)
            systems = mod_manager.load_systems()
            engine.register_systems(systems)

            # --- Step 6: Final Assembly (100%) ---
            report(1.0, "Server: Ready.")
            return cls(config, loader, exporter, engine, map_data, initial_state, player_tag=player_tag)

        except Exception as exc:
            print(f"[GameSession] Critical Startup Error: {exc}")
            raise exc

    @classmethod
    def create_headless(
        cls,
        config: GameConfig,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        save_name: Optional[str] = None,
        player_tag: str | None = None,
    ) -> 'GameSession':
        """
        Boots a simulation session without loading client-side map raster data.

        The server process only needs gameplay state and systems, so skipping the
        region image avoids unnecessary startup work in headless environments.
        """
        return cls.create_local(
            config,
            progress_cb=progress_cb,
            save_name=save_name,
            load_map_data=False,
            player_tag=player_tag,
        )

    @staticmethod
    def _load_map_data(config: GameConfig) -> RegionMapData:
        for data_dir in config.get_data_dirs():
            candidate = data_dir / "regions" / "regions.png"
            if candidate.exists():
                return RegionMapData(str(candidate))
        return RegionMapData(str(config.get_asset_path("map/regions.png")))

    def tick(self, delta_time: float):
        if not self.action_queue and delta_time <= 0:
            return

        # Intercept ActionSaveGame on the server side
        from src.shared.actions import ActionSaveGame

        save_actions = [action for action in self.action_queue if isinstance(action, ActionSaveGame)]
        if save_actions:
            from src.server.io.save_writer import SaveWriter

            writer = SaveWriter(self.config)
            self.engine.snapshot_system_state(self.state)
            for action in save_actions:
                writer.save_game(self.state, action.save_name)
            self.action_queue = [action for action in self.action_queue if not isinstance(action, ActionSaveGame)]

        # Pass the instance method of the engine
        self.engine.step(self.state, self.action_queue, delta_time)
        self.engine.snapshot_system_state(self.state)
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
