import arcade
from typing import Optional, TYPE_CHECKING

from src.shared.config import GameConfig
from src.client.services.navigation_service import NavigationService
from src.client.tasks.startup_task import StartupTask

if TYPE_CHECKING:
    from src.server.session import GameSession

class MainWindow(arcade.Window):
    
    def __init__(self, config: GameConfig):
        super().__init__(1280, 720, "OpenPower Engine", resizable=True)
        self.game_config = config
        self.center_window()
        self.set_minimum_size(800, 600)
        
        # 1. Initialize Navigation Service
        # This is the "Router" that handles all view switching
        self.nav = NavigationService(self)
        
        # Session starts as None; populated by StartupTask later
        self.session: Optional["GameSession"] = None 

    def setup(self):
        """
        Called by main.py to kick off the application lifecycle.
        """
        print("[Window] Booting...")
        
        # 1. Create the Task (The 'Disc')
        task = StartupTask(self.game_config)
        
        # 2. Define the callback (The 'next step')
        def on_boot_complete(result_session: "GameSession"):
            print("[Window] Engine Ready.")
            self.session = result_session
            
            # USE ROUTER: Switch to Main Menu
            # The window doesn't need to know what 'MainMenuView' is.
            self.nav.show_main_menu(self.session, self.game_config)
            
            # The callback must return a View for the LoadingView to switch to,
            # but since we switched explicitly above, we can return None 
            # or refactor NavigationService.show_loading to not auto-switch if we handle it.
            # Ideally, NavigationService handles the switch.
            return None 

        # 3. USE ROUTER: Start the Loading Screen
        # We modify show_loading slightly in service to handle the callback logic,
        # or we just let the loading view drive.
        # For this implementation, we simply pass the data to the service.
        self.nav.show_loading(task, on_success=on_boot_complete)
        
    def on_resize(self, width: int, height: int):
        """
        Handles window resizing events.
        """
        super().on_resize(width, height)
        
        # Force Viewport update (Safety measure against ImGui interfering)
        self.ctx.viewport = (0, 0, width, height)
        self.ctx.scissor = None 
        
        # Propagate to View/ImGuiService
        if self.current_view and hasattr(self.current_view, "on_resize"):
            self.current_view.on_resize(width, height)

    def on_update(self, delta_time: float):
        """Global game tick."""
        if self.session:
            self.session.tick(delta_time)