import arcade
from src.shared.config import GameConfig
from src.client.views.loading_view import LoadingView
from src.client.views.main_menu_view import MainMenuView
from src.client.tasks.startup_task import StartupTask

class MainWindow(arcade.Window):
    
    def __init__(self, config: GameConfig):
        super().__init__(1280, 720, "OpenPower Engine", resizable=True)
        self.game_config = config
        self.center_window()
        self.set_minimum_size(800, 600)
        
        # Session starts as None; populated by LoadingView later
        self.session = None 

    def setup(self):
        print("[Window] Booting...")
        
        # 1. Create the Task Object (The 'Disc')
        # This object implements the logic to load the server
        task = StartupTask(self.game_config)
        
        # 2. Define the callback (What happens when the Task finishes)
        def on_boot_complete(result_session):
            print("[Window] Engine Ready.")
            self.session = result_session
            # Switch to Main Menu with the ready session
            return MainMenuView(self.session, self.game_config)

        # 3. Create the View (The 'Player')
        # We pass the Task object, not a raw function
        loader = LoadingView(task, on_success=on_boot_complete)
        
        self.show_view(loader)
        
    def on_resize(self, width: float, height: float):
        """
        Handles window resizing events.
        
        Modification for Composition:
            We override this to ensure the active View (and its ImGui service)
            receives the resize event *synchronously*. 
            
            Without this explicit call, the OpenGL viewport might update before 
            ImGui's internal state, leading to temporary rendering artifacts 
            or 'black zones' during window maximization.
        """
        # 1. Call standard Arcade resize (handles projection matrices)
        super().on_resize(width, height)
        
        # 2. FORCE Viewport update (Safety measure against ImGui interfering)
        # Sometimes ImGui leaves the viewport in a weird state.
        self.ctx.viewport = (0, 0, width, height)
        self.ctx.scissor = None # Ensure full screen is writable
        
        # 3. Propagate to View/ImGuiService
        if self.current_view and hasattr(self.current_view, "on_resize"):
            self.current_view.on_resize(int(width), int(height))

    def on_update(self, delta_time: float):
        """Global game tick."""
        # Only tick the engine if loading is complete and session is ready.
        if self.session:
            self.session.tick(delta_time)