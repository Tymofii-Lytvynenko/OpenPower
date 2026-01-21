import arcade 
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.shared.config import GameConfig
    from src.server.session import GameSession
    from src.client.tasks.editor_loading_task import EditorContext

class NavigationService:
    def __init__(self, window: arcade.Window):
        self.window = window

    # --- MAIN MENU & INFRASTRUCTURE ---

    def show_main_menu(self, session: "GameSession", config: "GameConfig"):
        from src.client.views.main_menu_view import MainMenuView
        print("[Nav] Switching to Main Menu")
        self.window.show_view(MainMenuView(session, config))

    def show_loading(self, task, on_success, on_failure=None):
        from src.client.views.loading_view import LoadingView
        print("[Nav] Switching to Loading Screen")
        self.window.show_view(LoadingView(task, on_success, on_failure))

    # --- GAMEPLAY FLOW ---

    def show_new_game_screen(self, session: "GameSession", config: "GameConfig"):
        from src.client.views.new_game_view import NewGameView
        print("[Nav] Switching to New Game Selection")
        self.window.show_view(NewGameView(session, config))

    def show_load_game_screen(self, config: "GameConfig"):
        from src.client.views.load_game_view import LoadGameView
        print("[Nav] Switching to Load Game Screen")
        self.window.show_view(LoadGameView(config))

    def show_game_view(self, session: "GameSession", config: "GameConfig", player_tag: str, initial_pos=None):
        from src.client.views.game_view import GameView
        print(f"[Nav] Starting Game as {player_tag}")
        self.window.show_view(GameView(session, config, player_tag, initial_pos))

    # --- TOOLS ---

    def show_editor_loading(self, session: "GameSession", config: "GameConfig"):
        """
        Handles the complex sequence of Loading Task -> Editor View
        """
        from src.client.tasks.editor_loading_task import EditorLoadingTask
        from src.client.views.editor_view import EditorView
        
        # 1. Create Task
        task = EditorLoadingTask(session, config)
        
        # 2. Define what happens when loading finishes
        def on_editor_ready(context: "EditorContext"):
            return EditorView(context, config)

        # 3. Transition to Loading View
        self.show_loading(task, on_success=on_editor_ready)