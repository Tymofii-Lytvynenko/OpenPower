from __future__ import annotations

from unittest.mock import Mock

import arcade

from src.client.ui.layouts.game_layout import GameLayout


def test_game_menu_defers_window_close_until_after_the_draw_frame(monkeypatch) -> None:
    layout = GameLayout.__new__(GameLayout)
    window = Mock()
    layout._window = window
    scheduled: list[tuple[object, float]] = []

    monkeypatch.setattr(
        arcade,
        "schedule_once",
        lambda callback, delay: scheduled.append((callback, delay)),
    )

    layout._request_window_close()

    window.close.assert_not_called()
    assert len(scheduled) == 1
    callback, delay = scheduled[0]
    assert delay > 0
    callback(delay)
    window.close.assert_called_once_with()
