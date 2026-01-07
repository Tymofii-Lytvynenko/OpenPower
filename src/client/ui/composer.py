import arcade
from imgui_bundle import imgui
from src.client.ui.theme import UITheme

class UIComposer:
    """
    A service responsible for constructing standardized UI elements.
    """
    def __init__(self, theme: UITheme):
        self.theme = theme

    def setup_frame(self):
        """Applies frame-wide styles at the start of rendering."""
        self.theme.apply_global_styles()

    def begin_centered_panel(self, name: str, screen_w: int, screen_h: int, width: int = 300, height: int = 400) -> bool:
        """
        Creates a centered, decorated window for menus.
        """
        pos_x = (screen_w - width) / 2
        pos_y = (screen_h - height) / 2
        
        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((width, height))
        
        # Flags: No Title Bar, No Resize, No Move, No Scrollbar
        flags = (imgui.WindowFlags_.no_title_bar | 
                 imgui.WindowFlags_.no_resize | 
                 imgui.WindowFlags_.no_move |
                 imgui.WindowFlags_.no_scrollbar)

        # Style Push: Add a thicker border for the main menu panel
        imgui.push_style_var(imgui.StyleVar_.window_border_size, 1.0)
        visible = imgui.begin(name, True, flags)[0]
        imgui.pop_style_var()
        
        return visible

    def end_panel(self):
        imgui.end()

    def draw_menu_button(self, label: str, width: float = -1, height: float = 40) -> bool:
        """
        Draws a large, stylized menu button.
        """
        clicked = imgui.button(label, (width, height))
        
        # --- FIX: Use Dummy instead of SetCursorPosY ---
        # This explicitly tells ImGui "I am using this 5px space", preventing the
        # "SetCursorPos extended window boundaries" assertion crash.
        imgui.dummy((0.0, 5.0))
        
        return clicked

    def draw_title(self, text: str):
        """
        Draws a large header text centered with a shadow effect.
        """
        window_width = imgui.get_window_width()
        text_width = imgui.calc_text_size(text).x
        
        # 1. Center the cursor horizontally
        center_x = (window_width - text_width) / 2
        imgui.set_cursor_pos_x(center_x)
        
        # 2. Draw Shadow using the low-level DrawList
        # This is safe because it doesn't affect the layout cursor
        p = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()
        
        # Shadow Color (Black, Fully Opaque)
        shadow_col = imgui.get_color_u32((0, 0, 0, 1))
        # Draw text at offset +2,+2
        draw_list.add_text((p.x + 2, p.y + 2), shadow_col, text)
        
        # 3. Draw Main Text (Normal Layout Item)
        imgui.text(text) 
        
        # 4. Spacing (Using Dummy for safety)
        imgui.separator()
        imgui.dummy((0.0, 10.0))
        
    def draw_progress_bar(self, fraction: float, text: str = "", width: float = -1, height: float = 20):
        """
        Draws a custom, sharp, industrial-style progress bar.
        
        Args:
            fraction: 0.0 to 1.0
            text: Text overlay (e.g. "Loading Regions...")
        """
        if width < 0:
            width = imgui.get_content_region_avail().x
            
        # Draw background (Darker slot)
        p = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()
        
        bg_col = imgui.get_color_u32((0.0, 0.1, 0.15, 1.0))
        fill_col = imgui.get_color_u32(self.theme.button_active) # Use active button cyan color
        text_col = imgui.get_color_u32((1, 1, 1, 1))
        
        # 1. Background Rect
        draw_list.add_rect_filled(p, (p.x + width, p.y + height), bg_col)
        
        # 2. Fill Rect (The actual progress)
        fill_width = max(2.0, width * fraction) # Ensure at least 2px so it's visible at start
        draw_list.add_rect_filled(p, (p.x + fill_width, p.y + height), fill_col)
        
        # 3. Border (The "SP2" thin cyan line)
        border_col = imgui.get_color_u32(self.theme.border)
        draw_list.add_rect(p, (p.x + width, p.y + height), border_col)
        
        # 4. Text Overlay (Centered)
        text_size = imgui.calc_text_size(text)
        text_x = p.x + (width - text_size.x) / 2
        text_y = p.y + (height - text_size.y) / 2
        draw_list.add_text((text_x, text_y), text_col, text)
        
        # Advance cursor so the next item doesn't overlap
        imgui.dummy((width, height))
        imgui.dummy((0.0, 5.0)) # Spacing