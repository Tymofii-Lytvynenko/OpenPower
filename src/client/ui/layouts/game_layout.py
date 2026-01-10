from imgui_bundle import imgui
from typing import Optional
import polars as pl

from src.client.services.network_client_service import NetworkClient
from src.client.ui.panels.region_inspector import RegionInspectorPanel
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME

# Panels
from src.client.ui.panels.politics_panel import PoliticsPanel
from src.client.ui.panels.military_panel import MilitaryPanel
from src.client.ui.panels.economy_panel import EconomyPanel

from src.shared.actions import ActionSetGameSpeed, ActionSetPaused

class GameLayout:
    def __init__(self, net_client: NetworkClient, player_tag: str):
        self.net = net_client
        self.player_tag = player_tag
        self.composer = UIComposer(GAMETHEME)
        
        # Sub-panels
        self.inspector = RegionInspectorPanel()
        self.panel_politics = PoliticsPanel()
        self.panel_military = MilitaryPanel()
        self.panel_economy = EconomyPanel()
        
        # --- Visibility State ---
        # Defaults to True to match the screenshot "Busy UI" look
        self.show_politics = True
        self.show_military = True
        self.show_economy = True
        
        self.map_mode = "political"

    def render(self, selected_region_id: Optional[int], fps: float):
        self.composer.setup_frame()
        state = self.net.get_state()

        # 1. Render Floating Panels (If toggled on)
        if self.show_politics:
            # We assume the Panel classes use composer.begin_panel now
            self.panel_politics.render(self.composer, state)
            
        if self.show_military:
            self.panel_military.render(self.composer, state)
            
        if self.show_economy:
            self.panel_economy.render(self.composer, state, self.player_tag)

        # 2. Render UI Controls
        self._render_top_bar(state, fps)
        self._render_toggle_bar()  # <--- NEW: Bottom Left Buttons
        self._render_time_controls(state)
        
        # 3. Contextual Inspector
        if selected_region_id is not None:
             self.inspector.render(selected_region_id, state)

    def _render_toggle_bar(self):
        """
        Renders the 3 toggle buttons at the bottom left of the screen.
        """
        screen_h = imgui.get_main_viewport().size.y
        
        # Position: Bottom Left, slightly padded
        # Window height ~ 80px to fit button (50) + bar (5) + padding
        imgui.set_next_window_pos((10, screen_h - 90)) 
        
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.always_auto_resize | 
                 imgui.WindowFlags_.no_background) # Transparent bg for the buttons container

        if imgui.begin("ToggleBar", True, flags)[0]:
            
            # 1. Politics Toggle (Yellow/Gold)
            # Using simple text icons for now, replace with textures later if needed
            if self.composer.draw_icon_toggle("POL", GAMETHEME.col_politics, self.show_politics):
                self.show_politics = not self.show_politics
            
            imgui.same_line()
            
            # 2. Military Toggle (Red)
            if self.composer.draw_icon_toggle("MIL", GAMETHEME.col_military, self.show_military):
                self.show_military = not self.show_military
            
            imgui.same_line()
            
            # 3. Economy Toggle (Green)
            if self.composer.draw_icon_toggle("ECO", GAMETHEME.col_economy, self.show_economy):
                self.show_economy = not self.show_economy
                
        imgui.end()

    def _render_top_bar(self, state, fps: float):
        """
        The top status bar: Flag, Resources, Map Modes, FPS.
        """
        if imgui.begin_main_menu_bar():
            # 1. Country Info
            imgui.text_colored((0, 1, 1, 1), f"[{self.player_tag}]")
            
            # Fetch Economy Data
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
            imgui.text(f"Treasury: ${balance:,}")
            imgui.separator()
            
            # 2. Map Modes
            if imgui.begin_menu("Map Mode"):
                if imgui.menu_item("Political", "", self.map_mode == "political")[0]:
                    self.map_mode = "political"
                if imgui.menu_item("Terrain", "", self.map_mode == "terrain")[0]:
                    self.map_mode = "terrain"
                imgui.end_menu()

            # 3. FPS (Right Aligned)
            main_vp_w = imgui.get_main_viewport().size.x
            imgui.set_cursor_pos_x(main_vp_w - 80)
            imgui.text_disabled(f"{fps:.0f} FPS")

            imgui.end_main_menu_bar()

    def _render_time_controls(self, state):
        """
        Renders the- bottom center time control panel.
        """
        viewport = imgui.get_main_viewport()
        screen_w = viewport.size.x
        screen_h = viewport.size.y
        
        panel_w, panel_h = 320, 90
        pos_x = (screen_w - panel_w) / 2
        pos_y = screen_h - panel_h - 10 # 10px padding from bottom

        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((panel_w, panel_h))

        # Styling: Dark background, no title, no resize
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.no_resize |
                 imgui.WindowFlags_.no_scrollbar)

        # Style Push: Semi-transparent black background, Cyan border
        imgui.push_style_color(imgui.Col_.window_bg, (0.05, 0.05, 0.1, 0.9))
        imgui.push_style_color(imgui.Col_.border, (0, 1, 1, 0.5))
        imgui.push_style_var(imgui.StyleVar_.window_rounding, 5.0)

        if imgui.begin("TimeControls", flags=flags):
            t = state.time

            # --- Row 1: The Date Display ---
            date_str = t.date_str
            text_w = imgui.calc_text_size(date_str).x
            imgui.set_cursor_pos_x((panel_w - text_w) / 2)
            
            imgui.text_colored((0, 1, 1, 1), date_str)
            
            imgui.dummy((0, 5)) 

            # --- Row 2: Playback Controls ---
            button_w = 40
            total_buttons_w = (button_w * 6) + (imgui.get_style().item_spacing.x * 5)
            imgui.set_cursor_pos_x((panel_w - total_buttons_w) / 2)

            # 1. Pause Button
            # FIX: Passed "local" as the dummy player_id
            self._draw_speed_button("||", is_active=t.is_paused, width=button_w, 
                                    callback=lambda: self.net.send_action(ActionSetPaused("local", True)))
            imgui.same_line()

            # 2. Speed Buttons (1 to 5)
            for i in range(1, 6):
                is_active = (not t.is_paused) and (t.speed_level == i)
                label = f"{i}x" if i < 3 else (">" * i)
                
                def _cb(speed=i):
                    # FIX: Passed "local" as the dummy player_id
                    self.net.send_action(ActionSetPaused("local", False))
                    self.net.send_action(ActionSetGameSpeed("local", speed))

                self._draw_speed_button(label, is_active=is_active, width=button_w, callback=_cb)
                
                if i < 5: imgui.same_line()

        imgui.end()
        
        imgui.pop_style_var()
        imgui.pop_style_color(2)

    def _draw_speed_button(self, label: str, is_active: bool, width: float, callback):
        """
        Helper to draw a styled toggle button.
        """
        if is_active:
            imgui.push_style_color(imgui.Col_.button, (0.0, 0.6, 0.8, 1.0))
            imgui.push_style_color(imgui.Col_.text, (1.0, 1.0, 1.0, 1.0))
        else:
            imgui.push_style_color(imgui.Col_.button, (0.0, 0.2, 0.3, 0.5))
            imgui.push_style_color(imgui.Col_.text, (0.0, 0.7, 0.7, 1.0))

        if imgui.button(label, (width, 0)):
            callback()

        imgui.pop_style_color(2)