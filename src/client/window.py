import arcade
import threading
from queue import Empty, Queue
from typing import Optional, TYPE_CHECKING

from src.shared.config import GameConfig
from src.client.services.navigation_service import NavigationService
from src.client.services.imgui_service import ImGuiService
from src.client.services.game_settings_service import GameSettingsService
from src.client.interfaces.session_factory import ClientSessionPort, SessionFactory

if TYPE_CHECKING:
    from src.client.renderers.map_renderer import MapRenderer


class MainWindow(arcade.Window):
    def __init__(self, config: GameConfig, session_factory: SessionFactory):
        super().__init__(1280, 720, "OpenPower Engine", resizable=True)
        self.switch_to()
        self.game_config = config
        self.set_minimum_size(800, 600)
        self.settings = GameSettingsService.from_path(config.user_data_dir / "settings.json")
        self.settings.apply_display(self)
        self.session_factory = session_factory

        font_path = config.get_asset_path("fonts/main_font.ttf")
        if not font_path or not font_path.exists():
            font_path = None
        self.imgui = ImGuiService(self, font_path=font_path, enable_implot=True)

        self.nav = NavigationService(self)
        self.session: Optional[ClientSessionPort] = None
        self.shared_renderer: Optional["MapRenderer"] = None
        self._boot_result_queue: Queue[tuple[str, object]] = Queue()
        self._boot_closing = threading.Event()
        self._boot_thread: threading.Thread | None = None

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
        self.boot_progress = 0.05
        self.boot_status = "Loading map index..."
        arcade.schedule(self._check_server_boot, 1 / 60)
        self._boot_thread = threading.Thread(
            target=self._create_boot_session,
            name="openpower-session-startup",
            daemon=True,
        )
        self._boot_thread.start()

    def _create_boot_session(self) -> None:
        try:
            session = self.session_factory(self.game_config)
        except Exception as exc:
            self._boot_result_queue.put(("ERROR", exc))
            return

        if self._boot_closing.is_set():
            session.shutdown()
            return
        self._boot_result_queue.put(("SESSION", session))

    def _check_server_boot(self, _delta_time: float) -> None:
        if self._boot_closing.is_set():
            return

        if self.session is None:
            try:
                result_type, result = self._boot_result_queue.get_nowait()
            except Empty:
                return
            if result_type == "ERROR":
                self.boot_error = str(result)
                self.boot_status = "Client proxy failed."
                arcade.unschedule(self._check_server_boot)
                return
            self.session = result  # type: ignore[assignment]

        try:
            msg_type, progress, text = self.session.progress_queue.get_nowait()
        except Empty:
            return

        if msg_type == "PROGRESS":
            self.boot_progress = float(progress)
            self.boot_status = str(text)
        elif msg_type == "READY":
            arcade.unschedule(self._check_server_boot)
            self.boot_progress = 1.0
            self.boot_status = "Engine ready."
            self.session.tick(0.0)
            self._sync_geo_language_to_session()
            self.nav.show_main_menu(self.session, self.game_config)
        elif msg_type == "ERROR":
            failed_session, self.session = self.session, None
            self.boot_error = str(text)
            self.boot_status = "Server boot failed."
            arcade.unschedule(self._check_server_boot)
            threading.Thread(target=failed_session.shutdown, daemon=True).start()

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
        self._boot_closing.set()
        arcade.unschedule(self._check_server_boot)
        if self.session:
            print("[Window] Shutting down Server Process...")
            self.session.shutdown()
        self.imgui.shutdown()
        super().on_close()
