from pathlib import Path
from typing import List

from src.server.state import GameState
from src.server.io.data_load_manager import DataLoader
from src.server.io.data_export_manager import DataExporter
from src.engine.mod_manager import ModManager
from src.engine.simulator import Engine
from src.shared.actions import GameAction
from src.shared.config import GameConfig

class GameSession:
    """
    The 'Host' of the game. It manages the lifecycle of the simulation.
    """
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.config = GameConfig(root_dir)
        
        # 1. Initialize Mod System
        # We must resolve mods BEFORE loading data or systems.
        self.mod_manager = ModManager(self.config)
        
        # This builds the dependency graph and determines valid load order
        active_mods = self.mod_manager.resolve_load_order()
        
        # Update config so DataLoader knows where to look for TSV files
        # (Assuming GameConfig has a method or list for this)
        self.config.active_mods = [m.id for m in active_mods] 

        # 2. Initialize IO subsystems
        self.loader = DataLoader(self.config)
        self.exporter = DataExporter(self.config)
        self.engine = Engine() # Instance the Engine
        
        # 3. Load the World Data (Tables)
        self.state: GameState = self.loader.load_initial_state()
        
        # 4. Load and Register Logic (Systems)
        systems = self.mod_manager.load_systems()
        self.engine.register_systems(systems)
        
        self.action_queue: List[GameAction] = []

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