import polars as pl
from imgui_bundle import imgui
from src.client.ui.panels.base_panel import BasePanel
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME

class RegionInspectorPanel(BasePanel):
    def __init__(self):
        super().__init__("Region Inspector", x=400, y=200, w=300, h=480)
        self.filter_text: str = ""
        self._cached_list: list = []
        self._cache_dirty = True

    def _render_content(self, composer: UIComposer, state, **kwargs):
        # Extract data passed from GameLayout
        region_id = kwargs.get("selected_region_id")
        on_focus_request = kwargs.get("on_focus_request")

        if region_id is None:
            imgui.text_disabled("Select a region on the map\nto view its statistics.")
        else:
            self._render_details(region_id, state, on_focus_request)

    def _render_details(self, region_id, state, on_focus_request):
        """Internal helper to render specific region stats."""
        try:
            regions = state.get_table("regions")
            row_df = regions.filter(pl.col("id") == region_id)
            
            if row_df.is_empty():
                imgui.text_colored(GAMETHEME.colors.error, "Region not found in database.")
                return

            row = row_df.row(0, named=True)
            imgui.text_colored(GAMETHEME.colors.accent, f"NAME: {row.get('name', '???')}")
            
            if on_focus_request and imgui.button("CENTER CAMERA"):
                on_focus_request(region_id) # The ViewportController handles the logic

            imgui.separator()
            imgui.text(f"ID: {region_id}")
            imgui.text(f"Owner: {row.get('owner', 'Neutral')}")
            imgui.text(f"Biome: {row.get('biome', 'N/A')}")
            
            pop = row.get('pop_14', 0) + row.get('pop_15_64', 0) + row.get('pop_65', 0)
            imgui.text(f"Total Population: {pop:,}")
            
        except Exception as e:
            imgui.text_disabled(f"Error loading data: {e}")

    def _update_filter_cache(self, state, filter_text: str):
        """
        Rebuilds the UI list from the dataframe.
        (Kept for future features, though not actively used in the current compact inspector)
        """
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