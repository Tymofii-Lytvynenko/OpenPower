import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class EconomyPanel:
    def __init__(self, toggle_resources_cb=None):
        self.toggle_resources_cb = toggle_resources_cb

    def render(self, state, **kwargs) -> bool:
        target_tag = kwargs.get("target_tag", "")
        is_own = kwargs.get("is_own_country", False)

        with WindowManager.window("ECONOMY", x=1600, y=100, w=260, h=450) as is_open:
            if not is_open: return False
            self._render_content(state, target_tag, is_own)
            return True

    def _render_content(self, state, target_tag, is_own):
        # --- 1. Fetch Economy Data ---
        reserves = 0.0
        gdp_per_capita = 0.0
        total_gdp = 0.0
        
        # Internal tax rate synced with EconomySystem baseline
        internal_tax_rate = 0.20 
        
        if "countries" in state.tables:
            try:
                df = state.tables["countries"]
                row = df.filter(pl.col("id") == target_tag)
                if not row.is_empty():
                    val = row["money_reserves"][0]
                    reserves = float(val) if val is not None else 0.0
                    
                    if "gdp_per_capita" in row.columns:
                        val_gdp_pc = row["gdp_per_capita"][0]
                        gdp_per_capita = float(val_gdp_pc) if val_gdp_pc is not None else 0.0
                        
                    if "gdp" in row.columns:
                        val_gdp = row["gdp"][0]
                        total_gdp = float(val_gdp) if val_gdp is not None else 0.0
            except Exception:
                pass

        # Calculate projected internal baseline income
        calculated_income = total_gdp * internal_tax_rate

        # --- 2. Render UI ---
        
        # Economic Model Section
        Prims.header("MACROECONOMIC POLICY")
        
        imgui.push_style_color(imgui.Col_.frame_bg, GAMETHEME.colors.bg_popup)
        imgui.push_style_color(imgui.Col_.slider_grab, GAMETHEME.colors.accent)
        
        if not is_own: imgui.begin_disabled()
        
        # Visual representation of State Control vs Free Market dominance
        imgui.slider_float("##eco_model", 0.35, 0.0, 1.0, "")
        
        if not is_own: imgui.end_disabled()

        imgui.pop_style_color(2)
        
        imgui.text_disabled("State-Controlled")
        imgui.same_line()
        Prims.right_align_text("Free Market", GAMETHEME.colors.text_dim)
        imgui.dummy((0, 5))

        # GDP Section
        Prims.header(f"GDP: ${total_gdp:,.0f}")
        
        # Assuming max standard GDP scale around 1T for health metering
        gdp_health = min((total_gdp / 1_000_000_000_000) * 100, 100.0)
        Prims.meter("", gdp_health, GAMETHEME.colors.positive) 
        
        imgui.text_disabled(f"Per Capita: ${gdp_per_capita:,.0f}")
        imgui.dummy((0, 5))

        # Budget Section
        Prims.header("STATE BUDGET")
        
        # Baseline Income (GDP Tax)
        Prims.currency_row("INTERNAL REVENUE", calculated_income)
        
        # Stubs for dynamic trade revenues/expenses that happen mid-tick
        Prims.currency_row("TRADE TARIFFS", 0.0) 
        Prims.currency_row("STATE IMPORTS", 0.0)
        
        imgui.dummy((0, 5))
        if is_own:
            col_res = GAMETHEME.colors.negative if reserves < 0 else GAMETHEME.colors.positive
            Prims.currency_row("TREASURY RESERVES", reserves, col_res)
        else:
            imgui.text("TREASURY RESERVES")
            imgui.same_line()
            Prims.right_align_text("Classified", GAMETHEME.colors.text_dim)
        
        imgui.dummy((0, 8))

        # Resources Section
        Prims.header("RESOURCES")
        if imgui.button("OPEN RESOURCES DIRECTORY", (-1, 30)):
            if self.toggle_resources_cb:
                self.toggle_resources_cb()
        
        imgui.dummy((0, 15))
        
        # Footer Action
        if is_own:
            if imgui.button("TRADE POLICIES", (-1, 35)): pass
        else:
            if imgui.button("PROPOSE TRADE AGREEMENT", (-1, 35)): pass