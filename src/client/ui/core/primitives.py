from imgui_bundle import imgui
from src.client.ui.core.theme import GAMETHEME

class UIPrimitives:
    """
    Stateless functional UI elements (Widgets).
    """

    @staticmethod
    def header(label: str, show_bg: bool = True):
        """Draws a styled section header."""
        if show_bg:
            p = imgui.get_cursor_screen_pos()
            w = imgui.get_content_region_avail().x
            h = 24.0
            draw_list = imgui.get_window_draw_list()
            
            draw_list.add_rect_filled(
                p, (p.x + w, p.y + h),
                imgui.get_color_u32(GAMETHEME.colors.bg_input), 4.0
            )
            
            # Center text vertically
            text_size = imgui.calc_text_size(label)
            text_y = p.y + (h - text_size.y) / 2
            
            imgui.set_cursor_screen_pos((p.x + 8, text_y))
            imgui.text_colored(GAMETHEME.colors.text_main, label)
            
            # Reset cursor for next item
            imgui.set_cursor_screen_pos((p.x, p.y + h + 5))
        else:
            imgui.text_colored(GAMETHEME.colors.text_main, label)
            imgui.separator()

    @staticmethod
    def meter(label: str, value_pct: float, color: tuple, height: float = 12.0):
        """Draws a custom progress bar/meter."""
        if label:
            imgui.text(label)
        
        w = imgui.get_content_region_avail().x
        p = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()

        # Background Track
        draw_list.add_rect_filled(
            p, (p.x + w, p.y + height),
            imgui.get_color_u32(GAMETHEME.colors.bg_input), height / 2
        )

        # Foreground Fill
        fraction = max(0.0, min(value_pct, 100.0)) / 100.0
        if fraction > 0.01:
            draw_list.add_rect_filled(
                p, (p.x + w * fraction, p.y + height),
                imgui.get_color_u32(color), height / 2
            )
        
        imgui.dummy((0, height + 5))

    @staticmethod
    def currency_row(label: str, value: float, color: tuple = None):
        """Aligned row: Label ...... $Value."""
        imgui.text(label)
        imgui.same_line()
        
        val_str = f"$ {value:,.0f}".replace(",", " ")
        width = imgui.calc_text_size(val_str).x
        
        # Right align
        avail_w = imgui.get_content_region_avail().x
        if avail_w > width:
            imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail_w - width)
        
        col = color if color else GAMETHEME.colors.text_main
        imgui.text_colored(col, val_str)

    @staticmethod
    def right_align_text(text: str, color: tuple = None):
        width = imgui.calc_text_size(text).x
        avail_w = imgui.get_content_region_avail().x
        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail_w - width)
        if color:
            imgui.text_colored(color, text)
        else:
            imgui.text(text)