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

        # Uses WindowManager context instead of Inheritance
        with WindowManager.window("ECONOMY", x=1600, y=100, w=260, h=450) as is_open:
            if not is_open: return False
            self._render_content(state, target_tag, is_own)
            return True

    def _render_content(self, state, target_tag, is_own):
        # --- 1. Fetch Economy Data ---
        reserves = -25000000000 
        gdp_per_capita = 0
        total_gdp = 0.0
        tax_rate = 0.2 
        
        if "countries" in state.tables:
            try:
                df = state.tables["countries"]
                row = df.filter(pl.col("id") == target_tag)
                if not row.is_empty():
                    val = row["money_reserves"][0]
                    reserves = float(val) if val is not None else 0.0
                    
                    if "gdp_per_capita" in row.columns:
                        val_gdp_pc = row["gdp_per_capita"][0]
                        gdp_per_capita = int(val_gdp_pc) if val_gdp_pc is not None else 0
                        
                    if "gdp" in row.columns:
                        val_gdp = row["gdp"][0]
                        total_gdp = float(val_gdp) if val_gdp is not None else 0.0
                    
                    if "global_tax_rate" in row.columns:
                        val_tax = row["global_tax_rate"][0]
                        tax_rate = float(val_tax) if val_tax is not None else 0.2
            except Exception:
                pass

        calculated_income = total_gdp * tax_rate

        # --- 4. Render UI ---
        
        # Economic Model Section
        Prims.header("ECONOMIC MODEL")
        
        imgui.push_style_color(imgui.Col_.frame_bg, GAMETHEME.colors.bg_popup)
        imgui.push_style_color(imgui.Col_.slider_grab, GAMETHEME.colors.accent)
        
        # Disable interaction if foreign country
        if not is_own: imgui.begin_disabled()
        
        imgui.slider_float("##eco_model", 0.2, 0.0, 1.0, "")
        
        if not is_own: imgui.end_disabled()

        imgui.pop_style_color(2)
        
        imgui.text_disabled("State-Controlled")
        imgui.same_line()
        # Custom alignment using primitives logic
        Prims.right_align_text("Free Market", GAMETHEME.colors.text_dim)
        imgui.dummy((0, 5))

        # GDP Section
        Prims.header(f"GDP: ${total_gdp:,.0f}")
        
        gdp_health = min((total_gdp / 1000000000000) * 100, 100.0)
        Prims.meter("", gdp_health, GAMETHEME.colors.positive) 
        
        imgui.text_disabled(f"Per Capita: ${gdp_per_capita:,}")
        imgui.dummy((0, 5))

        # Budget Section
        Prims.header("BUDGET")
        
        Prims.currency_row("INCOME", calculated_income)
        
        expenses = 0 # Placeholder
        Prims.currency_row("EXPENSES", expenses)
        
        balance = calculated_income - expenses
        col_bal = GAMETHEME.colors.negative if balance < 0 else GAMETHEME.colors.positive
        Prims.currency_row("BALANCE", balance, col_bal)
        
        # Maybe hide exact reserves if not own country?
        if is_own:
            col_res = GAMETHEME.colors.negative if reserves < 0 else GAMETHEME.colors.positive
            Prims.currency_row("AVAILABLE", reserves, col_res)
        else:
            imgui.text("AVAILABLE")
            imgui.same_line()
            Prims.right_align_text("Unknown", GAMETHEME.colors.text_dim)
        
        imgui.dummy((0, 8))

        # Resources Section
        Prims.header("RESOURCES")
        if imgui.button("OPEN RESOURCES DIRECTORY", (-1, 30)):
            if self.toggle_resources_cb:
                self.toggle_resources_cb()
        
        imgui.dummy((0, 15))
        
        # Footer
        if is_own:
            if imgui.button("TRADE", (-1, 35)): pass
        else:
            if imgui.button("PROPOSE TRADE", (-1, 35)): pass