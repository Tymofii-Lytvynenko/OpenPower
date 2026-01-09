from imgui_bundle import imgui
import polars as pl
from typing import Optional
from src.server.state import GameState

class RegionInspectorPanel:
    def render(self, region_id: Optional[int], state: GameState):
        imgui.begin("Region Inspector")
        
        if region_id is None:
            imgui.text_disabled("Select a region to view details.")
            imgui.end()
            return

        try:
            regions = state.get_table("regions")
            # Efficient Polars lookup
            row = regions.filter(pl.col("id") == region_id).row(0, named=True)
            
            # Header
            imgui.text_colored((0, 1, 1, 1), f"REGION: {row.get('name', 'Unknown')}")
            imgui.separator()
            
            # Data
            imgui.text(f"ID: {region_id}")
            imgui.text(f"Owner: {row.get('owner', 'None')}")
            imgui.text(f"Biome: {row.get('biome', 'Unknown')}")
            
            # Demographics calculation
            pop = row.get('pop_14', 0) + row.get('pop_15_64', 0) + row.get('pop_65', 0)
            imgui.text(f"Total Population: {pop:,}")

        except Exception as e:
            imgui.text_colored((1, 0, 0, 1), f"Data Error: {e}")
            
        imgui.end()