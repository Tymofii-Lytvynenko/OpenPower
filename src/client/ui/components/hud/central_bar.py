import arcade
import polars as pl
from pathlib import Path
from typing import Dict, Optional
from imgui_bundle import imgui

from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.client.services.network_client_service import NetworkClient
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused

class CentralBar:
    def __init__(self):
        self.show_speed_controls = False
        self.news_ticker_text = "Welcome to OpenPower. Global news will appear here..."
        
        # Internal Cache for flags
        self._flag_cache: Dict[str, arcade.Texture] = {}
        self.active_player_tag = "" 

    def render(self, composer: UIComposer, state, net: NetworkClient, player_tag: str) -> str:
        self.active_player_tag = player_tag
        
        viewport = imgui.get_main_viewport()
        screen_w = viewport.size.x
        screen_h = viewport.size.y
        
        bar_w = 700
        bar_h = 85
        
        imgui.set_next_window_pos(( (screen_w - bar_w)/2, screen_h - bar_h - 10 ))
        imgui.set_next_window_size((bar_w, bar_h))

        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.no_scroll_with_mouse |
                 imgui.WindowFlags_.no_background)

        # SAFE WINDOW BLOCK
        if imgui.begin("CentralBar", True, flags):
            try:
                draw_list = imgui.get_window_draw_list()
                p = imgui.get_cursor_screen_pos()
                
                # Draw Backgrounds
                draw_list.add_rect_filled(p, (p.x + bar_w, p.y + 60), imgui.get_color_u32(GAMETHEME.col_panel_bg))
                draw_list.add_rect_filled((p.x, p.y + 60), (p.x + bar_w, p.y + bar_h), imgui.get_color_u32(GAMETHEME.col_overlay_bg))
                draw_list.add_rect(p, (p.x + bar_w, p.y + bar_h), imgui.get_color_u32(GAMETHEME.border), 4.0)

                # --- Section 1: Flag & Country ---
                imgui.begin_group()
                
                flag_tex = self._get_flag_texture(player_tag)
                
                # FIX: Check if texture is valid (not None) before drawing
                if flag_tex:
                    composer.draw_image(flag_tex, 80, 50)
                else:
                    composer.dummy((80, 50))
                
                imgui.same_line()
                
                imgui.begin_group()
                if imgui.button(f" {player_tag} ", (180, 24)):
                    imgui.open_popup("CountrySelectorPopup")
                
                imgui.push_style_var(imgui.StyleVar_.item_spacing, (2, 0))
                self._draw_status_button("ALLIED", GAMETHEME.col_positive)
                imgui.same_line()
                self._draw_status_button("RELATIONS", GAMETHEME.col_button_idle)
                imgui.same_line()
                self._draw_status_button("MORE INFO", GAMETHEME.col_button_idle)
                imgui.pop_style_var()
                
                imgui.end_group()
                imgui.end_group()

                # --- Section 2: Quick Actions ---
                imgui.same_line()
                imgui.dummy((15, 0))
                imgui.same_line()
                
                btn_sz = (40, 40)
                if imgui.button("AI", btn_sz): pass
                imgui.same_line()
                if imgui.button("STAT", btn_sz): pass
                imgui.same_line()
                if imgui.button("MSG", btn_sz): pass

                # --- Section 3: Time Control ---
                imgui.same_line()
                imgui.dummy((15, 0))
                imgui.same_line()
                self._render_time_section(state, net)

                # --- Section 4: News Ticker ---
                imgui.set_cursor_pos((10, 64)) 
                imgui.text_colored(GAMETHEME.col_text_bright, f">> {self.news_ticker_text}")
                
                imgui.same_line()
                imgui.set_cursor_pos_x(bar_w - 50)
                if imgui.button("LOG", (40, 18)): pass

                # --- Popups ---
                self._render_country_selector_popup(state)

            except Exception as e:
                # Catch errors inside the bar logic so we can still close the window safely
                print(f"[CentralBar] Error: {e}")
            finally:
                # Ensure the window is ALWAYS closed
                imgui.end()
        else:
            imgui.end()
            
        return self.active_player_tag

    def _render_time_section(self, state, net):
        # Using a group requires we match begin_group/end_group perfectly.
        # If an error happens inside, end_group might be skipped, crashing ImGui.
        # We wrap this specific logic in try/finally as well.
        imgui.begin_group()
        try:
            if imgui.button("TIME", (40, 40)):
                self.show_speed_controls = not self.show_speed_controls
                
            imgui.same_line()
            
            draw_list = imgui.get_window_draw_list()
            p = imgui.get_cursor_screen_pos()
            box_w, box_h = 130, 40
            draw_list.add_rect_filled(p, (p.x + box_w, p.y + box_h), imgui.get_color_u32((0, 0, 0, 1)))
            draw_list.add_rect(p, (p.x + box_w, p.y + box_h), imgui.get_color_u32(GAMETHEME.border))

            imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + 8)
            imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() + 5)

            if self.show_speed_controls:
                imgui.push_style_color(imgui.Col_.button, (0,0,0,0)) 
                if imgui.button("||", (20, 30)): net.send_action(ActionSetPaused("local", True))
                imgui.same_line()
                if imgui.button("T1", (20, 30)): self._set_speed(net, 1)
                imgui.same_line()
                if imgui.button("T2", (20, 30)): self._set_speed(net, 2)
                imgui.same_line()
                if imgui.button("T3", (20, 30)): self._set_speed(net, 3)
                imgui.pop_style_color()
            else:
                t = state.time
                parts = t.date_str.split(" ")
                date_part = parts[0] if len(parts) > 0 else "N/A"
                time_part = parts[1] if len(parts) > 1 else ""
                imgui.text_colored(GAMETHEME.col_positive, date_part)
                imgui.same_line()
                imgui.text_colored(GAMETHEME.col_text_bright, time_part)
        except Exception as e:
            print(f"[TimeSection] Error: {e}")
        finally:
            imgui.end_group()

    def _render_country_selector_popup(self, state):
        if imgui.begin_popup("CountrySelectorPopup"):
            try:
                imgui.text_disabled("Switch Viewpoint")
                imgui.separator()
                if "countries" in state.tables:
                    df = state.tables["countries"]
                    for row in df.head(50).iter_rows(named=True):
                        tag = row['id']
                        name = row.get('name', tag)
                        
                        if imgui.selectable(f"{tag} - {name}", False)[0]:
                            self.active_player_tag = tag
            finally:
                imgui.end_popup()

    def _set_speed(self, net, speed):
        net.send_action(ActionSetPaused("local", False))
        net.send_action(ActionSetGameSpeed("local", speed))

    def _draw_status_button(self, label, color_bg):
        imgui.push_style_color(imgui.Col_.button, color_bg)
        imgui.button(label, (60, 20))
        imgui.pop_style_color()

    def _get_flag_texture(self, tag: str) -> Optional[arcade.Texture]:
        if tag in self._flag_cache:
            return self._flag_cache[tag]

        try:
            base_path = Path(f"modules/base/assets/flags/{tag}.png")
            if not base_path.exists():
                base_path = Path("modules/base/assets/flags/XXX.png")
            
            if not base_path.exists():
                return None 
                
            texture = arcade.load_texture(str(base_path))
            self._flag_cache[tag] = texture
            return texture
        except Exception as e:
            print(f"[CentralBar] Flag Load Error: {e}")
            return None