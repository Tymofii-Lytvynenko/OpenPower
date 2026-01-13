from imgui_bundle import imgui
import polars as pl
from typing import Optional, Callable
from src.server.state import GameState
from src.client.ui.theme import GAMETHEME

class RegionInspectorPanel:
    def __init__(self):
        # Filter State
        self.filter_text: str = ""
        
        # Cache to prevent slow dataframe filtering every frame
        # List of tuples: (id, name, owner, cx, cy)
        self._cached_list: list = []
        self._cache_dirty = True

    def render(self, region_id: Optional[int], state: GameState, on_focus_request: Callable[[int, float, float], None]):
        """
        Args:
            region_id: Currently selected ID
            state: GameState for data lookup
            on_focus_request: Callback(region_id, x, y) to trigger camera jump
        """
        imgui.begin("Region Inspector")

        # --- 1. REGION FINDER LIST ---
        if imgui.collapsing_header("Region Finder", True):
            imgui.text("Filter (Name or Owner):")
            
            # Input Text
            changed, self.filter_text = imgui.input_text("##filter", self.filter_text)
            if changed:
                self._cache_dirty = True
            
            # Refresh Cache if needed
            if self._cache_dirty or (not self._cached_list and "regions" in state.tables):
                self._update_filter_cache(state, self.filter_text)

            # List Box (Fixed Height)
            if imgui.begin_list_box("##region_list", (-1, 150)):
                if not self._cached_list:
                    imgui.text_disabled("No matches found.")
                
                for item in self._cached_list:
                    rid, rname, rowner, rcx, rcy = item
                    
                    label = f"{rname} ({rowner})"
                    is_selected = (region_id == rid)
                    
                    if imgui.selectable(label, is_selected)[0]:
                        on_focus_request(rid, float(rcx), float(rcy))
                
                imgui.end_list_box()

        imgui.separator()
        imgui.dummy((0, 10))

        # --- 2. DETAILS PANEL ---
        if region_id is None:
            imgui.text_disabled("Select a region to view details.")
            imgui.end()
            return

        try:
            regions = state.get_table("regions")
            row_df = regions.filter(pl.col("id") == region_id)
            
            if row_df.is_empty():
                imgui.text_colored(GAMETHEME.col_error, "Region Data Not Found")
                imgui.end()
                return

            row = row_df.row(0, named=True)
            
            # Title
            imgui.text_colored(GAMETHEME.col_accent_main, f"REGION: {row.get('name', 'Unknown')}")
            
            # Focus Button
            imgui.same_line()
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x - 60)
            if imgui.button("FOCUS"):
                 cx = row.get("center_y", 0)
                 cy = row.get("center_x", 0)
                 on_focus_request(region_id, float(cx), float(cy))

            imgui.separator()
            
            # Info
            imgui.text(f"ID: {region_id}")
            imgui.text(f"Owner: {row.get('owner', 'None')}")
            imgui.text(f"Biome: {row.get('biome', 'Unknown')}")
            
            # Population
            pop = row.get('pop_14', 0) + row.get('pop_15_64', 0) + row.get('pop_65', 0)
            imgui.text(f"Total Pop: {pop:,}")

        except Exception as e:
            imgui.text_colored(GAMETHEME.col_error, f"Data Error: {e}")
            
        imgui.end()

    def _update_filter_cache(self, state: GameState, filter_text: str):
        """Rebuilds the UI list from the dataframe."""
        try:
            if "regions" not in state.tables: return

            df = state.tables["regions"]
            txt = filter_text.lower()
            
            cols = ["id", "name", "owner", "center_x", "center_y"]

            if not txt:
                res = df.select(cols).sort("name").head(50)
            else:
                res = df.filter(
                    pl.col("name").str.to_lowercase().str.contains(txt) | 
                    pl.col("owner").str.to_lowercase().str.contains(txt)
                ).select(cols).head(50)

            self._cached_list = res.rows()
            self._cache_dirty = False
            
        except Exception as e:
            print(f"[RegionInspector] Filter Error: {e}")
            self._cached_list = []