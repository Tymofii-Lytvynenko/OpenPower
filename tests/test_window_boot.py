from __future__ import annotations

from pathlib import Path
from queue import Queue
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

import polars as pl

from src.client.window import MainWindow


class QueueWithoutEmpty(Queue):
    def empty(self):
        raise AssertionError("Queue.empty() is not safe for progress polling")


class FakeSession:
    def __init__(self, messages=()):
        self.progress_queue = QueueWithoutEmpty()
        for message in messages:
            self.progress_queue.put(message)
        self.tick = Mock()
        self.state = SimpleNamespace(globals={})
        self.presentation_state = SimpleNamespace(geo_language_code="en")
        self.shutdown = Mock()


def _window(session_factory=None):
    window = MainWindow.__new__(MainWindow)
    window.game_config = object()
    window.session_factory = session_factory or Mock()
    window.session = None
    window.nav = Mock()
    window.settings = SimpleNamespace(settings=SimpleNamespace(geo_language_code="en"))
    window.boot_progress = 0.0
    window.boot_status = "Preparing"
    window.boot_error = None
    window._boot_result_queue = Queue()
    window._boot_closing = Event()
    window._boot_thread = None
    return window


def test_setup_schedules_boot_progress_polling_at_sixty_hertz() -> None:
    session = FakeSession()
    factory = Mock(return_value=session)
    window = _window(factory)
    window.show_view = Mock()

    with (
        patch("src.client.views.server_boot_view.ServerBootView", return_value=object()),
        patch("src.client.window.arcade.schedule") as schedule,
    ):
        window.setup()
        window._boot_thread.join(timeout=2.0)

    schedule.assert_called_once_with(window._check_server_boot, 1 / 60)
    assert window._boot_thread is not None and not window._boot_thread.is_alive()
    factory.assert_called_once_with(window.game_config)


def test_ready_waits_for_background_snapshot_before_navigation() -> None:
    session = FakeSession([("READY", 1.0, "Ready")])
    session.state = None
    window = _window()
    window._boot_result_queue.put(("SESSION", session))
    with patch("src.client.window.arcade.unschedule"):
        window._check_server_boot(1 / 60)
        window.nav.show_main_menu.assert_not_called()
        session.state = SimpleNamespace(globals={})
        window._check_server_boot(1 / 60)
    window.nav.show_main_menu.assert_called_once_with(session, window.game_config)


def test_boot_queue_displays_progress_then_routes_on_ready_without_empty_probe() -> None:
    session = FakeSession([
        ("PROGRESS", 0.65, "Loading scenario"),
        ("READY", 1.0, "Ready"),
    ])
    window = _window()
    window._boot_result_queue.put(("SESSION", session))

    with patch("src.client.window.arcade.unschedule") as unschedule:
        window._check_server_boot(1 / 60)

        assert window.boot_progress == 0.65
        assert window.boot_status == "Loading scenario"
        session.tick.assert_not_called()
        window.nav.show_main_menu.assert_not_called()

        window._check_server_boot(1 / 60)

    assert window.boot_progress == 1.0
    assert window.boot_status == "Engine ready."
    session.tick.assert_called_once_with(0.0)
    window.nav.show_main_menu.assert_called_once_with(session, window.game_config)
    unschedule.assert_called_once_with(window._check_server_boot)


def test_each_queued_progress_message_is_rendered_before_ready() -> None:
    session = FakeSession([
        ("PROGRESS", 0.1, "Loading data"),
        ("PROGRESS", 0.6, "Starting simulation"),
        ("PROGRESS", 0.9, "Publishing snapshot"),
        ("READY", 1.0, "Ready"),
    ])
    window = _window()
    window._boot_result_queue.put(("SESSION", session))
    seen = []

    with patch("src.client.window.arcade.unschedule"):
        for _ in range(3):
            window._check_server_boot(1 / 60)
            seen.append((window.boot_progress, window.boot_status))
            window.nav.show_main_menu.assert_not_called()
        window._check_server_boot(1 / 60)

    assert seen == [
        (0.1, "Loading data"),
        (0.6, "Starting simulation"),
        (0.9, "Publishing snapshot"),
    ]
    window.nav.show_main_menu.assert_called_once_with(session, window.game_config)


