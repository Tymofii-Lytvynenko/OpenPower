from __future__ import annotations

from queue import Queue
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

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
        self.state = None
        self.shutdown = Mock()


def _window(session_factory=None):
    window = MainWindow.__new__(MainWindow)
    window.game_config = object()
    window.session_factory = session_factory or Mock()
    window.session = None
    window.nav = Mock()
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
