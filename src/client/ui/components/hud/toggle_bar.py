from typing import Dict, Any
from imgui_bundle import imgui
from src.client.ui.composer import UIComposer

class ToggleBar:
    def render(self, composer: UIComposer, panels: Dict[str, Dict[str, Any]]):
        """
        Renders the icon toggles for the panels.
        Anchored Bottom-Left using pivots for perfect screen independence.
        """
        viewport = imgui.get_main_viewport()
        
        # Padding
        pad_x, pad_y = 10.0, 10.0
        
        # Anchor: BOTTOM-LEFT
        # Pivot (0, 1) -> (Left, Bottom)
        # Pos (Pad, ScreenH - Pad)
        imgui.set_next_window_pos(
            imgui.ImVec2(pad_x, viewport.size.y - pad_y),
            imgui.Cond_.always,
            imgui.ImVec2(0.0, 1.0)
        )
        
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.always_auto_resize | 
                 imgui.WindowFlags_.no_background)

        if imgui.begin("ToggleBar", True, flags):
            try:
                # Filter for panels that have an icon
                icon_panels = [(pid, d) for pid, d in panels.items() if "icon" in d]
                
                # Dynamic Icon Size
                size = 50.0 
                
                for i, (panel_id, data) in enumerate(icon_panels):
                    if i > 0:
                        imgui.same_line(0, 10) # 10px spacing
                    
                    if composer.draw_icon_toggle(data["icon"], data["color"], data["visible"], width=size, height=size): # type: ignore
                        data["visible"] = not data["visible"]
                        
            except Exception as e:
                print(f"[ToggleBar] Error: {e}")
            finally:
                imgui.end()
        else:
            imgui.end()