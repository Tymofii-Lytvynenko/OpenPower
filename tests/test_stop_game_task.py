from __future__ import annotations

from queue import Queue
from types import SimpleNamespace
from unittest.mock import patch

from src.client.services.navigation_service import NavigationService
from src.client.tasks.stop_game_task import StopGameTask


class _Session:
    def __init__(self, ready: bool = True) -> None:
        self.progress_queue = Queue()
        if ready:
            self.progress_queue.put(("READY", 1.0, "Ready"))
        self.shutdown_calls = 0

    def tick(self, _delta_time: float) -> None:
        pass

    def get_state_snapshot(self):
        return object()

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def test_stop_game_replaces_campaign_session_with_clean_menu_session() -> None:
    old_session = _Session()
    new_session = _Session()
    config = object()
    created_with = []

    def factory(received_config, **kwargs):
        created_with.append((received_config, kwargs))
        return new_session

    window = SimpleNamespace(session=old_session, session_factory=factory)
    task = StopGameTask(window, config)

    result = task.run()

    assert result is new_session
    assert old_session.shutdown_calls == 1
    assert window.session is None
    assert created_with == [(config, {"save_name": None, "player_tag": None})]
    assert task.progress == 1.0


def test_navigation_returns_to_main_menu_after_stop_task_completes() -> None:
    old_session = _Session()
    config = object()
    window = SimpleNamespace(game_config=config, session=old_session, session_factory=lambda *_a, **_k: None)
    navigation = NavigationService(window)
    pending = {}
    navigation.show_loading = lambda task, on_success, on_failure=None: pending.update(
        task=task, on_success=on_success, on_failure=on_failure,
    )
    menu_view = object()

    with patch("src.client.views.main_menu_view.MainMenuView", return_value=menu_view):
        navigation.stop_game()

    replacement = _Session()
    assert isinstance(pending["task"], StopGameTask)
    assert pending["task"].config is config
    assert pending["on_success"](replacement) is menu_view
    assert window.session is replacement
