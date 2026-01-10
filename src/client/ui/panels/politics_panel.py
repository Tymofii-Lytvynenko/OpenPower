from imgui_bundle import imgui
from src.client.ui.composer import UIComposer

class PoliticsPanel:
    def render(self, composer: UIComposer, state):
        # Position: Left side (approx 10px from left)
        # Use begin_panel to allow floating/dragging
        expanded, _ = composer.begin_panel("POLITICS", 10, 100, 240, 520)
        
        if expanded:
            # 1. Constitutional Form
            composer.draw_section_header("CONSTITUTIONAL FORM")
            imgui.text("Multi-party democracy")
            imgui.dummy((0, 5))

            # 2. Ideology
            composer.draw_section_header("IDEOLOGY", show_more_btn=False)
            
            # Visual Slider (Read-only representation)
            # Custom styling to make the grabber green or theme color
            imgui.push_style_color(imgui.Col_.slider_grab, (0.4, 0.6, 0.4, 1.0))
            imgui.push_style_color(imgui.Col_.frame_bg, (0.1, 0.1, 0.1, 1.0))
            
            # Mock value 0.3 (slightly left)
            imgui.slider_float("##ideology", 0.3, 0.0, 1.0, "")
            imgui.pop_style_color(2)
            
            # Labels below slider
            imgui.text_disabled("Left")
            imgui.same_line()
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x - 30)
            imgui.text_disabled("Right")
            
            imgui.dummy((0, 5))
            if imgui.button("INTERNAL LAWS", (imgui.get_content_region_avail().x, 0)):
                pass # TODO: Open laws modal
            imgui.dummy((0, 8))

            # 3. Meters Section
            # Green = Good, Red = Bad (usually)
            
            composer.draw_section_header("APPROVAL", show_more_btn=False)
            composer.draw_meter("", 51.7, (0.0, 0.6, 0.0)) # Green

            composer.draw_section_header("PRESSURE", show_more_btn=False)
            composer.draw_meter("", 0.0, (0.7, 0.1, 0.1)) # Red

            composer.draw_section_header("STABILITY", show_more_btn=False)
            composer.draw_meter("", 56.7, (0.0, 0.6, 0.0)) # Green

            composer.draw_section_header("CORRUPTION", show_more_btn=False)
            composer.draw_meter("", 47.2, (0.7, 0.1, 0.1)) # Red
            
            imgui.dummy((0, 10))
            
            # Footer Button
            if imgui.button("TREATIES", (imgui.get_content_region_avail().x, 35)):
                pass

        composer.end_panel()