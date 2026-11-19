import threading
from collections.abc import Mapping
from queue import Empty, Queue
from time import monotonic
from typing import TYPE_CHECKING, Optional

import arcade

from src.client.interfaces.session_factory import ClientSessionPort, SessionFactory
from src.client.services.game_settings_service import GameSettingsService
from src.client.services.imgui_service import ImGuiService
from src.client.services.navigation_service import NavigationService
from src.client.tasks.session_startup import (
    INITIAL_STATE_TIMEOUT_SECONDS,
    SERVER_READY_TIMEOUT_SECONDS,
    shutdown_session,
)
from src.shared.config import GameConfig

if TYPE_CHECKING:
    from src.client.renderers.map_renderer import MapRenderer


def _inspection_value(value):
    # Snapshot mappings are read-only proxies and must be converted before JSON export.
    if isinstance(value, Mapping):
        return {key: _inspection_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_inspection_value(item) for item in value]
    return value


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
        self.imgui = ImGuiService(self, font_path=font_path, enable_implot=True, inspection_provider=self._inspection_snapshot)

        self.nav = NavigationService(self)
        self.session: Optional[ClientSessionPort] = None
        self.shared_renderer: Optional["MapRenderer"] = None
        self._boot_result_queue: Queue[tuple[str, object]] = Queue()
        self._boot_closing = threading.Event()
        self._boot_thread: threading.Thread | None = None

    def _inspection_snapshot(self) -> dict:
        """Expose small authoritative observations only for opt-in UI inspection."""
        session = self.session
        state = getattr(session, "state", None)
        if state is None:
            return {"view": type(self.current_view).__name__, "ready": False}
        tag = getattr(self.current_view, "player_tag", None) or state.globals.get("player_tag")
        country = None
        countries = state.tables.get("countries")
        if tag and countries is not None:
            import polars as pl
            fields = [name for name in ("id", "money_reserves", "personal_income_tax_rate", "budget_infra_ratio") if name in countries.columns]
            rows = countries.select(fields).filter(pl.col("id") == tag).to_dicts()
            country = rows[0] if rows else None
        return {"view": type(self.current_view).__name__, "ready": True,
                "tick": int(state.globals.get("tick", 0)), "date": state.time.date_str,
                "total_minutes": state.time.total_minutes, "paused": state.time.is_paused,
                "speed": state.time.speed_level, "country": country,
                "table_rows": {name: frame.height for name, frame in state.tables.items()},
                "command_results": _inspection_value(state.journal.command_results[-20:]),
                "system_errors": list(getattr(session, "system_errors", []))}

    def _sync_geo_language_to_session(self) -> None:
        session = self.session
        if session is None:
            return

        presentation_state = getattr(session, "presentation_state", None)
        if presentation_state is not None:
            presentation_state.geo_language_code = (
                self.settings.settings.geo_language_code
            )

    def setup(self):
        if self._boot_thread is not None and self._boot_thread.is_alive():
            return
        previous_session, self.session = self.session, None
        arcade.unschedule(self._check_server_boot)
        self._boot_ready_received = False
        self._boot_deadline = None
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
            args=(previous_session,),
            name="openpower-session-startup",
            daemon=True,
        )
        self._boot_thread.start()

    def _create_boot_session(self, previous_session: ClientSessionPort | None = None) -> None:
        # The boot poller must only read messages from the replacement session.
        shutdown_session(previous_session)
        if self._boot_closing.is_set():
            return
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
            self._boot_deadline = monotonic() + SERVER_READY_TIMEOUT_SECONDS

        if getattr(self, "_boot_ready_received", False):
            msg_type, progress, text = "READY", 1.0, "Ready"
        else:
            try:
                msg_type, progress, text = self.session.progress_queue.get_nowait()
            except Empty:
                self._check_boot_stall("Timed out waiting for the simulation server to become ready.")
                return

        if msg_type == "PROGRESS":
            self.boot_progress = float(progress)
            self.boot_status = str(text)
        elif msg_type == "READY":
            if not getattr(self, "_boot_ready_received", False):
                self._boot_deadline = monotonic() + INITIAL_STATE_TIMEOUT_SECONDS
            self._boot_ready_received = True
            self.session.tick(0.0)
            # Progress and snapshots use different queues. Background decoding
            # can finish after READY; navigation needs the first usable world.
            if getattr(self.session, "state", None) is None:
                self.boot_status = "Synchronizing game state..."
                self._check_boot_stall("Timed out waiting for the initial game state.")
                return
            arcade.unschedule(self._check_server_boot)
            self.boot_progress = 1.0
            self.boot_status = "Engine ready."
            self._sync_geo_language_to_session()
            self.nav.show_main_menu(self.session, self.game_config)
        elif msg_type == "ERROR":
            self._fail_server_boot(str(text))

    def _check_boot_stall(self, timeout_message: str) -> None:
        process = getattr(self.session, "process", None)
        exit_code = getattr(process, "exitcode", None)
        if isinstance(exit_code, int):
            self._fail_server_boot(f"The simulation server stopped during startup (exit code {exit_code}).")
        elif (deadline := getattr(self, "_boot_deadline", None)) is not None and monotonic() >= deadline:
            self._fail_server_boot(timeout_message)

    def _fail_server_boot(self, message: str) -> None:
        failed_session, self.session = self.session, None
        self.boot_error = message
        self.boot_status = "Server boot failed."
        arcade.unschedule(self._check_server_boot)
        if failed_session is not None:
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
            telemetry = getattr(self.session, "telemetry", None)
            if telemetry and telemetry.collector.enabled:
                with telemetry.collector.measure("client.update_ms"):
                    self.session.tick(delta_time)
                    self._sync_geo_language_to_session()
            else:
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
