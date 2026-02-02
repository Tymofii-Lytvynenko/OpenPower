import arcade
from typing import Optional
from imgui_bundle import imgui, icons_fontawesome_6

from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.client.services.network_client_service import NetworkClient
from src.client.renderers.flag_renderer import FlagRenderer
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused

class CentralBar:
    """
    HUD component displayed at the bottom of the screen.
    Handles country info, time controls, and quick actions.
    """
    def __init__(self):
        self.show_speed_controls = True 
        self.news_ticker_text = "Global News: Simulation initialized and running."
        
        self.flag_renderer = FlagRenderer()
        self.active_tag = "" 
        self.is_own = True
        
        # Used to pass the popup selection back to the layout
        self._switch_request: Optional[str] = None

        # Layout configuration
        self.height = 100.0                
        self.top_section_h_pct = 0.65       
        self.content_scale_factor = 0.80    

    def render(self, composer: UIComposer, state, net: NetworkClient, target_tag: str, is_own_country: bool) -> Optional[str]:
        """
        Renders the bar.
        Returns: A string (Country Tag) if the user selected a new country from the popup, else None.
        """
        self.active_tag = target_tag
        self.is_own = is_own_country
        self._switch_request = None # Reset request
        
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

                padding_x = 12.0
                inner_item_h = top_h * self.content_scale_factor
                content_y = (top_h - inner_item_h) / 2
                left_section_w = 200.0  
                right_section_w = 250.0 

                # 1. Left Section: Country Flag & Info
                imgui.set_cursor_pos((padding_x, content_y))
                self._render_country_info(composer, inner_item_h)

                # 2. Right Section: Time Controls
                right_start_x = w - right_section_w - padding_x
                imgui.set_cursor_pos((right_start_x, content_y))
                self._render_time_controls(state, net, right_section_w, inner_item_h)

                # 3. Center Section: Quick Actions
                btn_count = 3
                btn_spacing = 10.0
                center_grp_w = (inner_item_h * btn_count) + (btn_spacing * (btn_count - 1))
                available_space_start = left_section_w + padding_x
                available_space_end = right_start_x
                center_x = available_space_start + ((available_space_end - available_space_start) - center_grp_w) / 2
                
                imgui.set_cursor_pos((center_x, content_y))
                self._render_quick_actions(inner_item_h, btn_spacing)

                # 4. Bottom Section: News Ticker
                # Set cursor to start of bottom section
                imgui.set_cursor_pos((0, top_h))
                self._render_ticker(w, ticker_h)

                # 5. Popups
                self._render_country_selector_popup(state)

            except Exception as e:
                print(f"[CentralBar] Render Error: {e}")
            finally:
                imgui.end()
        else:
            imgui.end()
            
        imgui.pop_style_var() 
        return self._switch_request

    def _render_time_controls(self, state, net, width, height):
        imgui.begin_group()
        try:
            if imgui.button(icons_fontawesome_6.ICON_FA_HOURGLASS_HALF, (50, height)):
                self.show_speed_controls = not self.show_speed_controls
            imgui.same_line()
            
            screen_w = width - 50 - imgui.get_style().item_spacing.x
            p = imgui.get_cursor_screen_pos()
            draw_list = imgui.get_window_draw_list()
            draw_list.add_rect_filled(p, (p.x + screen_w, p.y + height), imgui.get_color_u32(0xFF222222))
            draw_list.add_rect(p, (p.x + screen_w, p.y + height), imgui.get_color_u32(GAMETHEME.colors.accent))
            
            imgui.begin_child("TimeScreen", (screen_w, height), False, imgui.WindowFlags_.no_background)
            
            if self.show_speed_controls:
                # Center the buttons vertically within the child
                btn_h = 26
                imgui.set_cursor_pos((10, (height - btn_h) / 2))
                self._draw_speed_buttons(state, net)
            else:
                self._draw_date_display(state, screen_w, height)
            imgui.end_child()
        finally:
            imgui.end_group()

    def _draw_speed_buttons(self, state, net):
        current_speed = getattr(state.time, "speed", 1)
        is_paused = getattr(state.time, "paused", False)
        btn_s = (26, 26) 
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (2, 0))
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (0, 0))
        
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
        imgui.pop_style_var(2)

    def _draw_date_display(self, state, avail_w, avail_h):
        t = state.time
        parts = t.date_str.split(" ")
        date_part = parts[0] if len(parts) > 0 else "N/A"
        time_part = parts[1] if len(parts) > 1 else ""
        
        full_text = f"{date_part}   {time_part}"
        
        # Calculate size to center perfectly
        text_size = imgui.calc_text_size(full_text)
        text_w = text_size.x
        text_h = text_size.y
        
        pos_x = (avail_w - text_w) / 2
        pos_y = (avail_h - text_h) / 2
        
        imgui.set_cursor_pos((pos_x, pos_y))
        
        # Draw with color logic
        imgui.text_colored(GAMETHEME.colors.positive, date_part)
        imgui.same_line()
        imgui.text_colored(GAMETHEME.colors.text_main, time_part)

    def _render_country_info(self, composer: UIComposer, height):
        imgui.begin_group()
        try:
            flag_h = height
            flag_w = flag_h * 1.5
            
            self.flag_renderer.draw_flag(self.active_tag, flag_w, flag_h)

            imgui.same_line()

            imgui.begin_group()
            try:
                gap = 2.0
                row_h = (height - gap) / 2
                
                # Top Row: Country Tag (Click to open switcher)
                if imgui.button(f" {self.active_tag} ", (90, row_h)):
                    imgui.open_popup("CountrySelectorPopup")
                
                # Bottom Row: Status Indicator
                imgui.push_style_var(imgui.StyleVar_.item_spacing, (4, 0))
                
                if self.is_own:
                    self._draw_status_label("COMMAND", GAMETHEME.colors.positive, row_h, width=70)
                else:
                    self._draw_status_label("VIEWING", GAMETHEME.colors.warning, row_h, width=70)

                imgui.same_line()
                self._draw_status_label("INFO", GAMETHEME.colors.info, row_h, width=16)
                imgui.pop_style_var()
            finally:
                imgui.end_group()
        finally:
            imgui.end_group()

    def _render_quick_actions(self, height, spacing):
        # We disable quick actions if looking at another country
        if not self.is_own:
            imgui.begin_disabled()

        btn_sz = (height, height)
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (spacing, 0))
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_BRAIN}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("AI")
        imgui.same_line()
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_CHART_LINE}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Statistics")
        imgui.same_line()
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_ENVELOPE}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Messages")
        imgui.pop_style_var()

        if not self.is_own:
            imgui.end_disabled()

    def _render_ticker(self, section_w, section_h):
        """
        Renders the news ticker text centered vertically and adds a news history button on the right.
        """
        padding_x = 12.0
        
        # 1. Calculate Vertical Center for Text
        text_line_h = imgui.get_text_line_height()
        text_y = (section_h - text_line_h) / 2
        
        # We need to offset from the current cursor position (which is at the top of the section)
        current_y = imgui.get_cursor_pos_y()
        
        # Draw Text
        imgui.set_cursor_pos((padding_x, current_y + text_y))
        imgui.text_colored(GAMETHEME.colors.text_main, self.news_ticker_text)
        
        # 2. Draw "News Button" on the far right
        btn_h = section_h - 6.0 # Small padding top/bottom
        btn_w = btn_h
        
        btn_x = section_w - btn_w - 6.0 # 6px padding from right edge
        btn_y = current_y + (section_h - btn_h) / 2
        
        imgui.set_cursor_pos((btn_x, btn_y))
        
        # Use transparent background for a cleaner look, or standard button
        if imgui.button(icons_fontawesome_6.ICON_FA_NEWSPAPER, (btn_w, btn_h)):
            # Placeholder for opening news history panel
            pass
        if imgui.is_item_hovered():
            imgui.set_tooltip("News History")

    def _render_country_selector_popup(self, state):
        """Restored Popup: Lists all countries in the game state."""
        if imgui.begin_popup("CountrySelectorPopup"):
            imgui.text_disabled("Switch Viewpoint (Debug)")
            imgui.separator()
            
            if "countries" in state.tables:
                df = state.tables["countries"]
                # Sort alphabetically for better UX
                try:
                    df = df.sort("id")
                except: pass
                
                # Use a child window to make it scrollable
                imgui.begin_child("CountryList", (250, 300), True)
                
                for row in df.iter_rows(named=True):
                    tag = row['id']
                    name = row.get('name', tag)
                    label = f"{tag} - {name}"
                    
                    # Highlight current tag
                    is_selected = (tag == self.active_tag)
                    
                    if imgui.selectable(label, is_selected)[0]:
                        self._switch_request = tag
                        imgui.close_current_popup()
                        
                imgui.end_child()
            else:
                imgui.text_colored(GAMETHEME.colors.error, "No country data loaded.")
                
            imgui.end_popup()

    def _draw_status_label(self, label, color, height, width=40):
        imgui.push_style_color(imgui.Col_.button, color)
        imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_dim)
        imgui.button(label, (width, height))
        imgui.pop_style_color(2)