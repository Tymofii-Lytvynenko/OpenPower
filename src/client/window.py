import arcade
from typing import Optional, TYPE_CHECKING

from src.shared.config import GameConfig
from src.client.services.navigation_service import NavigationService
from src.client.services.imgui_service import ImGuiService

# UPDATED: Import the new Client Proxy instead of the heavy local session
from src.client.client_session import ClientSessionProxy

if TYPE_CHECKING:
    from src.client.renderers.map_renderer import MapRenderer

class MainWindow(arcade.Window):

    def __init__(self, config: GameConfig):
        super().__init__(1280, 720, "OpenPower Engine", resizable=True)
        self.switch_to()
        self.game_config = config
        self.center_window()
        self.set_minimum_size(800, 600)

        font_path = config.get_asset_path("fonts/main_font.ttf")
        if not font_path or not font_path.exists():
            font_path = None
        self.imgui = ImGuiService(self, font_path=font_path)

        self.nav = NavigationService(self)
        self.session: Optional[ClientSessionProxy] = None
        self.shared_renderer: Optional["MapRenderer"] = None

    def setup(self):
        print("[Window] Booting Client Proxy...")
        
        # Instantiate the Proxy (This spawns the background CPU core)
        self.session = ClientSessionProxy(self.game_config)

        def check_server_boot(delta_time):
            # Poll the progress queue from the background process
            while not self.session.progress_queue.empty():
                msg_type, progress, text = self.session.progress_queue.get_nowait()
                
                if msg_type == "PROGRESS":
                    # If you have a LoadingView, you can update its UI here
                    print(f"[Loading] {text} ({progress*100}%)")
                    
                elif msg_type == "READY":
                    print("[Window] Engine Ready! Server connected.")
                    arcade.unschedule(check_server_boot)
                    
                    # Fetch initial state
                    self.session.tick(0) 
                    self.nav.show_main_menu(self.session, self.game_config)
                    
                elif msg_type == "ERROR":
                    print(f"[Window] FATAL SERVER ERROR: {text}")
                    arcade.unschedule(check_server_boot)

        # Schedule the UI to listen for server boot progress
        arcade.schedule(check_server_boot, 1/60)
        
        # Show your visual Loading Screen while the server boots in the background
        # self.nav.show_loading_view() 

    def on_resize(self, width: int, height: int):
        super().on_resize(width, height)
        self.ctx.viewport = (0, 0, width, height)
        self.ctx.scissor = None
        if self.current_view and hasattr(self.current_view, "on_resize"):
            self.current_view.on_resize(width, height)

    def on_update(self, delta_time: float):
        if self.session:
            # Grabs the latest IPC payload (Takes < 0.001 seconds!)
            self.session.tick(delta_time)
            
    def on_close(self):
        if self.session:
            print("[Window] Shutting down Server Process...")
            self.session.shutdown()
        super().on_close()