import arcade
from imgui_bundle import imgui
from src.client.ui.theme import UITheme

class UIComposer:
    def __init__(self, theme: UITheme):
        self.theme = theme

    def setup_frame(self):
        self.theme.apply_global_styles()

    # =========================================================================
    # CONTAINER HELPERS
    # =========================================================================

    def begin_panel(self, name: str, x: float, y: float, width: float, height: float, closable: bool = False) -> tuple[bool, bool]:
        """
        Starts a floating panel. 
        Returns: (is_visible, is_open_state)
        """
        imgui.set_next_window_pos((x, y), imgui.Cond_.first_use_ever)
        imgui.set_next_window_size((width, height), imgui.Cond_.first_use_ever)
        
        flags = imgui.WindowFlags_.no_collapse
        expanded, open_state = imgui.begin(name, True if closable else None, flags)
        return expanded, open_state

    def end_panel(self):
        imgui.end()
        
    def begin_centered_panel(self, name: str, screen_w: int, screen_h: int, width: int = 300, height: int = 400) -> bool:
        """Old helper for Main Menu/Static screens."""
        pos_x = (screen_w - width) / 2
        pos_y = (screen_h - height) / 2
        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((width, height))
        
        flags = (imgui.WindowFlags_.no_title_bar | imgui.WindowFlags_.no_resize | 
                 imgui.WindowFlags_.no_move | imgui.WindowFlags_.no_scrollbar)
        
        imgui.push_style_var(imgui.StyleVar_.window_border_size, 1.0)
        visible = imgui.begin(name, True, flags)[0]
        imgui.pop_style_var()
        return visible

    # =========================================================================
    # WIDGET HELPERS
    # =========================================================================

    def draw_menu_button(self, label: str, width: float = -1, height: float = 40) -> bool:
        """Standard large menu button."""
        clicked = imgui.button(label, (width, height))
        imgui.dummy((0.0, 5.0))
        return clicked

    def draw_title(self, text: str):
        """Standard centered header."""
        window_width = imgui.get_window_width()
        text_width = imgui.calc_text_size(text).x
        imgui.set_cursor_pos_x((window_width - text_width) / 2)
        imgui.text(text)
        imgui.separator()
        imgui.dummy((0.0, 10.0))

    def draw_progress_bar(self, fraction: float, text: str = "", width: float = -1, height: float = 20):
        """
        Draws a custom, sharp, industrial-style progress bar.
        Required by LoadingView.
        """
        if width < 0:
            width = imgui.get_content_region_avail().x
            
        # Draw background (Darker slot)
        p = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()
        
        # Use theme colors
        bg_col = imgui.get_color_u32((0.0, 0.0, 0.0, 1.0))
        fill_col = imgui.get_color_u32(self.theme.button_active) # Cyan/Blue from theme
        text_col = imgui.get_color_u32(self.theme.text_main)
        
        # 1. Background Rect
        draw_list.add_rect_filled(p, (p.x + width, p.y + height), bg_col)
        
        # 2. Fill Rect
        fill_width = max(2.0, width * fraction)
        draw_list.add_rect_filled(p, (p.x + fill_width, p.y + height), fill_col)
        
        # 3. Border
        border_col = imgui.get_color_u32(self.theme.border)
        draw_list.add_rect(p, (p.x + width, p.y + height), border_col)
        
        # 4. Text Overlay
        if text:
            text_size = imgui.calc_text_size(text)
            text_x = p.x + (width - text_size.x) / 2
            text_y = p.y + (height - text_size.y) / 2
            draw_list.add_text((text_x, text_y), text_col, text)
        
        # Advance layout cursor
        imgui.dummy((width, height))
        imgui.dummy((0.0, 5.0))

    def draw_section_header(self, label: str, show_more_btn: bool = True):
        """
        Draws the dark bar with title.
        """
        draw_list = imgui.get_window_draw_list()
        p = imgui.get_cursor_screen_pos()
        width = imgui.get_content_region_avail().x
        height = 18.0

        # Background bar (Darker Olive)
        col_bg = imgui.get_color_u32(self.theme.header_bg)
        draw_list.add_rect_filled(p, (p.x + width, p.y + height), col_bg)

        # Text
        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + 5) # Padding
        imgui.text_colored(self.theme.text_main, label)

        # Optional "more" button aligned right
        if show_more_btn:
            imgui.same_line()
            # Align right
            imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + width - 45) 
            
            # Use small, transparent button
            imgui.push_style_color(imgui.Col_.button, (0,0,0,0))
            if imgui.small_button("more"):
                pass 
            imgui.pop_style_color()

        # Advance cursor past the custom header
        imgui.dummy((0.0, 3.0))

    def draw_meter(self, label: str, value: float, color: tuple, show_percentage: bool = True):
        """
        Draws style colored stat bars.
        """
        if label:
            imgui.text(label)
        
        w = imgui.get_content_region_avail().x
        h = 10.0
        
        p = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()
        
        # 1. Background (Black)
        draw_list.add_rect_filled(p, (p.x + w, p.y + h), imgui.get_color_u32((0,0,0,1)))
        
        # 2. Fill
        fill_w = (max(0.0, min(100.0, value)) / 100.0) * w
        fill_col = imgui.get_color_u32((color[0], color[1], color[2], 1.0))
        draw_list.add_rect_filled(p, (p.x + fill_w, p.y + h), fill_col)
        
        # 3. Border (Theme Border Color)
        border_col = imgui.get_color_u32(self.theme.border)
        draw_list.add_rect(p, (p.x + w, p.y + h), border_col)

        # 4. Overlay Text
        if show_percentage:
            txt = f"{value:.1f} %"
            # Position inside bar, left aligned with slight padding
            draw_list.add_text((p.x + 5, p.y - 1), imgui.get_color_u32((1,1,1,1)), txt)

        imgui.dummy((0, h + 5))

    def draw_currency_row(self, label: str, value: int, color_val=None):
        """Row with Label on left, Money on right."""
        imgui.text(label)
        imgui.same_line()
        
        val_str = f"$ {value:,.0f}".replace(",", " ") 
        w = imgui.calc_text_size(val_str).x
        avail = imgui.get_content_region_avail().x
        
        # Right align
        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail - w)
        c = color_val if color_val else self.theme.text_main
        imgui.text_colored(c, val_str)

    def draw_icon_toggle(self, icon: str, color: tuple, is_active: bool, width: float = 50, height: float = 50) -> bool:
        """
        Draws a big square toggle button with a status light bar at the bottom.
        """
        # Push colors based on active state
        if is_active:
             imgui.push_style_color(imgui.Col_.button, self.theme.button_active)
        else:
             imgui.push_style_color(imgui.Col_.button, self.theme.button_normal)

        clicked = imgui.button(icon, (width, height))
        imgui.pop_style_color()
        
        # Draw status bar below button (Visual indicator)
        p = imgui.get_item_rect_min()
        p_max = imgui.get_item_rect_max()
        draw_list = imgui.get_window_draw_list()
        
        bar_height = 4
        # If active, use the specific category color. If inactive, gray.
        bar_col = imgui.get_color_u32(color if is_active else (0.3, 0.3, 0.3, 1.0))
        
        draw_list.add_rect_filled(
            (p.x, p_max.y - bar_height), 
            (p_max.x, p_max.y), 
            bar_col
        )
        
        return clicked