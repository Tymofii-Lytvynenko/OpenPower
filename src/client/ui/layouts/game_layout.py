from imgui_bundle import imgui
from typing import Optional, Dict, Any
import polars as pl

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
        self.panels: Dict[str, Dict[str, Any]] = {
            "POL": {
                "instance": PoliticsPanel(), 
                "visible": True, 
                "icon": "POL", 
                "color": GAMETHEME.col_politics
            },
            "MIL": {
                "instance": MilitaryPanel(), 
                "visible": True, 
                "icon": "MIL", 
                "color": GAMETHEME.col_military
            },
            "ECO": {
                "instance": EconomyPanel(), 
                "visible": True, 
                "icon": "ECO", 
                "color": GAMETHEME.col_economy
            },
            "DEM": {
                "instance": DemographicsPanel(), 
                "visible": True, 
                "icon": "DEM", 
                "color": GAMETHEME.col_demographics
            },
        }

    def render(self, selected_region_id: Optional[int], fps: float):
        """Main UI Render Pass called every frame."""
        self.composer.setup_frame()
        state = self.net.get_state()

        # 1. Render Registered Panels
        # We iterate through the registry. If a panel is visible, we render it.
        for panel_id, data in self.panels.items():
            if data["visible"]:
                panel_instance = data["instance"]
                
                # Special Case: Economy Panel needs 'player_tag'
                # In a larger system, we might pass a context object to all panels.
                if panel_id in ["ECO", "DEM"]:
                    panel_instance.render(self.composer, state, self.player_tag)
                else:
                    panel_instance.render(self.composer, state)

        # 2. Render HUD Overlays (Top Bar, Bottom Bar)
        self._render_top_bar(state, fps)
        self._render_toggle_bar()
        self._render_time_controls(state)
        
        # 3. Contextual Inspector (Shows up when a region is clicked)
        # Inherited from BaseLayout
        if selected_region_id is not None:
             self.render_inspector(selected_region_id, state)

    def _render_toggle_bar(self):
        """
        Dynamically generates the buttons to show/hide panels.
        Placed at the bottom left of the screen.
        """
        screen_h = imgui.get_main_viewport().size.y
        imgui.set_next_window_pos((10, screen_h - 145)) 
        
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.always_auto_resize | 
                 imgui.WindowFlags_.no_background)

        if imgui.begin("ToggleBar", True, flags)[0]:
            
            # --- DYNAMIC PANEL TOGGLES ---
            # Automatically create a button for every panel in the registry
            for panel_id, data in self.panels.items():
                
                # Check if button was clicked
                if self.composer.draw_icon_toggle(data["icon"], data["color"], data["visible"]):
                    # Toggle visibility state
                    data["visible"] = not data["visible"]
                
                imgui.same_line()
            
            imgui.dummy((0, 8))
            imgui.separator()
            imgui.dummy((0, 2))
            
            # --- SELECTION MODE SWITCHES ---
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
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_info)
        else:
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.col_inactive_bg)
            imgui.push_style_color(imgui.Col_.text, GAMETHEME.col_text_disabled)

        if imgui.button(label, (52, 25)):
            callback()
        
        imgui.pop_style_color(2)

    def _render_top_bar(self, state, fps: float):
        """Renders the top menu bar with Player Tag, Treasury, and FPS."""
        if imgui.begin_main_menu_bar():
            # Player Identity
            imgui.text_colored(GAMETHEME.col_active_accent, f"[{self.player_tag}]")
            
            # Treasury (Read from State)
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
            
            # Map Mode Switcher
            if imgui.begin_menu("Map Mode"):
                if imgui.menu_item("Political", "", self.map_mode == "political")[0]:
                    self.map_mode = "political"
                if imgui.menu_item("Terrain", "", self.map_mode == "terrain")[0]:
                    self.map_mode = "terrain"
                imgui.end_menu()

            # FPS Counter (Far Right)
            main_vp_w = imgui.get_main_viewport().size.x
            imgui.set_cursor_pos_x(main_vp_w - 85)
            imgui.text_disabled(f"{fps:.0f} FPS")

            imgui.end_main_menu_bar()

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