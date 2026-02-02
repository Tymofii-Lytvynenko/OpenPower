import polars as pl
from imgui_bundle import imgui
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.containers import WindowManager

class RegionInspectorPanel:
    def render(self, state, **kwargs) -> bool:
        region_id = kwargs.get("selected_region_id")
        on_focus_request = kwargs.get("on_focus_request")

        with WindowManager.window("INSPECTOR", x=400, y=200, w=300, h=400) as is_open:
            if not is_open: return False
            
            if region_id is None:
                imgui.text_disabled("Select a region...")
                return True

            self._render_details(state, region_id, on_focus_request)
            return True

    def _render_details(self, state, region_id, on_focus):
        if "regions" not in state.tables: return
        
        row_df = state.tables["regions"].filter(pl.col("id") == region_id)
        if row_df.is_empty():
            imgui.text_colored(GAMETHEME.colors.error, "Invalid Region ID")
            return

        row = row_df.row(0, named=True)
        imgui.text_colored(GAMETHEME.colors.accent, row.get('name', 'Unknown'))
        
        imgui.separator()
        imgui.text(f"ID: {region_id}")
        imgui.text(f"Owner: {row.get('owner', 'N/A')}")
        imgui.text(f"Biome: {row.get('biome', 'N/A')}")
        
        if on_focus and imgui.button("Center Camera"):
            on_focus(region_id)