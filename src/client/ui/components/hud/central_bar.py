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
    Refactored to use UIComposer and modular rendering methods.
    """
    def __init__(self):
        # Composition helpers
        self.composer = UIComposer(GAMETHEME)
        self.flag_renderer = FlagRenderer()

        # Local State
        self.show_speed_controls = False 
        self.news_ticker_text = "Global News: Simulation initialized and running. Waiting for events..."
        self.active_tag = "" 
        self.is_own = True
        self._switch_request: Optional[str] = None

        # Layout configuration
        self.height = 100.0                 
        self.top_section_h_pct = 0.65       
        self.content_scale_factor = 0.80    

    def render(self, state, net, target_tag: str, is_own_country: bool) -> Optional[str]:
        """
        Main render loop.
        Returns: A string (Country Tag) if the user selected a new country from the debug popup, else None.
        """
        self.active_tag = target_tag
        self.is_own = is_own_country
        self._switch_request = None 
        
        # 1. Calculate Geometry
        viewport = imgui.get_main_viewport()
        screen_w, screen_h = viewport.size.x, viewport.size.y
        
        bar_width = max(700.0, min(screen_w * 0.45, 800.0))
        pos_x = (screen_w - bar_width) / 2
        pos_y = screen_h - self.height - 15 

        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((bar_width, self.height))
        imgui.push_style_var(imgui.StyleVar_.window_padding, (0, 0))

        # 2. Window Setup
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.no_scroll_with_mouse |
                 imgui.WindowFlags_.no_background)

        if imgui.begin("CentralBar", True, flags):
            try:
                # Layout calculations
                w = imgui.get_window_width()
                h = imgui.get_window_height()
                top_h = h * self.top_section_h_pct
                ticker_h = h - top_h
                inner_content_h = top_h * self.content_scale_factor
                content_pad_y = (top_h - inner_content_h) / 2
                padding_x = 12.0

                # 3. Draw Custom Background
                self._render_background(w, h, top_h)

                # 4. Render Content Sections
                
                # Left: Flag & Country Info
                imgui.set_cursor_pos((padding_x, content_pad_y))
                self._render_flag_section(inner_content_h)

                # Right: Time Controls
                right_section_w = 250.0
                right_start_x = w - right_section_w - padding_x
                imgui.set_cursor_pos((right_start_x, content_pad_y))
                self._render_time_section(state, net, right_section_w, inner_content_h)

                # Center: Quick Actions
                # Centered between the left section (Flag) and right section (Time)
                left_section_w = 200.0 
                avail_center_w = right_start_x - (left_section_w + padding_x)
                center_start_x = (left_section_w + padding_x) + (avail_center_w / 2)
                
                # We center the buttons around 'center_start_x' inside _render_quick_actions
                imgui.set_cursor_pos((center_start_x, content_pad_y))
                self._render_quick_actions(inner_content_h)

                # Bottom: Ticker
                imgui.set_cursor_pos((0, top_h))
                self._render_ticker(w, ticker_h)

                # 5. Debug Popups
                self._render_debug_selector(state)

            except Exception as e:
                print(f"[CentralBar] Render Error: {e}")
            finally:
                imgui.end()
        
        imgui.pop_style_var() 
        return self._switch_request

    # =========================================================================
    # Sub-Renderers
    # =========================================================================

    def _render_background(self, w: float, h: float, split_y: float):
        """Draws the specific two-tone glass background for the bar."""
        draw_list = imgui.get_window_draw_list()
        p = imgui.get_cursor_screen_pos()
        
        # Top part (Main Info)
        draw_list.add_rect_filled(
            p, (p.x + w, p.y + split_y), 
            imgui.get_color_u32(GAMETHEME.colors.bg_window), 
            GAMETHEME.rounding, imgui.ImDrawFlags_.round_corners_top
        )
        # Bottom part (Ticker - darker)
        draw_list.add_rect_filled(
            (p.x, p.y + split_y), (p.x + w, p.y + h), 
            imgui.get_color_u32(GAMETHEME.colors.bg_popup), 
            GAMETHEME.rounding, imgui.ImDrawFlags_.round_corners_bottom
        )
        # Outline
        draw_list.add_rect(
            p, (p.x + w, p.y + h), 
            imgui.get_color_u32(GAMETHEME.colors.accent), 
            GAMETHEME.rounding, 0, 1.5
        )

    def _render_flag_section(self, height: float):
        """Renders the flag and the country tag/status."""
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
                
                # Top Row: Country Tag (Clickable for debug)
                if imgui.button(f" {self.active_tag} ", (90, row_h)):
                    imgui.open_popup("CountrySelectorPopup")
                if imgui.is_item_hovered(): imgui.set_tooltip("Switch Country (Debug)")
                
                # Bottom Row: Status Indicator
                imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() + gap - 4)
                
                if self.is_own:
                    self._draw_status_label("COMMAND", GAMETHEME.colors.positive, row_h, 90)
                else:
                    self._draw_status_label("VIEWING", GAMETHEME.colors.warning, row_h, 90)
            finally:
                imgui.end_group()
        finally:
            imgui.end_group()

    def _render_time_section(self, state, net, width: float, height: float):
        """Renders the clock toggle and the digital display/speed controls."""
        imgui.begin_group()
        try:
            # Toggle Button (Clock Icon)
            if imgui.button(icons_fontawesome_6.ICON_FA_CLOCK, (40, height)):
                self.show_speed_controls = not self.show_speed_controls
            
            imgui.same_line()
            
            # LCD Display Area
            lcd_w = width - 40 - imgui.get_style().item_spacing.x
            
            # Draw LCD Background
            p = imgui.get_cursor_screen_pos()
            draw_list = imgui.get_window_draw_list()
            draw_list.add_rect_filled(
                p, (p.x + lcd_w, p.y + height), 
                imgui.get_color_u32((0,0,0,0.5)), 4.0
            )
            
            # Render LCD Content
            imgui.begin_child("TimeScreen", (lcd_w, height), False, imgui.WindowFlags_.no_background)
            if self.show_speed_controls:
                self._draw_speed_controls(state, net, height)
            else:
                self._draw_date_display(state, lcd_w, height)
            imgui.end_child()

        finally:
            imgui.end_group()

    def _draw_speed_controls(self, state, net, total_height: float):
        """Renders Pause and Speed 1-5 buttons centered vertically."""
        btn_h = 24
        # Vertical centering
        imgui.set_cursor_pos_y((total_height - btn_h) / 2)
        imgui.set_cursor_pos_x(10) # Padding left

        current_speed = getattr(state.time, "speed", 1)
        is_paused = getattr(state.time, "paused", False)
        btn_s = (24, btn_h) 
        
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (4, 0))
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (0, 0))
        
        # Pause Button
        if is_paused: 
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.warning)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_main)
        
        if imgui.button("||", btn_s):
            net.send_action(ActionSetPaused("local", not is_paused))
        
        if is_paused: imgui.pop_style_color(2)
        imgui.same_line()

        # Speed Buttons 1-5
        for i in range(1, 6):
            is_active = (current_speed == i and not is_paused)
            if is_active: 
                imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.interaction_active)
                imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.bg_window)
            
            if imgui.button(str(i), btn_s):
                net.send_action(ActionSetPaused("local", False))
                net.send_action(ActionSetGameSpeed("local", i))
            
            if is_active: imgui.pop_style_color(2)
            if i < 5: imgui.same_line()
            
        imgui.pop_style_var(2)

    def _draw_date_display(self, state, avail_w, avail_h):
        """Renders the text date."""
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

    def _render_quick_actions(self, height: float):
        """Renders the central action buttons."""
        if not self.is_own:
            imgui.begin_disabled()

        btn_count = 3
        spacing = 10.0
        btn_sz = (height, height)
        
        # Calculate width of the group to center it properly relative to the cursor start
        group_width = (height * btn_count) + (spacing * (btn_count - 1))
        
        # Offset cursor back by half the group width to center on the point provided
        current_x = imgui.get_cursor_pos_x()
        imgui.set_cursor_pos_x(current_x - (group_width / 2))

        imgui.push_style_var(imgui.StyleVar_.item_spacing, (spacing, 0))
        
        # 1. AI Button
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_BRAIN}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("AI Director")
        imgui.same_line()
        
        # 2. Statistics
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_CHART_LINE}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Global Statistics")
        imgui.same_line()
        
        # 3. Messages
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_ENVELOPE}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Diplomatic Messages")
        
        imgui.pop_style_var()

        if not self.is_own:
            imgui.end_disabled()

    def _render_ticker(self, section_w: float, section_h: float):
        """Renders the scrolling news ticker and history button."""
        padding_x = 12.0
        
        # 1. Ticker Text
        text_line_h = imgui.get_text_line_height()
        current_y = imgui.get_cursor_pos_y()
        text_y = (section_h - text_line_h) / 2
        
        imgui.set_cursor_pos((padding_x, current_y + text_y))
        imgui.text_colored(GAMETHEME.colors.text_main, self.news_ticker_text)
        
        # 2. History Button (Far Right)
        btn_h = section_h - 4.0 
        btn_w = btn_h
        btn_x = section_w - btn_w - 6.0 
        btn_y = current_y + (section_h - btn_h) / 2
        
        imgui.set_cursor_pos((btn_x, btn_y))
        
        imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.bg_child)
        if imgui.button(icons_fontawesome_6.ICON_FA_NEWSPAPER, (btn_w, btn_h)):
            pass 
        imgui.pop_style_color()
        
        if imgui.is_item_hovered(): imgui.set_tooltip("News History")

    def _render_debug_selector(self, state):
        """Renders the Country Selector Popup for debug/view switching."""
        imgui.set_next_window_size((300, 400))
        if imgui.begin_popup("CountrySelectorPopup"):
            imgui.text_disabled("Switch Viewpoint (Debug)")
            imgui.separator()
            
            if "countries" in state.tables:
                df = state.tables["countries"]
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
                        imgui.set_scroll_here_y()
                        
                imgui.end_child()
            else:
                imgui.text_colored(GAMETHEME.colors.error, "No country data loaded.")
                
            imgui.end_popup()

    def _draw_status_label(self, label: str, color: tuple, height: float, width: float = 40):
        """Helper to draw a colored status badge."""
        imgui.push_style_color(imgui.Col_.button, color)
        imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.bg_window)
        imgui.push_style_var(imgui.StyleVar_.frame_rounding, 4.0)
        imgui.button(label, (width, height))
        imgui.pop_style_var()
        imgui.pop_style_color(2)