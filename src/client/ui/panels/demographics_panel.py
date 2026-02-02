import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class DemographicsPanel:
    def render(self, state, **kwargs) -> bool:
        target_tag = kwargs.get("target_tag", "")
        is_own = kwargs.get("is_own_country", False)

        with WindowManager.window("DEMOGRAPHICS", x=10, y=350, w=240, h=480) as is_open:
            if not is_open: return False
            self._render_content(state, target_tag, is_own)
            return True

    def _render_content(self, state, target_tag, is_own):
        # --- 1. Aggregation Logic ---
        total_pop = 0
        pop_14 = 0
        pop_15_64 = 0
        pop_65 = 0
        
        if "regions" in state.tables:
            try:
                df = state.tables["regions"]
                # Filter by active target (could be foreign)
                target_regions = df.filter(pl.col("owner") == target_tag)
                
                if not target_regions.is_empty():
                    pop_14 = target_regions.select(pl.col("pop_14")).sum().item()
                    pop_15_64 = target_regions.select(pl.col("pop_15_64")).sum().item()
                    pop_65 = target_regions.select(pl.col("pop_65")).sum().item()
                    total_pop = pop_14 + pop_15_64 + pop_65
            except Exception as e:
                print(f"[Demographics] Error: {e}")

        # Calculate percentages
        pct_14 = (pop_14 / total_pop * 100) if total_pop > 0 else 0
        pct_15_64 = (pop_15_64 / total_pop * 100) if total_pop > 0 else 0
        pct_65 = (pop_65 / total_pop * 100) if total_pop > 0 else 0

        # --- 2. Render UI ---
        
        # Total Population
        Prims.header("POPULATION SUMMARY")

        imgui.text("Total:")
        imgui.same_line()
        # Right align the number
        Prims.right_align_text(f"{total_pop:,}", GAMETHEME.colors.accent)
        
        imgui.dummy((0, 5))

        # Age Structure
        Prims.header("AGE STRUCTURE", show_bg=False)
        
        Prims.meter(f"Youth: {pop_14:,}", pct_14, (0.4, 0.7, 1.0, 1.0))
        Prims.meter(f"Working: {pop_15_64:,}", pct_15_64, (0.3, 0.8, 0.4, 1.0))
        Prims.meter(f"Elderly: {pop_65:,}", pct_65, (0.8, 0.4, 0.4, 1.0))

        # Development Metrics
        Prims.header("DEVELOPMENT")
        
        human_dev_index = 0.0
        if "countries_dem" in state.tables:
            try:
                dem_df = state.tables["countries_dem"]
                row = dem_df.filter(pl.col("id") == target_tag)
                if not row.is_empty():
                    human_dev_index = float(row["human_dev"][0])
            except: pass

        Prims.meter("HDI Score", human_dev_index, GAMETHEME.colors.info)
        
        imgui.dummy((0, 15))
        
        # Action Buttons
        if is_own:
            if imgui.button("MIGRATION POLICY", (-1, 30)): pass
            if imgui.button("SOCIAL PROGRAMS", (-1, 30)): pass
        else:
            imgui.text_disabled("Internal Policies Restricted")