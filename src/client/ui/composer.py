import arcade
from imgui_bundle import imgui
from src.client.ui.theme import UITheme

class UIComposer:
    def __init__(self, theme: UITheme):
        self.theme = theme

    def setup_frame(self):
        self.theme.apply_global_styles()

    def begin_panel(self, name, x, y, w, h, closable=False):
        imgui.set_next_window_pos((x, y), imgui.Cond_.first_use_ever)
        imgui.set_next_window_size((w, h), imgui.Cond_.first_use_ever)
        return imgui.begin(name, closable, imgui.WindowFlags_.no_collapse)

    def end_panel(self): imgui.end()

    def begin_centered_panel(self, name, sw, sh, w=300, h=400):
        imgui.set_next_window_pos(((sw - w)/2, (sh - h)/2))
        imgui.set_next_window_size((w, h))
        imgui.push_style_var(imgui.StyleVar_.window_border_size, 1.0)
        v, _ = imgui.begin(name, None, imgui.WindowFlags_.no_title_bar | imgui.WindowFlags_.no_resize)
        imgui.pop_style_var()
        return v

    def draw_menu_button(self, label, w=-1, h=40):
        c = imgui.button(label, (w, h))
        imgui.dummy((0, 5))
        return c

    def draw_title(self, text):
        imgui.set_cursor_pos_x((imgui.get_window_width() - imgui.calc_text_size(text).x)/2)
        imgui.text(text)
        imgui.separator()
        imgui.dummy((0, 10))

    def draw_progress_bar(self, fraction, text="", width=-1, height=20):
        p = imgui.get_cursor_screen_pos()
        w = width if width > 0 else imgui.get_content_region_avail().x
        draw = imgui.get_window_draw_list()
        draw.add_rect_filled(p, (p.x + w, p.y + height), imgui.get_color_u32(self.theme.window_bg))
        draw.add_rect_filled(p, (p.x + w * fraction, p.y + height), imgui.get_color_u32(self.theme.button_active))
        draw.add_rect(p, (p.x + w, p.y + height), imgui.get_color_u32(self.theme.border))
        if text:
            ts = imgui.calc_text_size(text)
            draw.add_text((p.x + (w-ts.x)/2, p.y + (height-ts.y)/2), imgui.get_color_u32(self.theme.text_main), text)
        imgui.dummy((w, height + 5))

    def draw_section_header(self, label, show_more_btn=True):
        dl, p, w, h = imgui.get_window_draw_list(), imgui.get_cursor_screen_pos(), imgui.get_content_region_avail().x, 22.0
        dl.add_rect_filled(p, (p.x + w, p.y + h), imgui.get_color_u32(self.theme.header_bg))
        imgui.set_cursor_pos((imgui.get_cursor_pos_x()+5, imgui.get_cursor_pos_y()+(h-imgui.calc_text_size(label).y)/2))
        imgui.text_colored(self.theme.text_main, label)
        imgui.set_cursor_screen_pos((p.x, p.y + h + 5))

    def draw_meter(self, label, value, color, show_percentage=True):
        if label: imgui.text(label)
        w, h, p, dl = imgui.get_content_region_avail().x, 12.0, imgui.get_cursor_screen_pos(), imgui.get_window_draw_list()
        dl.add_rect_filled(p, (p.x + w, p.y + h), imgui.get_color_u32(self.theme.window_bg))
        dl.add_rect_filled(p, (p.x + (value/100.0)*w, p.y + h), imgui.get_color_u32((*color[:3], 1.0)))
        dl.add_rect(p, (p.x + w, p.y + h), imgui.get_color_u32(self.theme.border))
        imgui.dummy((0, h + 5))

    def draw_currency_row(self, label, value, color_val=None):
        imgui.text(label)
        imgui.same_line()
        val_str = f"$ {value:,.0f}".replace(",", " ")
        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + imgui.get_content_region_avail().x - imgui.calc_text_size(val_str).x)
        imgui.text_colored(color_val or self.theme.text_main, val_str)

    def draw_icon_toggle(self, icon, color, is_active, width=50, height=50):
        imgui.push_style_color(imgui.Col_.button, self.theme.button_active if is_active else self.theme.button_normal)
        clicked = imgui.button(icon, (width, height))
        imgui.pop_style_color()
        p, pm = imgui.get_item_rect_min(), imgui.get_item_rect_max()
        col = imgui.get_color_u32((*color[:3], 1.0) if is_active else self.theme.text_dim)
        imgui.get_window_draw_list().add_rect_filled((p.x, pm.y - 4), (pm.x, pm.y), col)
        return clicked