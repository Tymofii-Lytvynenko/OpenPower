import polars as pl
from imgui_bundle import imgui
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME

class EconomyPanel:
    def render(self, composer: UIComposer, state, player_tag: str):
        # Position: Right Side
        vp_w = imgui.get_main_viewport().size.x
        expanded, _ = composer.begin_panel("ECONOMY", vp_w - 280, 100, 260, 450)
        
        if expanded:
            # 1. Economic Model
            composer.draw_section_header("ECONOMIC MODEL", show_more_btn=False)
            
            # Styled Slider
            imgui.push_style_color(imgui.Col_.frame_bg, GAMETHEME.col_frame_bg)
            imgui.push_style_color(imgui.Col_.slider_grab, GAMETHEME.col_slider_accent)
            
            # Mock value: 0.2 (Mostly State Controlled)
            imgui.slider_float("##eco_model", 0.2, 0.0, 1.0, "")
            imgui.pop_style_color(2)
            
            # Labels
            imgui.text_disabled("State-Controlled")
            imgui.same_line()
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x - 70)
            imgui.text_disabled("Free Market")
            imgui.dummy((0, 5))

            # 2. Economic Health
            composer.draw_section_header("ECONOMIC HEALTH")
            # Mock value 22.1%
            composer.draw_meter("", 22.1, GAMETHEME.col_meter_positive) 

            # 3. Budget Section
            composer.draw_section_header("BUDGET")
            
            # Default Placeholders
            income = 14213346067
            expenses = 21697009754
            
            # Real Data Injection
            if "countries" in state.tables:
                try:
                    df = state.tables["countries"]
                    res = df.filter(pl.col("id") == player_tag).select("money_balance")
                    if not res.is_empty():
                        pass 
                except Exception:
                    pass

            composer.draw_currency_row("INCOME", income)
            composer.draw_currency_row("EXPENSES", expenses)
            
            # Calculated Balance
            balance = income - expenses
            col_bal = GAMETHEME.col_negative if balance < 0 else GAMETHEME.col_positive
            composer.draw_currency_row("BALANCE", balance, col_bal)
            
            # Available (Treasury) - Mock Debt
            composer.draw_currency_row("AVAILABLE", -25000193956, GAMETHEME.col_negative)
            
            imgui.dummy((0, 8))

            # 4. Resources
            composer.draw_section_header("RESOURCES")
            composer.draw_meter("", 66.0, GAMETHEME.col_meter_positive)
            
            imgui.dummy((0, 15))
            
            # Footer
            imgui.button("TRADE", (-1, 35))

        composer.end_panel()