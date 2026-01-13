from imgui_bundle import imgui
from typing import Optional
import polars as pl

from src.client.services.network_client_service import NetworkClient
from src.client.ui.layouts.base_layout import BaseLayout
from src.client.ui.theme import GAMETHEME
from src.client.controllers.viewport_controller import SelectionMode

# Panels
from src.client.ui.panels.politics_panel import PoliticsPanel
from src.client.ui.panels.military_panel import MilitaryPanel
from src.client.ui.panels.economy_panel import EconomyPanel
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused

class GameLayout(BaseLayout):
    def __init__(self, net_client: NetworkClient, player_tag: str, viewport_ctrl):
        super().__init__(net_client, viewport_ctrl)
        
        self.player_tag = player_tag
        
        # Sub-panels (Inspector is already in BaseLayout)
        self.panel_politics = PoliticsPanel()
        self.panel_military = MilitaryPanel()
        self.panel_economy = EconomyPanel()
        
        # Visibility State
        self.show_politics = True
        self.show_military = True
        self.show_economy = True
        
        self.map_mode = "political"

    def render(self, selected_region_id: Optional[int], fps: float):
        """Main UI Render Pass called every frame."""
        self.composer.setup_frame()
        state = self.net.get_state()

        # 1. Render Floating Data Panels
        if self.show_politics:
            self.panel_politics.render(self.composer, state)
            
        if self.show_military:
            self.panel_military.render(self.composer, state)
            
        if self.show_economy:
            self.panel_economy.render(self.composer, state, self.player_tag)

        # 2. Render HUD Overlays
        self._render_top_bar(state, fps)
        self._render_toggle_bar()
        self._render_time_controls(state)
        
        # 3. Contextual Inspector (Shows up when a region is clicked)
        # Use shared method from BaseLayout
        if selected_region_id is not None:
             self.render_inspector(selected_region_id, state)

    def _render_toggle_bar(self):
        screen_h = imgui.get_main_viewport().size.y
        imgui.set_next_window_pos((10, screen_h - 145)) 
        
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.always_auto_resize | 
                 imgui.WindowFlags_.no_background)

        if imgui.begin("ToggleBar", True, flags)[0]:
            # --- PANEL TOGGLES ---
            if self.composer.draw_icon_toggle("POL", GAMETHEME.col_politics, self.show_politics):
                self.show_politics = not self.show_politics
            imgui.same_line()
            
            if self.composer.draw_icon_toggle("MIL", GAMETHEME.col_military, self.show_military):
                self.show_military = not self.show_military
            imgui.same_line()
            
            if self.composer.draw_icon_toggle("ECO", GAMETHEME.col_economy, self.show_economy):
                self.show_economy = not self.show_economy
            
            imgui.dummy((0, 8))
            imgui.separator()
            imgui.dummy((0, 2))
            
            # --- SELECTION MODES ---
            imgui.text_disabled("SELECT MODE")
            
            # Region Mode Button
            is_reg = self.viewport_ctrl.selection_mode == SelectionMode.REGION
            self._draw_mode_button("REG", is_reg, lambda: self.viewport_ctrl.set_selection_mode(SelectionMode.REGION))
            imgui.same_line()

            # Country Mode Button
            is_ctry = self.viewport_ctrl.selection_mode == SelectionMode.COUNTRY
            self._draw_mode_button("CTRY", is_ctry, lambda: self.viewport_ctrl.set_selection_mode(SelectionMode.COUNTRY))

        imgui.end()

    def _draw_mode_button(self, label, is_active, callback):
        """Helper for selection mode buttons."""
        if is_active:
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_active_accent)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_text_bright)
        else:
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_inactive_bg)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_text_disabled)

        if imgui.button(label, (52, 25)):
            callback()
        
        imgui.pop_style_color(2)

    def _render_top_bar(self, state, fps: float):
        if imgui.begin_main_menu_bar():
            imgui.text_colored(GAMETHEME.col_accent_main, f"[{self.player_tag}]")
            
            balance = 0
            try:
                if "countries" in state.tables:
                    df = state.tables["countries"]
                    res = df.filter(pl.col("id") == self.player_tag).select("money_balance")
                    if not res.is_empty():
                        balance = res.item(0, 0)
            except Exception:
                pass

            imgui.separator()
            imgui.text(f"Treasury: ${balance:,.0f}".replace(",", " "))
            imgui.separator()
            
            if imgui.begin_menu("Map Mode"):
                if imgui.menu_item("Political", "", self.map_mode == "political")[0]:
                    self.map_mode = "political"
                if imgui.menu_item("Terrain", "", self.map_mode == "terrain")[0]:
                    self.map_mode = "terrain"
                imgui.end_menu()

            main_vp_w = imgui.get_main_viewport().size.x
            imgui.set_cursor_pos_x(main_vp_w - 85)
            imgui.text_disabled(f"{fps:.0f} FPS")

            imgui.end_main_menu_bar()

    def _render_time_controls(self, state):
        viewport = imgui.get_main_viewport()
        screen_w = viewport.size.x
        screen_h = viewport.size.y
        
        panel_w, panel_h = 320, 85
        pos_x = (screen_w - panel_w) / 2
        pos_y = screen_h - panel_h - 10

        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((panel_w, panel_h))

        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.no_resize |
                 imgui.WindowFlags_.no_scrollbar)

        imgui.push_style_color(imgui.Col_.window_bg, GAMETHEME.col_panel_bg)
        imgui.push_style_color(imgui.Col_.border, GAMETHEME.col_border_accent)
        imgui.push_style_var(imgui.StyleVar_.window_rounding, 4.0)

        if imgui.begin("TimeControls", flags=flags):
            t = state.time

            date_str = t.date_str
            text_w = imgui.calc_text_size(date_str).x
            imgui.set_cursor_pos_x((panel_w - text_w) / 2)
            imgui.text_colored(GAMETHEME.col_accent_main, date_str)
            
            imgui.dummy((0, 2)) 

            button_w = 42
            total_buttons_w = (button_w * 6) + (imgui.get_style().item_spacing.x * 5)
            imgui.set_cursor_pos_x((panel_w - total_buttons_w) / 2)

            self._draw_speed_button("||", is_active=t.is_paused, width=button_w, 
                                    callback=lambda: self.net.send_action(ActionSetPaused("local", True)))
            imgui.same_line()

            for i in range(1, 6):
                is_active = (not t.is_paused) and (t.speed_level == i)
                label = f"{i}x" if i < 3 else (">" * i)
                
                def _cb(speed=i):
                    self.net.send_action(ActionSetPaused("local", False))
                    self.net.send_action(ActionSetGameSpeed("local", speed))

                self._draw_speed_button(label, is_active=is_active, width=button_w, callback=_cb)
                if i < 5: imgui.same_line()

        imgui.end()
        imgui.pop_style_var()
        imgui.pop_style_color(2)

    def _draw_speed_button(self, label: str, is_active: bool, width: float, callback):
        if is_active:
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_active_accent)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_text_bright)
        else:
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_button_idle)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_button_text_idle)

        if imgui.button(label, (width, 0)):
            callback()

        imgui.pop_style_color(2)