def test_boot_error_is_shown_and_stops_polling() -> None:
    window = _window()
    window._boot_result_queue.put(("ERROR", RuntimeError("cannot start")))

    with patch("src.client.window.arcade.unschedule") as unschedule:
        window._check_server_boot(1 / 60)

    assert window.boot_error == "cannot start"
    assert window.boot_status == "Client proxy failed."
    unschedule.assert_called_once_with(window._check_server_boot)


def test_server_error_message_is_shown_and_child_cleanup_is_scheduled() -> None:
    session = FakeSession([("ERROR", 0.0, "server initialization failed")])
    window = _window()
    window._boot_result_queue.put(("SESSION", session))
    cleanup_thread = Mock()

    with (
        patch("src.client.window.arcade.unschedule") as unschedule,
        patch("src.client.window.threading.Thread", return_value=cleanup_thread) as thread,
    ):
        window._check_server_boot(1 / 60)

    assert window.session is None
    assert window.boot_error == "server initialization failed"
    assert window.boot_status == "Server boot failed."
    thread.assert_called_once()
    thread.call_args.kwargs["target"]()
    session.shutdown.assert_called_once_with()
    cleanup_thread.start.assert_called_once_with()
    unschedule.assert_called_once_with(window._check_server_boot)


def test_resize_forwards_to_viewport_imgui_settings_and_active_view() -> None:
    window = _window()
    ctx = SimpleNamespace(viewport=None, scissor="stale")
    window.imgui = Mock()
    window.settings = Mock()
    current_view = Mock()

    with (
        patch("arcade.Window.on_resize"),
        patch.object(MainWindow, "ctx", new_callable=PropertyMock, return_value=ctx),
        patch.object(MainWindow, "current_view", new_callable=PropertyMock, return_value=current_view),
    ):
        window.on_resize(1024, 768)

    assert ctx.viewport == (0, 0, 1024, 768)
    assert ctx.scissor is None
    window.imgui.resize.assert_called_once_with(1024, 768)
    window.settings.remember_windowed_size.assert_called_once_with(1024, 768)
    current_view.on_resize.assert_called_once_with(1024, 768)


def test_constructor_wires_services_and_optional_font_path(tmp_path: Path) -> None:
    existing_font = tmp_path / "font.ttf"
    existing_font.write_text("font", encoding="utf-8")

    for font_path in (None, tmp_path / "missing.ttf", existing_font):
        config = SimpleNamespace(
            user_data_dir=tmp_path,
            get_asset_path=Mock(return_value=font_path),
        )
        settings = Mock()
        window = MainWindow.__new__(MainWindow)

        with (
            patch("arcade.Window.__init__") as base_init,
            patch.object(MainWindow, "switch_to") as switch_to,
            patch.object(MainWindow, "set_minimum_size") as set_minimum_size,
            patch("src.client.window.GameSettingsService.from_path", return_value=settings) as from_path,
            patch("src.client.window.ImGuiService") as imgui_service,
            patch("src.client.window.NavigationService") as navigation_service,
        ):
            MainWindow.__init__(window, config, Mock())

        base_init.assert_called_once_with(1280, 720, "OpenPower Engine", resizable=True)
        switch_to.assert_called_once_with()
        set_minimum_size.assert_called_once_with(800, 600)
        from_path.assert_called_once_with(tmp_path / "settings.json")
        settings.apply_display.assert_called_once_with(window)
        expected_font_path = font_path if font_path == existing_font else None
        imgui_service.assert_called_once_with(
            window,
            font_path=expected_font_path,
            enable_implot=True,
            inspection_provider=window._inspection_snapshot,
        )
        navigation_service.assert_called_once_with(window)
        assert window.session is None
        assert window.shared_renderer is None
        assert window._boot_thread is None


