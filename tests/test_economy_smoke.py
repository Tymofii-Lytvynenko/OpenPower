import unittest
from pathlib import Path
from src.shared.config import GameConfig
from src.engine.mod_manager import ModManager
from src.engine.simulator import Engine
from src.server.io.data_load_manager import DataLoader
from src.server.state_bootstrap import ensure_ui_support_tables

class TestEconomySmoke(unittest.TestCase):
    def test_one_cycle_simulation(self):
        project_root = Path(__file__).resolve().parent.parent
        config = GameConfig(project_root)
        config.active_mods = ["base"]
        
        # 1. Resolve and Load Mod
        mod_manager = ModManager(config)
        mod_manager.resolve_load_order()
        
        # 2. Load Real Initial Database
        loader = DataLoader(config)
        state = loader.load_initial_state()
        ensure_ui_support_tables(state)
        
        # 3. Register systems
        engine = Engine(dev_mode=True)
        systems = mod_manager.load_systems()
        engine.register_systems(systems)
        
        # 4. Step Engine (simulating 1.0 real-time second to trigger EventRealSecond updates)
        engine.step(state, [], 1.0)
        
        self.assertEqual(state.globals["tick"], 1)
        self.assertIn("regions", state.tables)
        self.assertIn("countries", state.tables)
        
        # Verify that BootstrapSystem successfully seeded tables on the first step
        self.assertIn("country_governments", state.tables)
        govs = state.get_table("country_governments")
        self.assertFalse(govs.is_empty())
