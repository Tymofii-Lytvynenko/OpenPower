import arcade
import polars as pl
from typing import Optional
from imgui_bundle import imgui, icons_fontawesome_6

from src.client.ui.core.composer import UIComposer
from src.client.ui.core.theme import GAMETHEME
from src.client.renderers.flag_renderer import FlagRenderer
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused

class CentralBar:
    """
    HUD component displayed at the bottom of the screen.
    Handles country info, time controls, quick actions, and news ticker.
    """
    def __init__(self):
        self.show_speed_controls = True 
        self.news_ticker_text = "Global News: Simulation initialized and running. Waiting for events..."
        
        self.flag_renderer = FlagRenderer()
        self.active_tag = "" 
        self.is_own = True
        
        # Used to pass the popup selection back to the layout
        self._switch_request: Optional[str] = None

        # Layout configuration
        self.height = 100.0                
        self.top_section_h_pct = 0.65       
        self.content_scale_factor = 0.80    

    def render(self, state, net, target_tag: str, is_own_country: bool) -> Optional[str]:
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
        
        # Responsive Width
        bar_width = max(700.0, min(screen_w * 0.45, 900.0))
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

                # --- Draw Custom Backgrounds ---
                # Top part (Main info)
                draw_list.add_rect_filled(
                    p, (p.x + w, p.y + top_h), 
                    imgui.get_color_u32(GAMETHEME.colors.bg_window), 
                    GAMETHEME.rounding, imgui.ImDrawFlags_.round_corners_top
                )
                # Bottom part (Ticker - darker)
                draw_list.add_rect_filled(
                    (p.x, p.y + top_h), (p.x + w, p.y + h), 
                    imgui.get_color_u32(GAMETHEME.colors.bg_child), 
                    GAMETHEME.rounding, imgui.ImDrawFlags_.round_corners_bottom
                )
                # Border outline
                draw_list.add_rect(
                    p, (p.x + w, p.y + h), 
                    imgui.get_color_u32(GAMETHEME.colors.accent), 
                    GAMETHEME.rounding, 0, 1.5
                )

                padding_x = 12.0
                inner_item_h = top_h * self.content_scale_factor
                content_y = (top_h - inner_item_h) / 2
                
                left_section_w = 200.0  
                right_section_w = 250.0 

                # 1. Left Section: Country Flag & Info
                imgui.set_cursor_pos((padding_x, content_y))
                self._render_country_info(inner_item_h)

                # 2. Right Section: Time Controls
                right_start_x = w - right_section_w - padding_x
                imgui.set_cursor_pos((right_start_x, content_y))
                self._render_time_controls(state, net, right_section_w, inner_item_h)

                # 3. Center Section: Quick Actions
                # Calculate center position based on remaining space
                btn_count = 3
                btn_spacing = 10.0
                center_grp_w = (inner_item_h * btn_count) + (btn_spacing * (btn_count - 1))
                
                available_space_start = left_section_w + padding_x
                available_space_end = right_start_x
                center_x = available_space_start + ((available_space_end - available_space_start) - center_grp_w) / 2
                
                imgui.set_cursor_pos((center_x, content_y))
                self._render_quick_actions(inner_item_h, btn_spacing)

                # 4. Bottom Section: News Ticker
                imgui.set_cursor_pos((0, top_h))
                self._render_ticker(w, ticker_h)

                # 5. Popups
                self._render_country_selector_popup(state)

            except Exception as e:
                print(f"[CentralBar] Render Error: {e}")
            finally:
                imgui.end()
        
        imgui.pop_style_var() 
        return self._switch_request

    def _render_time_controls(self, state, net, width, height):
        imgui.begin_group()
        try:
            # Toggle between Speed Buttons and Date View
            if imgui.button(icons_fontawesome_6.ICON_FA_CLOCK, (40, height)):
                self.show_speed_controls = not self.show_speed_controls
            
            imgui.same_line()
            
            screen_w = width - 40 - imgui.get_style().item_spacing.x
            
            # Draw background for the time display area
            p = imgui.get_cursor_screen_pos()
            draw_list = imgui.get_window_draw_list()
            # A darker inset for the digital look
            draw_list.add_rect_filled(
                p, (p.x + screen_w, p.y + height), 
                imgui.get_color_u32((0,0,0,0.5)), 4.0
            )
            
            imgui.begin_child("TimeScreen", (screen_w, height), False, imgui.WindowFlags_.no_background)
            
            if self.show_speed_controls:
                # Center buttons vertically
                btn_h = 24
                # Roughly center vertically
                imgui.set_cursor_pos((10, (height - btn_h) / 2))
                self._draw_speed_buttons(state, net, btn_h)
            else:
                self._draw_date_display(state, screen_w, height)
            
            imgui.end_child()
        finally:
            imgui.end_group()

    def _draw_speed_buttons(self, state, net, btn_h):
        current_speed = getattr(state.time, "speed", 1)
        is_paused = getattr(state.time, "paused", False)
        btn_s = (24, btn_h) 
        
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (4, 0))
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (0, 0))
        
        # Pause Button
        if is_paused: 
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.warning)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.bg_window)
        
        if imgui.button("||", btn_s):
            net.send_action(ActionSetPaused("local", not is_paused))
        
        if is_paused: imgui.pop_style_color(2)
        imgui.same_line()

        # Speed 1-5
        for i in range(1, 6):
            is_active = (current_speed == i and not is_paused)
            if is_active: 
                imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.positive)
                imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.bg_window)
            
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
        
        full_text = f"{date_part}    {time_part}"
        text_size = imgui.calc_text_size(full_text)
        
        pos_x = (avail_w - text_size.x) / 2
        pos_y = (avail_h - text_size.y) / 2
        
        imgui.set_cursor_pos((pos_x, pos_y))
        imgui.text_colored(GAMETHEME.colors.text_main, date_part)
        imgui.same_line()
        imgui.text_colored(GAMETHEME.colors.text_dim, time_part)

    def _render_country_info(self, height):
        imgui.begin_group()
        try:
            flag_h = height
            flag_w = flag_h * 1.5
            
            self.flag_renderer.draw_flag(self.active_tag, flag_w, flag_h)

            imgui.same_line()

            imgui.begin_group()
            try:
                gap = 4.0
                row_h = (height - gap) / 2
                
                # Top Row: Country Tag (Click to open switcher)
                if imgui.button(f" {self.active_tag} ", (90, row_h)):
                    imgui.open_popup("CountrySelectorPopup")
                if imgui.is_item_hovered(): imgui.set_tooltip("Switch Country (Debug)")
                
                # Bottom Row: Status Indicator
                imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() + gap - 4) # Adjust spacing manually due to group
                
                if self.is_own:
                    self._draw_status_label("COMMAND", GAMETHEME.colors.positive, row_h, width=90)
                else:
                    self._draw_status_label("VIEWING", GAMETHEME.colors.warning, row_h, width=90)

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
        
        # 1. AI Button
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_BRAIN}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("AI Settings")
        imgui.same_line()
        
        # 2. Statistics
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_CHART_LINE}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Global Ledger")
        imgui.same_line()
        
        # 3. Messages
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_ENVELOPE}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Diplomatic Messages")
        
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
        current_y = imgui.get_cursor_pos_y()
        text_y = (section_h - text_line_h) / 2
        
        # Draw Text
        imgui.set_cursor_pos((padding_x, current_y + text_y))
        imgui.text_colored(GAMETHEME.colors.text_dim, self.news_ticker_text)
        
        # 2. Draw "News Button" on the far right
        btn_h = section_h - 4.0 
        btn_w = btn_h
        
        btn_x = section_w - btn_w - 6.0 
        btn_y = current_y + (section_h - btn_h) / 2
        
        imgui.set_cursor_pos((btn_x, btn_y))
        
        imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.bg_child)
        if imgui.button(icons_fontawesome_6.ICON_FA_NEWSPAPER, (btn_w, btn_h)):
            pass # Open history
        imgui.pop_style_color()
        
        if imgui.is_item_hovered():
            imgui.set_tooltip("News History")

    def _render_country_selector_popup(self, state):
        """Lists all countries in the game state for debug switching."""
        imgui.set_next_window_size((300, 400))
        if imgui.begin_popup("CountrySelectorPopup"):
            imgui.text_disabled("Switch Viewpoint (Debug)")
            imgui.separator()
            
            if "countries" in state.tables:
                df = state.tables["countries"]
                # Sort by ID
                try: df = df.sort("id")
                except: pass
                
                imgui.begin_child("CountryList", (0, 0), True)
                
                for row in df.iter_rows(named=True):
                    tag = row['id']
                    name = row.get('name', tag)
                    label = f"{tag} - {name}"
                    
                    is_selected = (tag == self.active_tag)
                    if is_selected:
                        imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.accent)
                    
                    if imgui.selectable(label, is_selected)[0]:
                        self._switch_request = tag
                        imgui.close_current_popup()
                        
                    if is_selected:
                        imgui.pop_style_color()
                        # Auto scroll to selected
                        imgui.set_scroll_here_y()
                        
                imgui.end_child()
            else:
                imgui.text_colored(GAMETHEME.colors.error, "No country data loaded.")
                
            imgui.end_popup()

    def _draw_status_label(self, label, color, height, width=40):
        imgui.push_style_color(imgui.Col_.button, color)
        imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.bg_window)
        imgui.push_style_var(imgui.StyleVar_.frame_rounding, 4.0)
        imgui.button(label, (width, height))
        imgui.pop_style_var()
        imgui.pop_style_color(2)