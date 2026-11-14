from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from src.modding import client_extensions
from src.shared import config as config_module
from src.simulation.ui_testing import surface as surface_module


@dataclass
class SettingsSnapshot:
    scale: float = 1.25
    enabled: bool = True


class FakeTelemetry:
    def __init__(self, size, snapshot) -> None:
        self.size = size
        self.snapshot = snapshot
        self.to_dict = Mock(side_effect=lambda: self.snapshot)


class FakeTextures:
    instances: list["FakeTextures"] = []

    def __init__(self) -> None:
        self.close = Mock()
        self.instances.append(self)


class FakeFlagRenderer:
    instances: list["FakeFlagRenderer"] = []

    def __init__(self, textures) -> None:
        self.textures = textures
        self.instances.append(self)


def install_surface_runtime(
    monkeypatch,
    *,
    snapshot: dict,
    step_outcomes: list[dict] | None = None,
    interact: bool = True,
    passed: bool = True,
    result_code: int = 6,
):
    FakeTextures.instances.clear()
    FakeFlagRenderer.instances.clear()
    state = object()
    client = SimpleNamespace(
        player_country="ukr",
        actions=["action-1"],
        requests=[{"type": "save"}],
        deliver_event=Mock(),
        deliver_snapshot=Mock(),
        enable_client_view=Mock(),
        get_state=Mock(return_value=state),
    )
    telemetry_instances = []
    draw = Mock()
    theme = SimpleNamespace(apply=Mock())
    imgui = SimpleNamespace(
        test_engine=SimpleNamespace(
            TestCheckFlags_=SimpleNamespace(none=0),
            check=Mock(),
        )
    )
    calls = {}

    class FakeGameConfig:
        def __init__(self, project_root: Path) -> None:
            self.project_root = project_root

        def get_asset_path(self, relative_path: str) -> Path:
            return self.project_root / relative_path

    def make_telemetry(size):
        telemetry = FakeTelemetry(size, snapshot)
        telemetry_instances.append(telemetry)
        return telemetry

    def run_steps(ctx, telemetry, steps, actions, results, checkpoints, deliver_event,
                  deliver_snapshot, viewport_requests, navigation_requests):
        calls["run_steps"] = {
            "ctx": ctx,
            "telemetry": telemetry,
            "steps": steps,
            "actions": actions,
            "checkpoints": checkpoints,
            "deliver_event": deliver_event,
            "deliver_snapshot": deliver_snapshot,
            "viewport_requests": viewport_requests,
            "navigation_requests": navigation_requests,
        }
        results.extend(step_outcomes or [])

    def execute_imgui_test(scenario, output_dir):
        calls["scenario"] = scenario
        calls["output"] = output_dir
        scenario.render()
        if interact:
            ctx = SimpleNamespace(yield_=Mock())
            calls["ctx"] = ctx
            scenario.test(ctx)
        calls["checks"] = scenario.collect_checks(passed)
        calls["details"] = scenario.collect_details()
        scenario.cleanup()
        return result_code

    run_imgui_test = Mock(side_effect=execute_imgui_test)

    telemetry_module = ModuleType("src.client.ui.testing.country_info_assets")
    telemetry_module.load_compact_region_map = Mock(return_value="compact-map")
    renderer_module = ModuleType("src.client.renderers.flag_renderer")
    renderer_module.FlagRenderer = FakeFlagRenderer
    textures_module = ModuleType("src.client.ui.testing.textures")
    textures_module.TestTextureUploader = FakeTextures

    monkeypatch.setattr(surface_module, "build_test_world", Mock(return_value=state))
    monkeypatch.setattr(surface_module, "RecordingClient", Mock(return_value=client))
    monkeypatch.setattr(surface_module, "test_settings", lambda: SimpleNamespace(settings=SettingsSnapshot()))
    monkeypatch.setattr(surface_module, "UIRunTelemetry", make_telemetry)
    monkeypatch.setattr(surface_module, "build_surface", Mock(return_value=draw))
    monkeypatch.setattr(surface_module, "run_steps", run_steps)
    monkeypatch.setattr(surface_module, "action_record", lambda action: {"action": action})
    monkeypatch.setattr(surface_module, "run_imgui_test", run_imgui_test)
    monkeypatch.setattr(surface_module, "imgui", imgui)
    monkeypatch.setattr(surface_module, "GAMETHEME", theme)
    presentation = {"test.presentation": object()}
    monkeypatch.setattr(client_extensions, "load_client_presentation", Mock(return_value=presentation))
    monkeypatch.setattr(config_module, "GameConfig", FakeGameConfig)
    monkeypatch.setitem(__import__("sys").modules, telemetry_module.__name__, telemetry_module)
    monkeypatch.setitem(__import__("sys").modules, renderer_module.__name__, renderer_module)
    monkeypatch.setitem(__import__("sys").modules, textures_module.__name__, textures_module)
    calls["presentation"] = presentation
    calls["run_imgui_test"] = run_imgui_test
    return state, client, telemetry_instances, draw, theme, imgui, calls


