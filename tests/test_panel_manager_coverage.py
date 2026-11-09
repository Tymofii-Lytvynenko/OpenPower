from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.client.ui.components.hud.panel_manager import PanelManager


@pytest.mark.parametrize("has_telemetry", [False, True])
def test_render_failure_is_logged_and_reported_when_telemetry_is_available(
    monkeypatch,
    has_telemetry: bool,
) -> None:
    recorder = Mock() if has_telemetry else None
    monkeypatch.setattr(
        "src.client.ui.core.testability.active_telemetry",
        lambda: recorder,
    )
    manager = PanelManager()
    manager.register(
        "broken",
        SimpleNamespace(render=Mock(side_effect=RuntimeError("render failed"))),
        visible=True,
    )

    manager.render_all(None, None)

    assert manager.is_visible("broken") is True
    if has_telemetry:
        assert recorder is not None
        recorder.record_error.assert_called_once()
        panel_id, traceback_text = recorder.record_error.call_args.args
        assert panel_id == "broken"
        assert "render failed" in traceback_text
    else:
        assert recorder is None


def test_get_entries_can_filter_panels_hidden_from_the_toggle_bar() -> None:
    manager = PanelManager()
    manager.register(
        "visible-toggle",
        SimpleNamespace(render=lambda *_args: True),
        show_in_toggle_bar=True,
    )
    manager.register(
        "not-in-toggle",
        SimpleNamespace(render=lambda *_args: True),
        show_in_toggle_bar=False,
    )

    assert [entry.id for entry in manager.get_entries(toggle_bar_only=True)] == [
        "visible-toggle"
    ]
