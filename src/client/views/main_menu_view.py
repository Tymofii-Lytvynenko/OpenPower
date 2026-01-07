import arcade
import sys
from src.client.services.imgui_service import ImGuiService
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.shared.config import GameConfig
from src.server.session import GameSession

# Views
from src.client.views.editor_view import EditorView
from src.client.views.game_view import GameView
from src.client.views.loading_view import LoadingView

# Tasks
from src.client.tasks.editor_loading_task import EditorLoadingTask, EditorContext

class MainMenuView(arcade.View):
    """
    The entry point of the game visual stack.
    """

    def __init__(self, session: GameSession, config: GameConfig):
        super().__init__()
        self.session = session
        self.config = config
        
        # Services
        self.imgui = ImGuiService(self.window)
        self.ui = UIComposer(GAMETHEME)

    def on_show_view(self):
        print("[MainMenuView] Entered Main Menu")
        self.window.background_color = arcade.color.BLACK

    def on_resize(self, width: int, height: int):
        self.imgui.resize(width, height)

    def on_draw(self):
        self.clear()
        
        self.imgui.new_frame(1.0 / 60.0)
        self.ui.setup_frame()
        self._render_menu_window()
        self.imgui.render()

    def _render_menu_window(self):
        screen_w, screen_h = self.window.get_size()
        
        if self.ui.begin_centered_panel("Main Menu", screen_w, screen_h, width=350, height=450):
            
            self.ui.draw_title("OPEN POWER")
            
            # -- Menu Buttons --
            if self.ui.draw_menu_button("SINGLE PLAYER"):
                game_view = GameView()
                self.window.show_view(game_view)
            
            if self.ui.draw_menu_button("MAP EDITOR"):
                self._launch_editor()
            
            if self.ui.draw_menu_button("SETTINGS"):
                print("Settings clicked (Not Implemented)")
            
            from imgui_bundle import imgui
            imgui.dummy((0, 50)) 
            
            if self.ui.draw_menu_button("EXIT TO DESKTOP"):
                arcade.exit()
                sys.exit()

            self.ui.end_panel()

    def _launch_editor(self):
        """
        Initiates the loading sequence for the editor.
        """
        # 1. Create the Task
        task = EditorLoadingTask(self.session, self.config)
        
        # 2. Define success callback
        def on_editor_loaded(context: EditorContext):
            # Pass the loaded context to the view
            return EditorView(context, self.config)
            
        # 3. Show Loading Screen
        loader = LoadingView(task, on_success=on_editor_loaded)
        self.window.show_view(loader)

    # --- Input Delegation ---
    
    def on_mouse_press(self, x, y, button, modifiers):
        self.imgui.on_mouse_press(x, y, button, modifiers)

    def on_mouse_release(self, x, y, button, modifiers):
        self.imgui.on_mouse_release(x, y, button, modifiers)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.imgui.on_mouse_drag(x, y, dx, dy, buttons, modifiers)

    def on_mouse_motion(self, x, y, dx, dy):
        self.imgui.on_mouse_motion(x, y, dx, dy)