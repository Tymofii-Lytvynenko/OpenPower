import arcade
from typing import Optional, TYPE_CHECKING

from src.shared.config import GameConfig
from src.client.services.navigation_service import NavigationService
from src.client.tasks.startup_task import StartupTask
from src.client.services.imgui_service import ImGuiService

if TYPE_CHECKING:
    from src.server.session import GameSession
    from src.client.renderers.map_renderer import MapRenderer

class MainWindow(arcade.Window):

    def __init__(self, config: GameConfig):
        super().__init__(1280, 720, "OpenPower Engine", resizable=True)
        self.switch_to()
        self.game_config = config
        self.center_window()
        self.set_minimum_size(800, 600)

        # 1. Initialize ImGui
        font_path = config.get_asset_path("fonts/main_font.ttf")
        if not font_path or not font_path.exists():
            font_path = None
        self.imgui = ImGuiService(self, font_path=font_path)

        # 2. Services & State
        self.nav = NavigationService(self)
        self.session: Optional["GameSession"] = None
        
        # 3. SHARED RENDERER (The Fix for Freezing)
        # We load this once, and all Views use it.
        self.shared_renderer: Optional["MapRenderer"] = None

    def setup(self):
        print("[Window] Booting...")
        task = StartupTask(self.game_config)

        def on_boot_complete(result_session: "GameSession"):
            print("[Window] Engine Ready.")
            self.session = result_session
            
            # Note: We initialize the renderer lazily in the Main Menu 
            # to ensure the OpenGL context is fully ready.
            self.nav.show_main_menu(self.session, self.game_config)
            return None

        self.nav.show_loading(task, on_success=on_boot_complete)

    def on_resize(self, width: int, height: int):
        super().on_resize(width, height)
        self.ctx.viewport = (0, 0, width, height)
        self.ctx.scissor = None
        if self.current_view and hasattr(self.current_view, "on_resize"):
            self.current_view.on_resize(width, height)

    def on_update(self, delta_time: float):
        if self.session:
            self.session.tick(delta_time)