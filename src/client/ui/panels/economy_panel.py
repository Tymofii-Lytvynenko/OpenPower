import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class EconomyPanel:
    def render(self, state, **kwargs) -> bool:
        target_tag = kwargs.get("target_tag", "")
        is_own = kwargs.get("is_own_country", False)

        with WindowManager.window("ECONOMY", x=1600, y=100, w=260, h=450) as is_open:
            if not is_open: return False

            self._render_content(state, target_tag, is_own)
            return True

    def _render_content(self, state, target_tag, is_own):
        # 1. Fetch Data
        reserves = 0
        gdp_per_capita = 0
        tax_rate = 0.2
        
        if "countries" in state.tables:
            try:
                row = state.tables["countries"].filter(pl.col("id") == target_tag)
                if not row.is_empty():
                    reserves = int(row["money_reserves"][0])
                    gdp_per_capita = int(row["gdp_per_capita"][0])
                    tax_rate = float(row["global_tax_rate"][0])
            except: pass

        # Approx Total GDP calculation
        total_pop = 1_000_000 # Fallback
        if "regions" in state.tables:
            try:
                target_regions = state.tables["regions"].filter(pl.col("owner") == target_tag)
                if not target_regions.is_empty():
                     total_pop = target_regions.select(pl.col("pop_14") + pl.col("pop_15_64") + pl.col("pop_65")).sum().item()
            except: pass

        total_gdp = total_pop * gdp_per_capita
        income = total_gdp * tax_rate
        expenses = 0 
        
        # 2. Render UI
        Prims.header("ECONOMIC MODEL", show_bg=False)
        if not is_own: imgui.begin_disabled()
        imgui.slider_float("##tax", tax_rate, 0.0, 1.0, "Tax: %.2f")
        if not is_own: imgui.end_disabled()
        
        imgui.dummy((0, 10))

        Prims.header(f"GDP: ${total_gdp:,.0f}")
        gdp_health = min((total_gdp / 1e12) * 100, 100.0)
        Prims.meter("GDP Health", gdp_health, GAMETHEME.colors.positive)
        Prims.currency_row("Per Capita", gdp_per_capita)

        imgui.dummy((0, 10))

        Prims.header("BUDGET")
        Prims.currency_row("INCOME", income)
        Prims.currency_row("EXPENSES", expenses)
        
        balance = income - expenses
        col_bal = GAMETHEME.colors.positive if balance >= 0 else GAMETHEME.colors.negative
        Prims.currency_row("BALANCE", balance, col_bal)

        if is_own:
            col_res = GAMETHEME.colors.positive if reserves >= 0 else GAMETHEME.colors.negative
            Prims.currency_row("RESERVES", reserves, col_res)
        
        imgui.dummy((0, 20))
        if is_own:
            imgui.button("TRADE AGREEMENTS", (-1, 35))