import polars as pl
from imgui_bundle import imgui
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME

class DemographicsPanel:
    def __init__(self):
        # Cache for sparkline or historical data if needed in the future
        self.age_groups = ["Youth (0-14)", "Working (15-64)", "Elderly (65+)"]

    def render(self, composer: UIComposer, state, player_tag: str):
        # Position: Left Side, offset below Politics
        expanded, _ = composer.begin_panel("DEMOGRAPHY", 10, 350, 240, 480)
        
        if expanded:
            # 1. TOTAL POPULATION SUMMARY
            composer.draw_section_header("POPULATION SUMMARY")
            
            total_pop = 0
            growth_rate = 1.2  # Mock value
            urbanization = 72.5 # Mock value
            
            # Data aggregation from regions belonging to the player
            if "regions" in state.tables:
                try:
                    df = state.tables["regions"]
                    # Sum populations for all regions owned by player_tag
                    player_regions = df.filter(pl.col("owner") == player_tag)
                    if not player_regions.is_empty():
                        total_pop = player_regions.select(
                            pl.col("pop_14") + pl.col("pop_15_64") + pl.col("pop_65")
                        ).sum().item()
                except Exception:
                    pass

            imgui.text("Total:")
            imgui.same_line()
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x + 20 - imgui.calc_text_size(f"{total_pop:,}").x)
            imgui.text_colored(GAMETHEME.col_active_accent, f"{total_pop:,}")
            
            imgui.text_disabled("Annual Growth:")
            imgui.same_line()
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x + 20 - imgui.calc_text_size(f"+{growth_rate}%").x)
            imgui.text_colored(GAMETHEME.col_positive, f"+{growth_rate}%")
            
            imgui.dummy((0, 5))

            # 2. AGE DISTRIBUTION (Using your draw_meter for a "pyramid" feel)
            composer.draw_section_header("AGE STRUCTURE", show_more_btn=False)
            
            # Mock distribution based on your Region schema
            # In a real scenario, you'd calculate these % from the dataframe
            composer.draw_meter("Youth (0-14)", 22.0, (0.4, 0.7, 1.0, 1.0))
            composer.draw_meter("Working (15-64)", 65.0, (0.3, 0.8, 0.4, 1.0))
            composer.draw_meter("Elderly (65+)", 13.0, (0.8, 0.4, 0.4, 1.0))

            # 3. SOCIAL METRICS
            composer.draw_section_header("SOCIAL INDICATORS")
            
            # Using draw_currency_row for aligned key-value pairs
            # (Adapted labels since it handles spacing well)
            composer.draw_currency_row("Literacy", 98, GAMETHEME.text_main)
            imgui.same_line() # Overwrite the $ sign logic if necessary, or just use text:
            imgui.text("%")
            
            composer.draw_currency_row("Life Expectancy", 78, GAMETHEME.text_main)
            
            imgui.dummy((0, 10))
            
            # 4. URBAN vs RURAL
            imgui.text_disabled("URBANIZATION")
            composer.draw_meter("", urbanization, GAMETHEME.col_info)
            imgui.text_disabled(f"{urbanization}% Urban")
            imgui.same_line()
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x - 60)
            imgui.text_disabled(f"{100-urbanization:.1f}% Rural")

            imgui.dummy((0, 15))
            
            # 5. ACTION BUTTONS
            if imgui.button("MIGRATION POLICY", (-1, 30)):
                pass
            if imgui.button("SOCIAL PROGRAMS", (-1, 30)):
                pass

        composer.end_panel()