def test_run_surface_builds_and_executes_custom_fixture_journey(monkeypatch, tmp_path) -> None:
    snapshot = {
        "regions": [{"visible": True, "present": True}],
        "widgets": [{"present": True}],
    }
    state, client, telemetries, draw, theme, imgui, calls = install_surface_runtime(
        monkeypatch,
        snapshot=snapshot,
        step_outcomes=[{"passed": True, "geometry_errors": []}],
    )
    fixture = {
        "test_support": {
            "player_country": " ca ",
            "selected_region_id": "17",
            "use_base_region_map": True,
        }
    }
    journey = {
        "steps": [{"action": "select-region"}],
        "visual_masks": [{"test_id": "fixture.mask"}],
    }
    baseline = tmp_path / "baseline.png"
    output = tmp_path / "artifacts"
    result = surface_module.run_surface(
        "country-info",
        output,
        tmp_path,
        size=(800, 600),
        journey=journey,
        fixture=fixture,
        baseline=baseline,
        tolerance=0.08,
    )

    assert result == 6
    surface_module.build_test_world.assert_called_once_with(tmp_path, fixture)
    assert client.player_country == "CA"
    client.enable_client_view.assert_called_once_with(calls["presentation"])
    assert surface_module.build_surface.call_args.args[1]._client is client
    assert surface_module.build_surface.call_args.args[0] == "country-info"
    context = surface_module.build_surface.call_args.args[3]
    window = surface_module.build_surface.call_args.args[5]
    assert context.target_tag == "CA"
    assert context.selected_region_id == 17
    assert context.net_client is client
    assert window.session.map_data == "compact-map"
    assert telemetries[0].size == (800, 600)
    assert calls["output"] == output
    assert calls["scenario"].baseline == baseline
    assert calls["scenario"].visual_tolerance == 0.08
    assert calls["scenario"].visual_masks == tuple(journey["visual_masks"])
    assert calls["scenario"].font_path == tmp_path / "fonts" / "main_font.ttf"
    assert calls["checks"] == [
        {"id": "test_engine", "passed": True, "message": "Interaction scenario completed."},
        {"id": "surface.visible", "passed": True, "message": "At least one UI region is visible."},
        {"id": "widgets.recorded", "passed": True, "message": "Rendered elements are exposed to agents."},
        {"id": "journey.steps", "passed": True, "message": "1/1 journey steps passed."},
        {
            "id": "journey.checkpoint_geometry",
            "passed": True,
            "message": "Check every captured destination, including dialogs closed before the final frame.",
        },
    ]
    assert calls["details"] == {
        "surface": "country-info",
        "fixture": "custom",
        "steps": [{"passed": True, "geometry_errors": []}],
        "actions": [{"action": "action-1"}],
        "requests": [{"type": "save"}],
        "settings": {"scale": 1.25, "enabled": True},
        "navigation": [],
        "viewport_requests": [],
    }
    FakeTextures.instances[0].close.assert_called_once_with()
    assert FakeFlagRenderer.instances[0].textures is FakeTextures.instances[0]
    draw.assert_called_once_with()
    theme.apply.assert_called_once_with()
    calls["ctx"].yield_.assert_called_once_with(3)
    run_steps_call = calls["run_steps"]
    assert run_steps_call["checkpoints"] == output / "checkpoints"
    assert run_steps_call["deliver_event"] is client.deliver_event
    assert run_steps_call["deliver_snapshot"] is client.deliver_snapshot
    imgui.test_engine.check.assert_called_once_with(
        surface_module.__file__,
        "interact",
        0,
        0,
        True,
        "UI surface rendered a visible region",
    )


def test_run_surface_uses_defaults_and_fallback_snapshot_without_interaction(
    monkeypatch,
    tmp_path,
) -> None:
    snapshot = {"regions": [{"visible": False, "present": True}], "widgets": [{"present": False}]}
    _state, client, telemetries, _draw, _theme, _imgui, calls = install_surface_runtime(
        monkeypatch,
        snapshot=snapshot,
        interact=False,
        passed=False,
        result_code=1,
    )

    assert surface_module.run_surface("main-menu", tmp_path / "out", tmp_path) == 1

    assert client.player_country == "UKR"
    assert telemetries[0].to_dict.call_count == 1
    assert calls["scenario"].viewport_size == (1920, 1080)
    assert calls["scenario"].baseline is None
    assert calls["scenario"].visual_tolerance == 0.03
    assert calls["scenario"].visual_masks == ()
    assert calls["checks"][0]["passed"] is False
    assert calls["checks"][1]["passed"] is False
    assert calls["checks"][2]["passed"] is False
    assert calls["checks"][3]["passed"] is True
    assert calls["details"]["fixture"] == "deterministic_sample"
    assert "run_steps" not in calls


def test_run_surface_rejects_non_list_journey_steps(monkeypatch, tmp_path) -> None:
    _state, _client, _telemetry, _draw, _theme, _imgui, calls = install_surface_runtime(
        monkeypatch,
        snapshot={"regions": [], "widgets": []},
    )

    with pytest.raises(ValueError, match="Journey steps must be a list"):
        surface_module.run_surface(
            "main-menu",
            tmp_path / "out",
            tmp_path,
            journey={"steps": "click"},
        )

    calls["run_imgui_test"].assert_not_called()
