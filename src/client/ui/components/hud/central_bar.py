import arcade
from typing import Optional
from imgui_bundle import imgui, icons_fontawesome_6

from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.client.services.network_client_service import NetworkClient
from src.client.renderers.flag_renderer import FlagRenderer
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused

class CentralBar:
    def __init__(self):
        self.show_speed_controls = True
        self.news_ticker_text = "Global News: Simulation initialized."
        
        # Dependencies
        self.flag_renderer = FlagRenderer()
        self.active_player_tag = "" 

        # Layout Constants
        self.WIDTH = 640.0
        self.HEIGHT = 80.0
        self.TOP_BAR_H = 55.0  # Height of the main control area

    def render(self, composer: UIComposer, state, net: NetworkClient, player_tag: str) -> str:
        self.active_player_tag = player_tag
        
        viewport = imgui.get_main_viewport()
        screen_w = viewport.size.x
        screen_h = viewport.size.y
        
        # Center horizontally, position at bottom
        pos_x = (screen_w - self.WIDTH) / 2
        pos_y = screen_h - self.HEIGHT - 10

        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((self.WIDTH, self.HEIGHT))

        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.no_scroll_with_mouse |
                 imgui.WindowFlags_.no_background)

        # --- DRAW LOOP ---
        if imgui.begin("CentralBar", True, flags):
            try:
                draw_list = imgui.get_window_draw_list()
                p = imgui.get_cursor_screen_pos()
                
                # 1. Custom Background Rendering
                # Upper Darker Panel (Controls)
                draw_list.add_rect_filled(
                    p, 
                    (p.x + self.WIDTH, p.y + self.TOP_BAR_H), 
                    imgui.get_color_u32(GAMETHEME.col_panel_bg)
                )
                # Lower Lighter Panel (Ticker)
                draw_list.add_rect_filled(
                    (p.x, p.y + self.TOP_BAR_H), 
                    (p.x + self.WIDTH, p.y + self.HEIGHT), 
                    imgui.get_color_u32(GAMETHEME.col_overlay_bg)
                )
                # Border Outline
                draw_list.add_rect(
                    p, 
                    (p.x + self.WIDTH, p.y + self.HEIGHT), 
                    imgui.get_color_u32(GAMETHEME.border), 
                    GAMETHEME.rounding
                )

                # 2. Content Layout
                # We use cursor positioning to create three distinct columns
                
                # --- LEFT COL: Flag & Country Info ---
                imgui.set_cursor_pos((10, 8))
                self._render_country_info(composer)

                # --- CENTER COL: Quick Actions ---
                # Calculate center based on width
                center_group_w = 140
                imgui.set_cursor_pos(((self.WIDTH - center_group_w) / 2, 8))
                self._render_quick_actions()

                # --- RIGHT COL: Time Controls ---
                right_group_w = 190
                imgui.set_cursor_pos((self.WIDTH - right_group_w - 10, 8))
                self._render_time_controls(state, net)

                # --- BOTTOM ROW: News Ticker ---
                imgui.set_cursor_pos((10, self.TOP_BAR_H + 4))
                self._render_ticker()

                # --- Popups ---
                self._render_country_selector_popup(state)

            except Exception as e:
                print(f"[CentralBar] Render Error: {e}")
            finally:
                imgui.end()
        else:
            imgui.end()
            
        return self.active_player_tag

    # --- SUB-SECTIONS ---

    def _render_country_info(self, composer: UIComposer):
        imgui.begin_group()
        
        # 1. Flag
        flag_tex = self.flag_renderer.get_texture(self.active_player_tag)
        if flag_tex:
            composer.draw_image(flag_tex, 64, 40)
        else:
            # Placeholder if missing
            composer.dummy((64, 40))

        imgui.same_line()

        # 2. Text Info
        imgui.begin_group()
        
        # Country Selector Button
        if imgui.button(f" {self.active_player_tag} ", (110, 20)):
            imgui.open_popup("CountrySelectorPopup")
        
        # Status Row
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (2, 0))
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (2, 2))
        
        self._draw_status_label("ALLIED", GAMETHEME.col_positive)
        imgui.same_line()
        self._draw_status_label("100%", GAMETHEME.col_info)
        
        imgui.pop_style_var(2)
        imgui.end_group() # End Text Info

        imgui.end_group() # End Left Col

    def _render_quick_actions(self):
        """Renders 3 central action buttons."""
        btn_sz = (40, 40)
        
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_DESKTOP}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Overview")
        
        imgui.same_line()
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_CHART_LINE}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Statistics")
        
        imgui.same_line()
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_MESSAGE}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Diplomacy")

    def _render_time_controls(self, state, net):
        """Renders the Date and Speed/Pause controls."""
        imgui.begin_group()
        
        # Row 1: Date/Time Text
        # We manually align text to center it within the group area if needed, 
        # but left-aligning inside the Right Group is usually cleaner.
        t = state.time
        date_str = t.date_str.split(" ")[0] if t.date_str else "Loading..."
        
        imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_active_accent)
        imgui.text(date_str)
        imgui.pop_style_color()
        
        # Row 2: Controls
        # Pause | 1 | 2 | 3
        btn_s = (24, 20)
        style = imgui.get_style()
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (2, 0))

        is_paused = getattr(state.time, "paused", False)
        current_speed = getattr(state.time, "speed", 1)

        # Pause Button
        if is_paused: 
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_warning)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_black)
        
        if imgui.button(icons_fontawesome_6.ICON_FA_PAUSE, btn_s):
            net.send_action(ActionSetPaused("local", not is_paused))
            
        if is_paused: 
            imgui.pop_style_color(2)

        imgui.same_line()

        # Speed Buttons (1, 2, 3)
        for i in range(1, 4):
            is_active = (current_speed == i and not is_paused)
            if is_active: 
                imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_positive)
                imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_black)

            if imgui.button(str(i), btn_s):
                net.send_action(ActionSetPaused("local", False))
                net.send_action(ActionSetGameSpeed("local", i))
            
            if is_active: 
                imgui.pop_style_color(2)
            
            if i < 3: imgui.same_line()

        imgui.pop_style_var() # Item spacing
        imgui.end_group()

    def _render_ticker(self):
        """Renders the news line at the bottom."""
        imgui.align_text_to_frame_padding()
        imgui.text_colored(GAMETHEME.col_text_disabled, icons_fontawesome_6.ICON_FA_NEWSPAPER)
        imgui.same_line()
        imgui.text_colored(GAMETHEME.col_text_bright, self.news_ticker_text)

    def _render_country_selector_popup(self, state):
        """Debug tool to switch player perspective."""
        if imgui.begin_popup("CountrySelectorPopup"):
            imgui.text_disabled("Switch Viewpoint")
            imgui.separator()
            if "countries" in state.tables:
                df = state.tables["countries"]
                # Use a child window if list is long to allow scrolling
                if imgui.begin_child("CountryList", (200, 300)):
                    for row in df.head(50).iter_rows(named=True):
                        tag = row['id']
                        name = row.get('name', tag)
                        if imgui.selectable(f"{tag} - {name}", False)[0]:
                            self.active_player_tag = tag
                            imgui.close_current_popup()
                    imgui.end_child()
            imgui.end_popup()

    def _draw_status_label(self, label, color):
        """Draws a small colored rectangle with text."""
        imgui.push_style_color(imgui.Col_.button, color)
        imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_black)
        imgui.button(label, (54, 16))
        imgui.pop_style_color(2)