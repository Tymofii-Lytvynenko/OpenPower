import arcade
from src.server.session import GameSession
from src.shared.config import GameConfig
from src.client.views.editor_view import EditorView

class MainWindow(arcade.Window):
    """
    The main application window container.
    
    It serves as the top-level lifecycle manager but delegates specific logic
    to Views (EditorView, GameView).
    """
    
    def __init__(self, session: GameSession, config: GameConfig):
        # Initialize standard Arcade window
        super().__init__(1280, 720, "OpenPower Editor", resizable=True)
        self.session = session
        self.game_config = config
        self.center_window()
        
        # Set a minimum size to prevent layout crashes in ImGui/Arcade on
        # extremely small window resizes (e.g., < 100px).
        self.set_minimum_size(800, 600)

    def setup(self):
        print("[Window] Initializing...")
        start_view = EditorView(self.session, self.game_config)
        self.show_view(start_view)
        
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
        self.session.tick(delta_time)