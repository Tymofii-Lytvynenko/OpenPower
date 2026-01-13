from imgui_bundle import imgui
from src.client.ui.composer import UIComposer
from src.server.state import GameState
from src.client.ui.theme import GAMETHEME

class PoliticsPanel:
    def render(self, composer: UIComposer, state: GameState):
        expanded, _ = composer.begin_panel("POLITICS", 10, 100, 240, 520)
        
        if expanded:
            # 1. Constitutional Form
            composer.draw_section_header("CONSTITUTIONAL FORM")
            imgui.text("Multi-party democracy")
            imgui.dummy((0, 5))

            # 2. Ideology
            composer.draw_section_header("IDEOLOGY", show_more_btn=False)
            
            # --- READING STATE ---
            current_ideology = 0.5 
            # Example real lookup:
            # if "politics" in state.tables:
            #     current_ideology = state.tables["politics"]["ruling_party_alignment"]

            imgui.push_style_color(imgui.Col_.slider_grab, GAMETHEME.col_active_accent)
            imgui.push_style_color(imgui.Col_.frame_bg, GAMETHEME.popup_bg)
            
            # --- RENDERING ONLY ---
            changed, new_val = imgui.slider_float("##ideology", current_ideology, 0.0, 1.0, "")
            
            if changed:
                # TODO: Dispatch ActionSetIdeology(new_val) via NetClient
                pass

            imgui.pop_style_color(2)
            
            imgui.text_disabled("Left")
            imgui.same_line()
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x - 30)
            imgui.text_disabled("Right")
            
            imgui.dummy((0, 5))
            if imgui.button("INTERNAL LAWS", (imgui.get_content_region_avail().x, 0)):
                pass 
            imgui.dummy((0, 8))

            # 3. Meters (Read Only)
            composer.draw_section_header("APPROVAL", show_more_btn=False)
            composer.draw_meter("", 51.7, GAMETHEME.col_positive) 

            composer.draw_section_header("PRESSURE", show_more_btn=False)
            composer.draw_meter("", 0.0, GAMETHEME.col_negative) 

            composer.draw_section_header("STABILITY", show_more_btn=False)
            composer.draw_meter("", 56.7, GAMETHEME.col_positive) 

            composer.draw_section_header("CORRUPTION", show_more_btn=False)
            composer.draw_meter("", 47.2, GAMETHEME.col_negative) 
            
            imgui.dummy((0, 10))
            
            if imgui.button("TREATIES", (imgui.get_content_region_avail().x, 35)):
                pass

        composer.end_panel()