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
        # --- View State ---
        self.show_speed_controls = True 
        self.news_ticker_text = "Global News: Simulation initialized and running."
        self.flag_renderer = FlagRenderer()
        self.active_player_tag = "" 

        # Layout Settings
        self.height = 100.0
        self.top_section_h_pct = 0.65 # Top section takes 65% of height, Ticker takes rest

    def render(self, composer: UIComposer, state, net: NetworkClient, player_tag: str) -> str:
        self.active_player_tag = player_tag
        
        viewport = imgui.get_main_viewport()
        screen_w = viewport.size.x
        screen_h = viewport.size.y
        
        # --- Dynamic Sizing ---
        # Width: 35% of screen, but clamped between 600px and 900px
        bar_width = max(600.0, min(screen_w * 0.35, 900.0))
        
        # Position: Centered horizontally, anchored to bottom with padding
        pos_x = (screen_w - bar_width) / 2
        pos_y = screen_h - self.height - 15 # 15px padding from bottom

        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((bar_width, self.height))

        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.no_scroll_with_mouse |
                 imgui.WindowFlags_.no_background)

        if imgui.begin("CentralBar", True, flags):
            try:
                draw_list = imgui.get_window_draw_list()
                p = imgui.get_cursor_screen_pos()
                
                # We recalculate actual dimensions in case ImGui constrained the window
                w = imgui.get_window_width()
                h = imgui.get_window_height()
                top_h = h * self.top_section_h_pct

                # --- BACKGROUND DRAWING ---
                # 1. Control Panel (Top)
                draw_list.add_rect_filled(
                    p, 
                    (p.x + w, p.y + top_h), 
                    imgui.get_color_u32(GAMETHEME.col_panel_bg),
                    GAMETHEME.rounding,
                    imgui.ImDrawFlags_.round_corners_top
                )
                # 2. Ticker Panel (Bottom)
                draw_list.add_rect_filled(
                    (p.x, p.y + top_h), 
                    (p.x + w, p.y + h), 
                    imgui.get_color_u32(GAMETHEME.col_overlay_bg),
                    GAMETHEME.rounding,
                    imgui.ImDrawFlags_.round_corners_bottom
                )
                # 3. Border
                draw_list.add_rect(
                    p, 
                    (p.x + w, p.y + h), 
                    imgui.get_color_u32(GAMETHEME.border),
                    GAMETHEME.rounding,
                    0, 
                    1.5 # Thicker border
                )

                # --- LAYOUT LOGIC ---
                # We use a cursor strategy:
                # Left Group | Spring | Center Group | Spring | Right Group
                
                padding_x = 12.0
                padding_y = 8.0

                # 1. LEFT: Flag & Country Info
                imgui.set_cursor_pos((padding_x, padding_y))
                self._render_country_info(composer, top_h)

                # 2. RIGHT: Time Controls 
                # We render this *second* but position it explicitly to the right
                # to ensure it fits before calculating the center space.
                
                # Determine needed width for time controls roughly
                # Button (50) + Spacing + Box (180) ~ 240
                right_section_w = 240.0 
                imgui.set_cursor_pos((w - right_section_w - padding_x, padding_y))
                self._render_time_controls(state, net, right_section_w, top_h - (padding_y*2))

                # 3. CENTER: Quick Actions
                # Calculate center position based on remaining space
                center_section_w = 150.0 # Approx width of 3 buttons
                center_x = (w - center_section_w) / 2
                imgui.set_cursor_pos((center_x, padding_y))
                self._render_quick_actions(top_h - (padding_y*2))

                # 4. BOTTOM: News Ticker
                # Center vertically in the bottom section
                ticker_y = top_h + (h - top_h - imgui.get_text_line_height()) / 2
                imgui.set_cursor_pos((padding_x, ticker_y))
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

    def _render_time_controls(self, state, net, width, height):
        imgui.begin_group()
        
        # Style vars for standard button height matching
        btn_h = height
        
        # 1. TIME Toggle Button
        if imgui.button("TIME", (50, btn_h)):
            self.show_speed_controls = not self.show_speed_controls
        
        imgui.same_line()
        
        # 2. The "Screen" Box (LCD Display Look)
        # We fill the remaining width allocated to this section
        screen_w = width - 50 - imgui.get_style().item_spacing.x
        
        p = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()
        
        # Draw Black Screen Background
        draw_list.add_rect_filled(p, (p.x + screen_w, p.y + btn_h), imgui.get_color_u32(GAMETHEME.col_black))
        draw_list.add_rect(p, (p.x + screen_w, p.y + btn_h), imgui.get_color_u32(GAMETHEME.border))

        # Create a nested group / child for clipping inside the screen
        imgui.begin_child("TimeScreen", (screen_w, btn_h), False, imgui.WindowFlags_.no_background)
        
        # Vertically Center content inside the screen
        # We calculate offsets based on standard button sizes inside
        imgui.set_cursor_pos((5, (btn_h - 26)/2)) # 26 is approx height of small buttons/text

        if self.show_speed_controls:
            self._draw_speed_buttons(state, net)
        else:
            self._draw_date_display(state)
            
        imgui.end_child()

        imgui.end_group()

    def _draw_speed_buttons(self, state, net):
        """Draws Pause | 1 | 2 | 3 buttons."""
        current_speed = getattr(state.time, "speed", 1)
        is_paused = getattr(state.time, "paused", False)
        
        # Button Size (Small squares)
        btn_s = (26, 26) 
        
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (2, 0))
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (0, 0))

        # --- PAUSE ---
        if is_paused: 
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_warning)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_black)
            
        if imgui.button(icons_fontawesome_6.ICON_FA_PAUSE, btn_s):
            net.send_action(ActionSetPaused("local", not is_paused))
            
        if is_paused: 
            imgui.pop_style_color(2)

        imgui.same_line()

        # --- SPEEDS 1-5 ---
        for i in range(1, 6):
            is_active = (current_speed == i and not is_paused)
            if is_active: 
                imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_positive)
                imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_black)

            if imgui.button(str(i), btn_s):
                net.send_action(ActionSetPaused("local", False))
                net.send_action(ActionSetGameSpeed("local", i))
            
            if is_active: 
                imgui.pop_style_color(2)
            
            if i < 5: imgui.same_line()

        imgui.pop_style_var(2)

    def _draw_date_display(self, state):
        t = state.time
        parts = t.date_str.split(" ")
        date_part = parts[0] if len(parts) > 0 else "N/A"
        time_part = parts[1] if len(parts) > 1 else ""
        
        imgui.align_text_to_frame_padding()
        imgui.text_colored(GAMETHEME.col_positive, date_part)
        imgui.same_line()
        imgui.text_colored(GAMETHEME.col_text_bright, time_part)

    def _render_country_info(self, composer: UIComposer, height):
        imgui.begin_group()
        
        # 1. Flag (Aspect Ratio 3:2 roughly)
        flag_h = height - 16 # padding
        flag_w = flag_h * 1.5
        
        flag_tex = self.flag_renderer.get_texture(self.active_player_tag)
        
        # Center vertically in the group
        current_y = imgui.get_cursor_pos_y()
        
        if flag_tex:
            composer.draw_image(flag_tex, flag_w, flag_h)
        else:
            composer.dummy((flag_w, flag_h))

        imgui.same_line()

        # 2. Text Info Stack
        imgui.begin_group()
        # Country Tag Button
        if imgui.button(f" {self.active_player_tag} ", (90, 22)):
            imgui.open_popup("CountrySelectorPopup")
        
        # Status Row
        imgui.dummy((0, 2))
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (2, 0))
        
        self._draw_status_label("ALLIED", GAMETHEME.col_positive)
        imgui.same_line()
        self._draw_status_label("100%", GAMETHEME.col_info)
        
        imgui.pop_style_var()
        imgui.end_group()
        imgui.end_group()

    def _render_quick_actions(self, height):
        # Square buttons based on available height
        btn_sz = (height, height)
        
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (8, 0))
        
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_DESKTOP}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Overview")
        
        imgui.same_line()
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_CHART_LINE}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Statistics")
        
        imgui.same_line()
        if imgui.button(f"{icons_fontawesome_6.ICON_FA_MESSAGE}", btn_sz): pass
        if imgui.is_item_hovered(): imgui.set_tooltip("Diplomacy")
        
        imgui.pop_style_var()

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
        # Small font or default?
        imgui.button(label, (44, 16))
        imgui.pop_style_color(2)