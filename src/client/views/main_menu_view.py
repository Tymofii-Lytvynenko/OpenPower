# --- File: views/main_menu_view.py ---
import arcade
import sys
from typing import TYPE_CHECKING

# Base Class
from src.client.views.base_view import BaseImGuiView

# UI Components
from src.client.services.imgui_service import ImGuiService
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME

# Type Checking (No runtime imports = No Cycles)
if TYPE_CHECKING:
    from src.shared.config import GameConfig
    from src.server.session import GameSession

class MainMenuView(BaseImGuiView):
    """
    The entry point of the game visual stack.
    Refactored to use NavigationService for decoupled transitions.
    """

    def __init__(self, session: "GameSession", config: "GameConfig"):
        super().__init__()
        self.session = session
        self.config = config
        
        # We only need to init the UI Composer. 
        # ImGuiService is handled by BaseImGuiView.
        self.ui = UIComposer(GAMETHEME)

    def on_show_view(self):
        print("[MainMenuView] Entered Main Menu")
        self.window.background_color = GAMETHEME.col_black
        
        # Ensure ImGui is set up (from BaseImGuiView)
        if not self.imgui:
            self.setup_imgui()

    def on_draw(self):
        self.clear()
        
        # BaseImGuiView doesn't automatically call new_frame/render 
        # to allow flexibility, so we do it here.
        if self.imgui:
            self.imgui.new_frame()
            self.ui.setup_frame()
            self._render_menu_window()
            self.imgui.render()

    def _render_menu_window(self):
        screen_w, screen_h = self.window.get_size()
        
        if self.ui.begin_centered_panel("Main Menu", screen_w, screen_h, w=350, h=450):
            
            self.ui.draw_title("OPENPOWER")
            
            # -- Menu Buttons (Delegated to NavigationService) --
            
            if self.ui.draw_menu_button("SINGLEPLAYER"):
                # Clean transition: No imports needed here
                self.nav.show_new_game_screen(self.session, self.config)
            
            if self.ui.draw_menu_button("LOAD GAME"):
                self.nav.show_load_game_screen(self.config)
            
            # ------------------
            
            if self.ui.draw_menu_button("MAP EDITOR"):
                self.nav.show_editor_loading(self.session, self.config)
            
            if self.ui.draw_menu_button("SETTINGS"):
                print("Settings clicked (Not Implemented)")
            
            # Spacing
            from imgui_bundle import imgui
            imgui.dummy((0, 50)) 
            
            if self.ui.draw_menu_button("EXIT TO DESKTOP"):
                arcade.exit()
                sys.exit()

            self.ui.end_panel()