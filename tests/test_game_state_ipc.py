import unittest
import polars as pl
from src.shared.state import GameState

class TestGameStateIPC(unittest.TestCase):
    def test_ipc_roundtrip_all_tables(self):
        state = GameState()
        df_regions = pl.DataFrame({"id": [1, 2], "owner": ["USA", "CAN"]})
        df_trade = pl.DataFrame({
            "exporter_id": ["USA"], 
            "importer_id": ["WORLD"], 
            "game_resource_id": ["electricity"], 
            "trade_value_usd": [5000.0]
        })
        
        state.update_table("regions", df_regions)
        state.update_table("trade_network", df_trade)
        state.time.total_minutes = 300
        state.globals["tick"] = 5
        
        # 1. Roundtrip serialization
        ipc_data = state.to_ipc()
        self.assertIn("trade_network", ipc_data["tables"])  # Verify trade_network is NOT excluded
        
        # 2. Deserialization
        restored = GameState.from_ipc(ipc_data)
        self.assertEqual(restored.time.total_minutes, 300)
        self.assertEqual(restored.globals["tick"], 5)
        
        # 3. Assert content equality
        self.assertTrue(restored.get_table("regions").equals(df_regions))
        self.assertTrue(restored.get_table("trade_network").equals(df_trade))
