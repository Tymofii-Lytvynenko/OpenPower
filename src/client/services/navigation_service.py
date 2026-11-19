import arcade
import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.shared.config import GameConfig
    from src.shared.protocols import SessionPort
    from src.client.tasks.editor_loading_task import EditorContext

class NavigationService:
    def __init__(self, window: arcade.Window):
        self.window = window

    # --- MAIN MENU & INFRASTRUCTURE ---

    def show_main_menu(self, session: "SessionPort", config: "GameConfig"):
        from src.client.views.main_menu_view import MainMenuView
        print("[Nav] Switching to Main Menu")
        self.window.show_view(MainMenuView(session, config))

    def stop_game(self):
        """Replace the active campaign session with a clean menu session."""
        from src.client.tasks.stop_game_task import StopGameTask
        from src.client.views.main_menu_view import MainMenuView

        config = self.window.game_config

        def on_success(session):
            self.window.session = session
            return MainMenuView(session, config)

        def on_failure(_error):
            # The stop task disposes its replacement session after a failed
            # transition, so the window must not retain that closed session.
            self.window.session = None

        self.show_loading(StopGameTask(self.window, config), on_success, on_failure)

    def show_loading(self, task, on_success, on_failure=None, *, on_return=None):
        from src.client.views.loading_view import LoadingView
        print("[Nav] Switching to Loading Screen")
        self.window.show_view(LoadingView(task, on_success, on_failure, on_return=on_return))

    # --- GAMEPLAY FLOW ---

    def show_new_game_screen(self, session: "SessionPort", config: "GameConfig", *, scenario: bool = False):
        from src.client.views.new_game_view import NewGameView
        print("[Nav] Switching to New Game Selection")
        self.window.show_view(NewGameView(session, config, scenario=scenario))

    def show_load_game_screen(self, config: "GameConfig"):
        from src.client.views.load_game_view import LoadGameView
        print("[Nav] Switching to Load Game Screen")
        self.window.show_view(LoadGameView(config))

    def load_saved_game(self, config: "GameConfig", save_name: str):
        from src.client.tasks.load_game_task import LoadGameTask

        previous_session = getattr(self.window, "session", None)
        previous_view = getattr(self.window, "current_view", None)

        def on_success(session):
            self.window.session = session
            try:
                state = session.get_state_snapshot()
                player_tag = str(state.globals["player_tag"]).strip().upper()
                self.show_game_view(session, config, player_tag)
            except Exception:
                # Retain the previous session if constructing the loaded view fails.
                self.window.session = previous_session
                raise
            if previous_session is not None and previous_session is not session:
                try:
                    previous_session.shutdown()
                except Exception:
                    # The new game is already active; cleanup must not invalidate it.
                    logger.exception("Could not shut down the previous session")

        def return_to_previous_view():
            self.window.show_view(previous_view)

        self.show_loading(
            LoadGameTask(self.window, config, save_name),
            on_success,
            on_return=return_to_previous_view if previous_view is not None else None,
        )

    def show_game_view(self, session: "SessionPort", config: "GameConfig", player_tag: str, initial_pos=None):
        from src.client.views.game_view import GameView
        print(f"[Nav] Starting Game as {player_tag}")
        self.window.show_view(GameView(session, config, player_tag, initial_pos))

    # --- TOOLS ---

    def show_editor_loading(self, session: "SessionPort", config: "GameConfig"):
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
