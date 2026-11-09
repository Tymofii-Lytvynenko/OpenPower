from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock
from uuid import UUID
import json
import os
import sys

import pytest

from src.client.ui.testing import live_smoke


SMOKE_PREFIX = "00000000-0000-0000-0000-000000000123"


class FakeWindow:
    def __init__(self) -> None:
        self.switch_to = Mock()
        self.dispatch_events = Mock()
        self.clear = Mock()
        self.flip = Mock()
        self.close = Mock()
        self.push_handlers = Mock()


def install_live_smoke_runtime(
    monkeypatch,
    *,
    all_commands_pass: bool = True,
    region: dict | None = None,
    window_error: Exception | None = None,
):
    windows: list[FakeWindow] = []
    services = []
    results = [
        {"id": f"{SMOKE_PREFIX}.toggle", "passed": all_commands_pass},
        {"id": f"{SMOKE_PREFIX}.name", "passed": all_commands_pass},
        {"id": f"{SMOKE_PREFIX}.move", "passed": all_commands_pass},
    ]

    def create_window(*_args, **_kwargs):
        if window_error is not None:
            raise window_error
        window = FakeWindow()
        windows.append(window)
        return window

    arcade_module = ModuleType("arcade")
    arcade_module.Window = create_window

    class FakeImGuiService:
        def __init__(self, window) -> None:
            self.window = window
            self.new_frame = Mock()
            self.render = Mock()
            self.shutdown = Mock()
            self.on_mouse_motion = Mock()
            self.on_mouse_press = Mock()
            self.on_mouse_drag = Mock()
            self.on_mouse_release = Mock()
            self._ui_bridge = SimpleNamespace(
                interval=1,
                results=results,
                telemetry=SimpleNamespace(region=lambda _panel_id: region),
            )
            services.append(self)

    service_module = ModuleType("src.client.services.imgui_service")
    service_module.ImGuiService = FakeImGuiService

    class FakeWindowManager:
        _placements = {}
        begin_frame = Mock()

        @staticmethod
        @contextmanager
        def window(*_args, **_kwargs):
            yield True

    containers_module = ModuleType("src.client.ui.core.containers")
    containers_module.WindowManager = FakeWindowManager

    imgui = SimpleNamespace(
        checkbox=lambda _label, _checked: (True, True),
        input_text=lambda _label, _text: (True, "after"),
    )
    instrumented_imgui_module = ModuleType("src.client.ui.core.instrumented_imgui")
    instrumented_imgui_module.imgui = imgui

    monkeypatch.setitem(sys.modules, "arcade", arcade_module)
    monkeypatch.setitem(sys.modules, "src.client.services.imgui_service", service_module)
    monkeypatch.setitem(sys.modules, "src.client.ui.core.containers", containers_module)
    monkeypatch.setitem(sys.modules, "src.client.ui.core.instrumented_imgui", instrumented_imgui_module)
    monkeypatch.setattr(live_smoke, "uuid4", lambda: UUID(SMOKE_PREFIX))
    return windows, services, FakeWindowManager


def test_live_smoke_runs_commands_and_restores_unset_environment(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.delenv("OPENPOWER_UI_ARTIFACTS", raising=False)
    region = {"rect": {"x": 80, "y": 70}}
    windows, services, window_manager = install_live_smoke_runtime(monkeypatch, region=region)
    output = tmp_path / "live-smoke"

    assert live_smoke.run_live_smoke(output) == 0

    assert os.environ.get("OPENPOWER_UI_ARTIFACTS") is None
    assert json.loads((output / "commands.json").read_text(encoding="utf-8"))["commands"] == [
        {
            "id": f"{SMOKE_PREFIX}.toggle",
            "op": "click",
            "target": {"label": "Toggle", "type": "checkbox"},
        },
        {
            "id": f"{SMOKE_PREFIX}.name",
            "op": "input",
            "target": {"label": "Name", "type": "input_text"},
            "value": "after",
        },
        {
            "id": f"{SMOKE_PREFIX}.move",
            "op": "pointer_drag",
            "start": {"x": 100, "y": 27},
            "end": {"x": 160, "y": 77},
            "steps": 10,
        },
    ]
    assert windows[0].push_handlers.call_count == 1
    assert windows[0].switch_to.call_count == 80
    assert windows[0].dispatch_events.call_count == 80
    assert windows[0].flip.call_count == 80
    assert services[0].new_frame.call_count == 80
    assert services[0].render.call_count == 80
    services[0].shutdown.assert_called_once_with()
    windows[0].close.assert_called_once_with()
    assert window_manager.begin_frame.call_count == 80
    assert "Live UI bridge PASS" in capsys.readouterr().out


def test_live_smoke_reports_failed_commands_and_restores_existing_environment(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setenv("OPENPOWER_UI_ARTIFACTS", "previous-artifacts")
    windows, services, _window_manager = install_live_smoke_runtime(
        monkeypatch,
        all_commands_pass=False,
        region=None,
    )

    assert live_smoke.run_live_smoke(tmp_path / "failed-smoke") == 1

    assert os.environ["OPENPOWER_UI_ARTIFACTS"] == "previous-artifacts"
    services[0].shutdown.assert_called_once_with()
    windows[0].close.assert_called_once_with()
    assert "Live UI bridge FAIL" in capsys.readouterr().out


def test_live_smoke_restores_environment_when_window_creation_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENPOWER_UI_ARTIFACTS", "previous-artifacts")
    windows, services, _window_manager = install_live_smoke_runtime(
        monkeypatch,
        window_error=RuntimeError("window unavailable"),
    )

    with pytest.raises(RuntimeError, match="window unavailable"):
        live_smoke.run_live_smoke(tmp_path / "failed-create")

    assert os.environ["OPENPOWER_UI_ARTIFACTS"] == "previous-artifacts"
    assert windows == []
    assert services == []
