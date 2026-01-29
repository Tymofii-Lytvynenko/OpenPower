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
        # --- RESTORED: View State ---
        self.show_speed_controls = True 
        
        self.news_ticker_text = "Global News: Simulation initialized."
        self.flag_renderer = FlagRenderer()
        self.active_player_tag = "" 

        # Layout Constants
        self.WIDTH = 640.0
        self.HEIGHT = 80.0
        self.TOP_BAR_H = 55.0

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

        if imgui.begin("CentralBar", True, flags):
            try:
                draw_list = imgui.get_window_draw_list()
                p = imgui.get_cursor_screen_pos()
                
                # --- BACKGROUND DRAWING ---
                # Control Panel (Top)
                draw_list.add_rect_filled(
                    p, 
                    (p.x + self.WIDTH, p.y + self.TOP_BAR_H), 
                    imgui.get_color_u32(GAMETHEME.col_panel_bg)
                )
                # Ticker Panel (Bottom)
                draw_list.add_rect_filled(
                    (p.x, p.y + self.TOP_BAR_H), 
                    (p.x + self.WIDTH, p.y + self.HEIGHT), 
                    imgui.get_color_u32(GAMETHEME.col_overlay_bg)
                )
                # Border
                draw_list.add_rect(
                    p, 
                    (p.x + self.WIDTH, p.y + self.HEIGHT), 
                    imgui.get_color_u32(GAMETHEME.border), 
                    GAMETHEME.rounding
                )

                # --- 1. LEFT: Flag & Country ---
                imgui.set_cursor_pos((10, 8))
                self._render_country_info(composer)

                # --- 2. CENTER: Quick Actions ---
                # Approx center of bar minus half the width of buttons group
                imgui.set_cursor_pos(((self.WIDTH - 140) / 2, 8))
                self._render_quick_actions()

                # --- 3. RIGHT: Time Controls ---
                # RESTORED: Positioned to fit the Toggle Button + Screen Box
                # Width needed: 50 (Btn) + 8 (Space) + 160 (Box) = ~220px
                imgui.set_cursor_pos((self.WIDTH - 230, 5))
                self._render_time_controls(state, net)

                # --- 4. BOTTOM: News Ticker ---
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

    def _render_time_controls(self, state, net):
        """
        RESTORED: Toggles between 'TIME' controls and Date Display.
        This fixes the unresponsive buttons by using the original logic structure.
        """
        imgui.begin_group()
        
        # 1. TIME Toggle Button
        # Used to switch views between Controls and Clock
        if imgui.button("TIME", (50, 45)):
            self.show_speed_controls = not self.show_speed_controls
        
        imgui.same_line()
        
        # 2. The "Screen" Box
        # We draw a container that holds either the controls or the date text
        p = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()
        
        box_w, box_h = 160.0, 45.0
        
        # Black background for the 'screen' look
        draw_list.add_rect_filled(p, (p.x + box_w, p.y + box_h), imgui.get_color_u32(GAMETHEME.col_black))
        draw_list.add_rect(p, (p.x + box_w, p.y + box_h), imgui.get_color_u32(GAMETHEME.border))

        # Offset cursor to draw inside this new box
        # We use a dummy to reserve the space logically in ImGui layout
        cursor_start = imgui.get_cursor_pos()
        imgui.dummy((box_w, box_h)) 
        
        # Move back to start of dummy + padding to place content
        imgui.set_cursor_pos((cursor_start.x + 10, cursor_start.y + 7))

        # 3. Logic Switch
        if self.show_speed_controls:
            self._draw_speed_buttons(state, net)
        else:
            self._draw_date_display(state)

        imgui.end_group()

    def _draw_speed_buttons(self, state, net):
        """Draws Pause | 1 | 2 | 3 buttons."""
        current_speed = getattr(state.time, "speed", 1)
        is_paused = getattr(state.time, "paused", False)
        
        btn_s = (30, 30)
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (4, 0))

        # --- PAUSE ---
        # Highlight if paused
        if is_paused: 
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_warning)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_black)
            
        if imgui.button(icons_fontawesome_6.ICON_FA_PAUSE, btn_s):
            # Toggle pause state
            net.send_action(ActionSetPaused("local", not is_paused))
            
        if is_paused: 
            imgui.pop_style_color(2)

        imgui.same_line()

        # --- SPEEDS 1, 2, 3 ---
        for i in range(1, 4):
            # Highlight if this is the active speed AND not paused
            is_active = (current_speed == i and not is_paused)
            if is_active: 
                imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_positive)
                imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_black)

            if imgui.button(str(i), btn_s):
                # Unpause and set speed
                net.send_action(ActionSetPaused("local", False))
                net.send_action(ActionSetGameSpeed("local", i))
            
            if is_active: 
                imgui.pop_style_color(2)
            
            if i < 3: imgui.same_line()

        imgui.pop_style_var()

    def _draw_date_display(self, state):
        """Draws the date string."""
        t = state.time
        parts = t.date_str.split(" ")
        date_part = parts[0] if len(parts) > 0 else "N/A"
        time_part = parts[1] if len(parts) > 1 else ""
        
        # Center vertically roughly
        imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() + 4)
        
        imgui.text_colored(GAMETHEME.col_positive, date_part)
        imgui.same_line()
        imgui.text_colored(GAMETHEME.col_text_bright, time_part)

    def _render_country_info(self, composer: UIComposer):
        imgui.begin_group()
        
        # 1. Flag
        flag_tex = self.flag_renderer.get_texture(self.active_player_tag)
        if flag_tex:
            composer.draw_image(flag_tex, 64, 40)
        else:
            composer.dummy((64, 40))

        imgui.same_line()

        # 2. Text Info
        imgui.begin_group()
        if imgui.button(f" {self.active_player_tag} ", (110, 20)):
            imgui.open_popup("CountrySelectorPopup")
        
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (2, 0))
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (2, 2))
        
        self._draw_status_label("ALLIED", GAMETHEME.col_positive)
        imgui.same_line()
        self._draw_status_label("100%", GAMETHEME.col_info)
        
        imgui.pop_style_var(2)
        imgui.end_group()
        imgui.end_group()

    def _render_quick_actions(self):
        btn_sz = (40, 40)
        
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_DESKTOP}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Overview")
        
        imgui.same_line()
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_CHART_LINE}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Statistics")
        
        imgui.same_line()
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_MESSAGE}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Diplomacy")

    def _render_ticker(self):
        imgui.align_text_to_frame_padding()
        imgui.text_colored(GAMETHEME.col_text_disabled, icons_fontawesome_6.ICON_FA_NEWSPAPER)
        imgui.same_line()
        imgui.text_colored(GAMETHEME.col_text_bright, self.news_ticker_text)

    def _render_country_selector_popup(self, state):
        if imgui.begin_popup("CountrySelectorPopup"):
            imgui.text_disabled("Switch Viewpoint")
            imgui.separator()
            if "countries" in state.tables:
                df = state.tables["countries"]
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
        imgui.push_style_color(imgui.Col_.button, color)
        imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_black)
        imgui.button(label, (54, 16))
        imgui.pop_style_color(2)