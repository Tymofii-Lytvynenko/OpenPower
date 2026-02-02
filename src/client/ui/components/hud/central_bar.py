import arcade
from typing import Optional
from imgui_bundle import imgui, icons_fontawesome_6

from src.client.ui.core.theme import GAMETHEME
from src.client.renderers.flag_renderer import FlagRenderer
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused

class CentralBar:
    """
    HUD component displayed at the bottom of the screen.
    """
    def __init__(self):
        self.show_speed_controls = True 
        self.news_ticker_text = "Global News: Simulation initialized and running."
        
        self.flag_renderer = FlagRenderer()
        self.active_tag = "" 
        self.is_own = True
        self._switch_request: Optional[str] = None

        self.height = 100.0                
        self.top_section_h_pct = 0.65        
        self.content_scale_factor = 0.80    

    def render(self, state, net, target_tag: str, is_own_country: bool) -> Optional[str]:
        self.active_tag = target_tag
        self.is_own = is_own_country
        self._switch_request = None
        
        viewport = imgui.get_main_viewport()
        screen_w = viewport.size.x
        screen_h = viewport.size.y
        
        bar_width = max(700.0, min(screen_w * 0.40, 800.0))
        pos_x = (screen_w - bar_width) / 2
        pos_y = screen_h - self.height - 15 

        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((bar_width, self.height))
        imgui.push_style_var(imgui.StyleVar_.window_padding, (0, 0))

        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.no_scroll_with_mouse |
                 imgui.WindowFlags_.no_background)

        if imgui.begin("CentralBar", True, flags):
            try:
                draw_list = imgui.get_window_draw_list()
                p = imgui.get_cursor_screen_pos()
                w = imgui.get_window_width()
                h = imgui.get_window_height()
                top_h = h * self.top_section_h_pct
                ticker_h = h - top_h

                # Draw backgrounds
                draw_list.add_rect_filled(p, (p.x + w, p.y + top_h), imgui.get_color_u32(GAMETHEME.colors.bg_window), GAMETHEME.rounding, imgui.ImDrawFlags_.round_corners_top)
                draw_list.add_rect_filled((p.x, p.y + top_h), (p.x + w, p.y + h), imgui.get_color_u32(GAMETHEME.colors.bg_window), GAMETHEME.rounding, imgui.ImDrawFlags_.round_corners_bottom)
                draw_list.add_rect(p, (p.x + w, p.y + h), imgui.get_color_u32(GAMETHEME.colors.accent), GAMETHEME.rounding, 0, 1.5)

                inner_item_h = top_h * self.content_scale_factor
                content_y = (top_h - inner_item_h) / 2
                
                # 1. Left Section
                imgui.set_cursor_pos((12.0, content_y))
                self._render_country_info(inner_item_h)

                # 2. Right Section
                right_w = 250.0
                imgui.set_cursor_pos((w - right_w - 12.0, content_y))
                self._render_time_controls(state, net, right_w, inner_item_h)

                # 3. News Ticker
                imgui.set_cursor_pos((0, top_h))
                self._render_ticker(w, ticker_h)
                
                # 4. Popups
                self._render_country_selector_popup(state)

            finally:
                imgui.end()
        
        imgui.pop_style_var() 
        return self._switch_request

    def _render_time_controls(self, state, net, width, height):
        imgui.begin_group()
        if imgui.button(icons_fontawesome_6.ICON_FA_HOURGLASS_HALF, (50, height)):
            self.show_speed_controls = not self.show_speed_controls
        imgui.same_line()
        
        imgui.begin_child("TimeScreen", (width - 60, height), False, imgui.WindowFlags_.no_background)
        
        if self.show_speed_controls:
            self._draw_speed_buttons(state, net, height)
        else:
            self._draw_date_display(state, width - 60, height)
        imgui.end_child()
        imgui.end_group()

    def _draw_speed_buttons(self, state, net, height):
        current_speed = getattr(state.time, "speed", 1)
        is_paused = getattr(state.time, "paused", False)
        btn_s = (26, 26) 
        
        # Center vertically
        imgui.set_cursor_pos_y((height - 26) / 2)
        
        if is_paused: 
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.warning)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_dim)
        
        if imgui.button("||", btn_s):
            net.send_action(ActionSetPaused("local", not is_paused))
        
        if is_paused: imgui.pop_style_color(2)
        imgui.same_line()

        for i in range(1, 6):
            is_active = (current_speed == i and not is_paused)
            if is_active: 
                imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.positive)
                imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_dim)
            if imgui.button(str(i), btn_s):
                net.send_action(ActionSetPaused("local", False))
                net.send_action(ActionSetGameSpeed("local", i))
            if is_active: imgui.pop_style_color(2)
            if i < 5: imgui.same_line()

    def _draw_date_display(self, state, avail_w, avail_h):
        t = state.time
        parts = t.date_str.split(" ")
        date_part = parts[0] if len(parts) > 0 else "N/A"
        time_part = parts[1] if len(parts) > 1 else ""
        
        full_text = f"{date_part}    {time_part}"
        text_size = imgui.calc_text_size(full_text)
        
        pos_x = (avail_w - text_size.x) / 2
        pos_y = (avail_h - text_size.y) / 2
        
        imgui.set_cursor_pos((pos_x, pos_y))
        imgui.text_colored(GAMETHEME.colors.positive, date_part)
        imgui.same_line()
        imgui.text_colored(GAMETHEME.colors.text_main, time_part)

    def _render_country_info(self, height):
        imgui.begin_group()
        flag_h = height
        flag_w = flag_h * 1.5
        
        self.flag_renderer.draw_flag(self.active_tag, flag_w, flag_h)

        imgui.same_line()

        imgui.begin_group()
        gap = 2.0
        row_h = (height - gap) / 2
        
        # Tag Button
        if imgui.button(f" {self.active_tag} ", (90, row_h)):
            imgui.open_popup("CountrySelectorPopup")
        
        # Status Label
        if self.is_own:
            self._draw_status_label("COMMAND", GAMETHEME.colors.positive, row_h, 90)
        else:
            self._draw_status_label("VIEWING", GAMETHEME.colors.warning, row_h, 90)

        imgui.end_group()
        imgui.end_group()

    def _render_ticker(self, section_w, section_h):
        text_line_h = imgui.get_text_line_height()
        current_y = imgui.get_cursor_pos_y()
        text_y = (section_h - text_line_h) / 2
        
        imgui.set_cursor_pos((12.0, current_y + text_y))
        imgui.text_colored(GAMETHEME.colors.text_main, self.news_ticker_text)

    def _render_country_selector_popup(self, state):
        if imgui.begin_popup("CountrySelectorPopup"):
            imgui.text_disabled("Switch Viewpoint (Debug)")
            imgui.separator()
            
            if "countries" in state.tables:
                df = state.tables["countries"]
                try: df = df.sort("id")
                except: pass
                
                imgui.begin_child("CountryList", (250, 300), True)
                for row in df.iter_rows(named=True):
                    tag = row['id']
                    label = f"{tag} - {row.get('name', tag)}"
                    if imgui.selectable(label, tag == self.active_tag)[0]:
                        self._switch_request = tag
                        imgui.close_current_popup()
                imgui.end_child()
            imgui.end_popup()

    def _draw_status_label(self, label, color, height, width):
        imgui.push_style_color(imgui.Col_.button, color)
        imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_dim)
        imgui.button(label, (width, height))
        imgui.pop_style_color(2)