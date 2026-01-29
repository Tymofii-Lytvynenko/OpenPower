from typing import Dict, Any
from imgui_bundle import imgui
from src.client.ui.composer import UIComposer

class ToggleBar:
    def render(self, composer: UIComposer, panels: Dict[str, Dict[str, Any]]):
        """
        Renders the icon toggles for the panels.
        Directly modifies the 'visible' state in the panels dict.
        """
        screen_h = imgui.get_main_viewport().size.y
        
        # Position: Bottom-Left
        imgui.set_next_window_pos((10, screen_h - 70))
        
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.always_auto_resize | 
                 imgui.WindowFlags_.no_background)

        # START CRITICAL SECTION
        # We must ensure imgui.end() is called even if drawing fails
        if imgui.begin("ToggleBar", True, flags):
            try:
                # Filter for panels that have an icon
                icon_panels = [(pid, d) for pid, d in panels.items() if "icon" in d]
                
                for i, (panel_id, data) in enumerate(icon_panels):
                    if i > 0:
                        imgui.same_line(0, 10) # 10px spacing
                    
                    # Draw Toggle Button
                    # If this crashes (e.g. icon missing), 'finally' block handles cleanup
                    if composer.draw_icon_toggle(data["icon"], data["color"], data["visible"]):
                        data["visible"] = not data["visible"]
            except Exception as e:
                print(f"[ToggleBar] Error: {e}")
            finally:
                imgui.end()
        else:
            imgui.end()