from imgui_bundle import imgui
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.components.hud.panel_manager import PanelManager

class ToggleBar:
    def __init__(self, panel_manager: PanelManager):
        self.manager = panel_manager

    def render(self):
        viewport = imgui.get_main_viewport()
        pad_x, pad_y = 10.0, 10.0
        
        # Anchor Bottom-Left
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
            entries = self.manager.get_entries()
            
            # Filter only those with icons
            icon_entries = [e for e in entries if e.icon]
            
            for i, entry in enumerate(icon_entries):
                if i > 0: imgui.same_line(0, 10)
                
                if self._draw_toggle(entry.icon, entry.color, entry.visible):
                    self.manager.toggle(entry.id)
            
            imgui.end()

    def _draw_toggle(self, icon: str, color: tuple, is_active: bool) -> bool:
        bg = GAMETHEME.colors.interaction_active if is_active else GAMETHEME.colors.bg_input
        imgui.push_style_color(imgui.Col_.button, bg)
        imgui.push_style_var(imgui.StyleVar_.frame_rounding, 8.0)
        
        clicked = imgui.button(icon, (50, 50))
        
        imgui.pop_style_var()
        imgui.pop_style_color()

        # Draw Indicator Line if active
        if is_active:
            p_min = imgui.get_item_rect_min()
            p_max = imgui.get_item_rect_max()
            draw_list = imgui.get_window_draw_list()
            
            # Indicator color uses the panel's specific color
            ind_col = imgui.get_color_u32((color[0], color[1], color[2], 1.0))
            
            draw_list.add_rect_filled(
                (p_min.x + 5, p_max.y - 6), 
                (p_max.x - 5, p_max.y - 2), 
                ind_col, 2.0
            )
            
        return clicked