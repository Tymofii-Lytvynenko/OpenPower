import arcade
import polars as pl
from pathlib import Path
from typing import Optional, Dict
from imgui_bundle import imgui

# --- Internal Services & Theme ---
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.client.services.network_client_service import NetworkClient
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused

# --- Panel Imports ---
from src.client.ui.layouts.base_layout import BaseLayout
from src.client.ui.panels.politics_panel import PoliticsPanel
from src.client.ui.panels.military_panel import MilitaryPanel
from src.client.ui.panels.economy_panel import EconomyPanel
from src.client.ui.panels.demographics_panel import DemographicsPanel
from src.client.ui.panels.data_insp_panel import DataInspectorPanel

class GameLayout(BaseLayout):
    """
    The primary HUD for the Gameplay View.
    """

    def __init__(self, net_client: NetworkClient, player_tag: str, viewport_ctrl):
        super().__init__(net_client, viewport_ctrl)
        
        self.player_tag = player_tag
        self.map_mode = "political"

        # --- Panel Registry ---
        self.register_panel("POL", PoliticsPanel(), icon="POL", color=GAMETHEME.col_politics, visible=False)
        self.register_panel("MIL", MilitaryPanel(), icon="MIL", color=GAMETHEME.col_military, visible=False)
        self.register_panel("ECO", EconomyPanel(), icon="ECO", color=GAMETHEME.col_economy, visible=False)
        self.register_panel("DEM", DemographicsPanel(), icon="DEM", color=GAMETHEME.col_demographics, visible=False)

        # Debug tool
        self.register_panel("DATA_INSPECTOR", DataInspectorPanel(), visible=False)

        # --- Central Bar State ---
        self.show_speed_controls = False
        self.news_ticker_text = "Welcome to OpenPower. Global news will appear here..."
        
        # --- Asset Caching ---
        self._flag_cache: Dict[str, arcade.Texture] = {}

    def render(self, selected_region_id: Optional[int], fps: float, nav_service):
        """
        Main UI Render Loop.
        """
        self.composer.setup_frame()
        state = self.net.get_state()

        # 1. Global Overlays
        self._render_fps_counter(fps)
        self._render_system_bar(nav_service)
        self._render_context_menu()

        # 2. Interactive Panels
        self._render_panels(
            state, 
            player_tag=self.player_tag, 
            selected_region_id=selected_region_id,
            on_focus_request=self._on_focus_region
        )

        # 3. Main HUD (Bottom)
        self._render_central_bar(state)
        
        # 4. Side Toggles
        self._render_toggle_bar()

    def _render_central_bar(self, state):
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
                
                # 1. Get Texture Object (Cached)
                flag_tex = self._get_flag_texture(self.player_tag)
                
                # 2. Draw via Composer (Safe)
                self.composer.draw_image(flag_tex, 80, 50)
                
                imgui.same_line()
                
                imgui.begin_group()
                if imgui.button(f" {self.player_tag} ", (180, 24)):
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
                self._render_time_section(state)

                # --- Section 4: News Ticker ---
                imgui.set_cursor_pos((10, 64)) 
                imgui.text_colored(GAMETHEME.col_text_bright, f">> {self.news_ticker_text}")
                
                imgui.same_line()
                imgui.set_cursor_pos_x(bar_w - 50)
                if imgui.button("LOG", (40, 18)):
                    pass

                # --- Popups ---
                self._render_country_selector_popup(state)

            except Exception as e:
                # Catch logic errors (e.g. data lookup fail) but keep app running
                print(f"[UI] Central Bar Logic Error: {e}")

            finally:
                # Ensure the stack is balanced
                imgui.end()
        else:
            imgui.end()

    def _render_time_section(self, state):
        imgui.begin_group()
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
            if imgui.button("||", (20, 30)): self.net.send_action(ActionSetPaused("local", True))
            imgui.same_line()
            if imgui.button(">", (20, 30)): self._set_speed(1)
            imgui.same_line()
            if imgui.button(">>", (20, 30)): self._set_speed(3)
            imgui.same_line()
            if imgui.button(">>>", (20, 30)): self._set_speed(5)
            imgui.pop_style_color()
        else:
            t = state.time
            parts = t.date_str.split(" ")
            date_part = parts[0] if len(parts) > 0 else "N/A"
            time_part = parts[1] if len(parts) > 1 else ""
            imgui.text_colored(GAMETHEME.col_positive, date_part)
            imgui.same_line()
            imgui.text_colored(GAMETHEME.col_text_bright, time_part)

        imgui.end_group()

    def _render_system_bar(self, nav):
        vp_w = imgui.get_main_viewport().size.x
        imgui.set_next_window_pos((vp_w - 260, 10))
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.always_auto_resize |
                 imgui.WindowFlags_.no_background)

        if imgui.begin("##System_Bar", True, flags):
            try:
                btn_size = (70, 25)
                if imgui.button("SAVE", btn_size):
                    self.net.request_save()
                imgui.same_line()
                if imgui.button("LOAD", btn_size):
                    if hasattr(self.net, 'session'):
                        nav.show_load_game_screen(self.net.session.config)
                imgui.same_line()
                if imgui.button("MENU", btn_size):
                    if hasattr(self.net, 'session'):
                        nav.show_main_menu(self.net.session, self.net.session.config)
            except Exception as e:
                print(f"[UI] System Bar Error: {e}")
            finally:
                imgui.end()
        else:
            imgui.end()

    def _render_toggle_bar(self):
        screen_h = imgui.get_main_viewport().size.y
        
        # Position: Bottom-Left
        imgui.set_next_window_pos((10, screen_h - 70))
        
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.always_auto_resize | 
                 imgui.WindowFlags_.no_background)

        if imgui.begin("ToggleBar", True, flags):
            # 1. Filter icons
            icon_panels = [(pid, d) for pid, d in self.panels.items() if "icon" in d]
            
            for i, (panel_id, data) in enumerate(icon_panels):
                # 2. THE FIX: Call SameLine BEFORE drawing the button
                # This ensures Button[i] appears next to Button[i-1]
                if i > 0:
                    imgui.same_line(0, 10) # 0 offset, 10px spacing
                
                # 3. Draw Button
                if self.composer.draw_icon_toggle(data["icon"], data["color"], data["visible"]):
                    data["visible"] = not data["visible"]

        imgui.end()

    def _set_speed(self, speed):
        self.net.send_action(ActionSetPaused("local", False))
        self.net.send_action(ActionSetGameSpeed("local", speed))

    def _draw_status_button(self, label, color_bg):
        imgui.push_style_color(imgui.Col_.button, color_bg)
        imgui.button(label, (60, 20))
        imgui.pop_style_color()

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
                            self.player_tag = tag
            except Exception as e:
                print(f"[UI] Selector Error: {e}")
            finally:
                imgui.end_popup()

    def _get_flag_texture(self, tag: str) -> arcade.Texture:
        """
        Loads and returns the Arcade Texture for a country flag.
        Handles caching and disk I/O.
        """
        # 1. Check Cache
        if tag in self._flag_cache:
            return self._flag_cache[tag]

        # 2. Attempt Load
        try:
            base_path = Path(f"modules/base/assets/flags/{tag}.png")
            if not base_path.exists():
                base_path = Path("modules/base/assets/flags/XXX.png")
            
            if not base_path.exists():
                # Return None so the composer can draw a dummy box
                return None # type: ignore
                
            texture = arcade.load_texture(str(base_path))
            self._flag_cache[tag] = texture
            
            return texture

        except Exception as e:
            print(f"[GameLayout] Flag Load Error ({tag}): {e}")
            return None # type: ignore