def test_inspection_snapshot_handles_missing_state_and_country_rows() -> None:
    window = MainWindow.__new__(MainWindow)
    window.session = None
    view = SimpleNamespace(player_tag=None)

    with patch.object(MainWindow, "current_view", new_callable=PropertyMock, return_value=view):
        assert window._inspection_snapshot() == {"view": "SimpleNamespace", "ready": False}

        window.session = SimpleNamespace(
            state=SimpleNamespace(
                globals={"tick": 4, "player_tag": "USA"},
                tables={"countries": pl.DataFrame({"id": ["USA"], "money_reserves": [12.5]})},
                time=SimpleNamespace(
                    date_str="1936-01-01",
                    total_minutes=10,
                    is_paused=False,
                    speed_level=2,
                ),
                journal=SimpleNamespace(command_results=list(range(25))),
            ),
            system_errors=["diagnostic"],
        )
        snapshot = window._inspection_snapshot()

    assert snapshot["ready"] is True
    assert snapshot["country"] == {"id": "USA", "money_reserves": 12.5}
    assert snapshot["table_rows"] == {"countries": 1}
    assert snapshot["command_results"] == list(range(5, 25))
    assert snapshot["system_errors"] == ["diagnostic"]

    window.session.state.globals = {"tick": 1}
    window.session.state.tables = {}
    with patch.object(MainWindow, "current_view", new_callable=PropertyMock, return_value=view):
        snapshot = window._inspection_snapshot()
    assert snapshot["country"] is None


def test_geo_language_sync_ignores_missing_or_non_dict_session_state() -> None:
    window = _window()
    window.session = None
    window._sync_geo_language_to_session()

    window.session = SimpleNamespace(state=None)
    window._sync_geo_language_to_session()

    globals_object = SimpleNamespace(geo_language_code="old")
    presentation_state = SimpleNamespace(geo_language_code="en")
    window.session = SimpleNamespace(
        state=SimpleNamespace(globals=globals_object),
        presentation_state=presentation_state,
    )
    window._sync_geo_language_to_session()
    assert globals_object.geo_language_code == "old"
    assert presentation_state.geo_language_code == "en"

    globals_dict = {}
    presentation_state = SimpleNamespace(geo_language_code="en")
    window.session = SimpleNamespace(
        state=SimpleNamespace(globals=globals_dict),
        presentation_state=presentation_state,
    )
    window._sync_geo_language_to_session()
    assert globals_dict == {}
    assert presentation_state.geo_language_code == "en"


def test_boot_creation_and_polling_handle_factory_failure_closing_and_empty_queues() -> None:
    failed_window = _window(Mock(side_effect=RuntimeError("factory failed")))
    failed_window._create_boot_session()
    message_type, error = failed_window._boot_result_queue.get_nowait()
    assert message_type == "ERROR"
    assert str(error) == "factory failed"

    session = FakeSession()
    closing_window = _window(Mock(return_value=session))
    closing_window._boot_closing.set()
    closing_window._create_boot_session()
    session.shutdown.assert_called_once_with()
    assert closing_window._boot_result_queue.empty()

    window = _window()
    window._boot_closing.set()
    window._check_server_boot(1 / 60)

    window._boot_closing.clear()
    with patch("src.client.window.arcade.unschedule"):
        window._check_server_boot(1 / 60)
        window.session = FakeSession()
        window._check_server_boot(1 / 60)
    window.session.tick.assert_not_called()


def test_update_and_close_forward_to_live_session_and_imgui() -> None:
    window = _window()
    window.imgui = Mock()
    session = FakeSession()
    window.session = session

    window.on_update(0.25)
    session.tick.assert_called_once_with(0.25)
    assert session.state.globals == {}
    assert session.presentation_state.geo_language_code == "en"

    with (
        patch("src.client.window.arcade.unschedule") as unschedule,
        patch("arcade.Window.on_close") as base_close,
    ):
        window.on_close()

    assert window._boot_closing.is_set()
    unschedule.assert_called_once_with(window._check_server_boot)
    session.shutdown.assert_called_once_with()
    window.imgui.shutdown.assert_called_once_with()
    base_close.assert_called_once_with()
