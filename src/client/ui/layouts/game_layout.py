from imgui_bundle import imgui
from typing import Optional, Dict, Any
import polars as pl

from src.server.state import GameState
from src.client.services.network_client_service import NetworkClient
from src.client.ui.layouts.base_layout import BaseLayout
from src.client.ui.theme import GAMETHEME
from src.client.controllers.viewport_controller import SelectionMode

# Panels
from src.client.ui.panels.politics_panel import PoliticsPanel
from src.client.ui.panels.military_panel import MilitaryPanel
from src.client.ui.panels.economy_panel import EconomyPanel
from src.client.ui.panels.demographics_panel import DemographicsPanel
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused
from src.client.ui.panels.data_insp_panel import DataInspectorPanel

class GameLayout(BaseLayout):
    """
    Manages the complex HUD for the actual Gameplay.
    
    Architecture:
    - Uses a Dictionary Registry ('self.panels') to manage UI modules.
    - Allows dynamic toggling of any registered panel.
    - Renders the Top Bar (Resources), Bottom Bar (Time), and Side Panels.
    """
    def __init__(self, net_client: NetworkClient, player_tag: str, viewport_ctrl):
        super().__init__(net_client, viewport_ctrl)
        
        self.player_tag = player_tag
        self.map_mode = "political"

        # --- PANEL REGISTRY ---
        # This structure defines every floating panel in the game.
        # It links the Controller (Panel Object), Visibility State, Icon, and Color.
        self.register_panel("POL", PoliticsPanel(), icon="POL", color=GAMETHEME.col_politics)
        self.register_panel("MIL", MilitaryPanel(), icon="MIL", color=GAMETHEME.col_military)
        self.register_panel("ECO", EconomyPanel(), icon="ECO", color=GAMETHEME.col_economy)
        self.register_panel("DEM", DemographicsPanel(), icon="DEM", color=GAMETHEME.col_demographics)
        
    def render(self, selected_region_id: Optional[int], fps: float, nav_service):
        """
        Main render loop. 
        Takes both selected_region_id (left click) and hovered_region_id (under mouse)
        to handle context-sensitive actions properly.
        """
        self.composer.setup_frame()
        state = self.net.get_state()

        # Context menu now relies on hovered_region_id for right-click targeting.
        self._render_context_menu()

        # Main panel rendering uses the persistent selected_region_id.
        self._render_panels(
            state, 
            player_tag=self.player_tag, 
            selected_region_id=selected_region_id,
            on_focus_request=self._on_focus_region
        )

        self._render_system_bar(state)
        self._render_toggle_bar()
        self._render_time_controls(state)

    def _render_toggle_bar(self):
        """
        Dynamic panel switcher at the bottom-left.
        Uses metadata to determine which panels get a button.
        """
        screen_h = imgui.get_main_viewport().size.y
        # Cond_.always ensures it stays fixed even if you resize the window
        imgui.set_next_window_pos((10, screen_h - 80), imgui.Cond_.always)
        
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.always_auto_resize | 
                 imgui.WindowFlags_.no_background)

        if imgui.begin("ToggleBar", True, flags)[0]:
            # Draw buttons for gameplay panels (POL, ECO, etc.)
            for panel_id, data in self.panels.items():
                if "icon" not in data:
                    continue
                
                # Check if the toggle button was clicked
                if self.composer.draw_icon_toggle(data["icon"], data["color"], data["visible"]):
                    data["visible"] = not data["visible"]
                
                imgui.same_line()
            
            imgui.dummy((0, 8))
            #imgui.separator()

        imgui.end()

    def _draw_mode_button(self, label, is_active, callback):
        """Helper for selection mode buttons."""
        if is_active:
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_active_accent)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_info)
        else:
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_inactive_bg)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_text_disabled)

        if imgui.button(label, (52, 25)):
            callback()
        
        imgui.pop_style_color(2)

    def _render_system_bar(self, nav):
        """Top-Right corner buttons."""
        vp_w = imgui.get_main_viewport().size.x
        imgui.set_next_window_pos((vp_w - 260, 10))
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.always_auto_resize |
                 imgui.WindowFlags_.no_background)

        if imgui.begin("##System_Bar", True, flags):
            # Using theme buttons
            btn_size = (70, 25)
            if imgui.button("SAVE", btn_size):
                self.net.request_save()
            imgui.same_line()
            if imgui.button("LOAD", btn_size):
                nav.show_load_game_screen(self.net.session.config)
            imgui.same_line()
            if imgui.button("MENU", btn_size):
                nav.show_main_menu(self.net.session, self.net.session.config)
        imgui.end()

    def _render_time_controls(self, state):
        """Renders the Play/Pause and Speed controls at the bottom center."""
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

        # Style specifically for this panel
        imgui.push_style_color(imgui.Col_.window_bg, GAMETHEME.col_panel_bg)
        imgui.push_style_color(imgui.Col_.border, GAMETHEME.col_border_accent)
        imgui.push_style_var(imgui.StyleVar_.window_rounding, 4.0)

        if imgui.begin("TimeControls", flags=flags):
            t = state.time

            # Date Display
            date_str = t.date_str
            text_w = imgui.calc_text_size(date_str).x
            imgui.set_cursor_pos_x((panel_w - text_w) / 2)
            imgui.text_colored(GAMETHEME.col_active_accent, date_str)
            
            imgui.dummy((0, 2)) 

            # Controls Centering
            button_w = 42
            # 6 buttons (Pause + 1x...5x) + 5 spacings
            total_buttons_w = (button_w * 6) + (imgui.get_style().item_spacing.x * 5)
            imgui.set_cursor_pos_x((panel_w - total_buttons_w) / 2)

            # Pause Button
            # Note: We send Actions to NetworkClient, adhering to Passive Observer
            self._draw_speed_button("||", is_active=t.is_paused, width=button_w, 
                                    callback=lambda: self.net.send_action(ActionSetPaused("local", True)))
            imgui.same_line()

            # Speed Buttons 1x - 5x
            for i in range(1, 6):
                is_active = (not t.is_paused) and (t.speed_level == i)
                label = f"{i}x" if i < 3 else (">" * i)
                
                # Capture 'i' in lambda closure
                def _cb(speed=i):
                    self.net.send_action(ActionSetPaused("local", False))
                    self.net.send_action(ActionSetGameSpeed("local", speed))

                self._draw_speed_button(label, is_active=is_active, width=button_w, callback=_cb)
                if i < 5: imgui.same_line()

        imgui.end()
        imgui.pop_style_var()
        imgui.pop_style_color(2)

    def _draw_speed_button(self, label: str, is_active: bool, width: float, callback):
        """Helper to style time control buttons."""
        if is_active:
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_active_accent)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.text_main)
        else:
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_button_idle)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_button_text_idle)

        if imgui.button(label, (width, 0)):
            callback()

        imgui.pop_style_color(2)