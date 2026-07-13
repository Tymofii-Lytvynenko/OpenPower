import arcade
from typing import Optional, TYPE_CHECKING

from src.shared.config import GameConfig
from src.client.services.navigation_service import NavigationService
from src.client.services.imgui_service import ImGuiService
from src.client.services.game_settings_service import GameSettingsService

# The launcher lives in the server layer and handles process spawning;
# the window only needs to call it and hold the resulting proxy.
from src.server.launcher import spawn_local_server

if TYPE_CHECKING:
    from src.client.renderers.map_renderer import MapRenderer


class MainWindow(arcade.Window):
    def __init__(self, config: GameConfig):
        super().__init__(1280, 720, "OpenPower Engine", resizable=True)
        self.switch_to()
        self.game_config = config
        self.set_minimum_size(800, 600)
        self.settings = GameSettingsService.from_path(config.user_data_dir / "settings.json")
        self.settings.apply_display(self)

        font_path = config.get_asset_path("fonts/main_font.ttf")
        if not font_path or not font_path.exists():
            font_path = None
        self.imgui = ImGuiService(self, font_path=font_path)

        self.nav = NavigationService(self)
        self.session: Optional["ClientSessionProxy"] = None
        self.shared_renderer: Optional["MapRenderer"] = None

    def _sync_geo_language_to_session(self) -> None:
        session = self.session
        if session is None or getattr(session, "state", None) is None:
            return

        globals_dict = getattr(session.state, "globals", None)
        if isinstance(globals_dict, dict):
            globals_dict["geo_language_code"] = self.settings.settings.geo_language_code

    def setup(self):
        self.boot_progress = 0.0
        self.boot_status = "Preparing client..."
        self.boot_error: Optional[str] = None

        from src.client.views.server_boot_view import ServerBootView
        self.show_view(ServerBootView(self.game_config))

        def check_server_boot(delta_time):
            if self.session is None:
                return

            # Poll the progress queue from the background process
            while not self.session.progress_queue.empty():
                msg_type, progress, text = self.session.progress_queue.get_nowait()

                if msg_type == "PROGRESS":
                    self.boot_progress = float(progress)
                    self.boot_status = text
                    print(f"[Loading] {text} ({progress*100}%)")

                elif msg_type == "READY":
                    print("[Window] Engine Ready! Server connected.")
                    arcade.unschedule(check_server_boot)
                    self.boot_progress = 1.0
                    self.boot_status = "Engine ready."

                    # Fetch initial state
                    self.session.tick(0)
                    self._sync_geo_language_to_session()
                    self.nav.show_main_menu(self.session, self.game_config)

                elif msg_type == "ERROR":
                    print(f"[Window] FATAL SERVER ERROR: {text}")
                    self.boot_error = text
                    self.boot_status = "Server boot failed."
                    arcade.unschedule(check_server_boot)

        def start_client_proxy(delta_time):
            arcade.unschedule(start_client_proxy)
            print("[Window] Booting Client Proxy...")
            self.boot_progress = 0.05
            self.boot_status = "Loading map index..."

            try:
                # spawn_local_server creates the IPC channels, boots the
                # background process, and loads map data - all in one call.
                from src.client.client_session import ClientSessionProxy
                bundle = spawn_local_server(self.game_config)
                self.session = ClientSessionProxy(
                    map_data=bundle.map_data,
                    action_queue=bundle.action_queue,
                    state_queue=bundle.state_queue,
                    progress_queue=bundle.progress_queue,
                    snapshot_ack_queue=bundle.snapshot_ack_queue,
                    process=bundle.process,
                )
            except Exception as exc:
                self.boot_error = str(exc)
                self.boot_status = "Client proxy failed."
                return

            arcade.schedule(check_server_boot, 1 / 60)

        # Delay one frame so the boot screen paints before any blocking setup work.
        arcade.schedule(start_client_proxy, 0.1)

    def on_resize(self, width: int, height: int):
        super().on_resize(width, height)
        self.ctx.viewport = (0, 0, width, height)
        self.ctx.scissor = None
        if hasattr(self, "imgui"):
            self.imgui.resize(width, height)
        if hasattr(self, "settings"):
            self.settings.remember_windowed_size(width, height)
        if self.current_view and hasattr(self.current_view, "on_resize"):
            self.current_view.on_resize(width, height)

    def on_update(self, delta_time: float):
        if self.session:
            # Grabs the latest IPC payload (Takes < 0.001 seconds!)
            self.session.tick(delta_time)
            self._sync_geo_language_to_session()

    def on_close(self):
        if self.session:
            print("[Window] Shutting down Server Process...")
            self.session.shutdown()
        super().on_close()
