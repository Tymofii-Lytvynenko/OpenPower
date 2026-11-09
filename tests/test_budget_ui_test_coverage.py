from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.client.ui.testing import budget as budget_module
from src.shared.actions import ActionUpdateBudget


class FakeBudgetPanel:
    PERSONAL_INCOME_TAX_KEY = "personal_income_tax_rate"
    instances: list["FakeBudgetPanel"] = []

    def __init__(self) -> None:
        self.draft_allocations = {
            self.PERSONAL_INCOME_TAX_KEY: 0.20,
            "budget_infra_ratio": 0.50,
        }
        self.render = Mock()
        self.instances.append(self)


class FakeTelemetry:
    def __init__(self, viewport_size: tuple[int, int], *, widgets_available: bool) -> None:
        self.viewport_size = viewport_size
        self.widgets_available = widgets_available
        self.panel_rect = {"x": 100, "y": 100, "width": 500, "height": 600}
        self.child_rect = {"x": 110, "y": 200, "width": 200, "height": 40}

    def region(self, test_id: str):
        if test_id == "budget.panel" and self.widgets_available:
            return {"rect": self.panel_rect, "visible": True}
        return None

    def widget(self, test_id: str):
        if not self.widgets_available:
            return None
        if test_id == "budget.income_tax_rate":
            return {"rect": self.child_rect, "ever_visible": True}
        if test_id == "budget.allocation.budget_infra_ratio":
            return {"rect": self.child_rect, "ever_visible": True}
        if test_id == "budget.apply":
            return {"rect": self.child_rect, "ever_enabled": True}
        return None


def install_budget_runtime(
    monkeypatch,
    *,
    apply_action: bool = True,
    widgets_available: bool = True,
    test_passed: bool = True,
):
    FakeBudgetPanel.instances.clear()
    clients = []
    driver_calls = []
    telemetry_instances = []
    checks = Mock()
    imgui = SimpleNamespace(
        test_engine=SimpleNamespace(
            TestCheckFlags_=SimpleNamespace(none=0),
            check=checks,
        )
    )
    theme = SimpleNamespace(apply=Mock())

    original_client = budget_module._RecordingClient

    def make_client():
        client = original_client()
        clients.append(client)
        return client

    def make_telemetry(viewport_size):
        telemetry = FakeTelemetry(viewport_size, widgets_available=widgets_available)
        telemetry_instances.append(telemetry)
        return telemetry

    class FakeDriver:
        def __init__(self, _ctx, telemetry) -> None:
            self.telemetry = telemetry
            self.panel = FakeBudgetPanel.instances[-1]
            self.client = clients[-1]

        def exists(self, test_id: str) -> bool:
            driver_calls.append(("exists", test_id))
            return True

        def input_value(self, test_id: str, value: float) -> None:
            driver_calls.append(("input_value", test_id, value))
            if apply_action:
                self.panel.draft_allocations[self.panel.PERSONAL_INCOME_TAX_KEY] = value / 100

        def drag_to_fraction(self, test_id: str, fraction: float) -> None:
            driver_calls.append(("drag_to_fraction", test_id, fraction))
            if apply_action:
                self.panel.draft_allocations["budget_infra_ratio"] = fraction

        def click(self, test_id: str) -> None:
            driver_calls.append(("click", test_id))
            if apply_action:
                self.client.send_action(
                    ActionUpdateBudget(
                        self.client.player_id,
                        "UKR",
                        dict(self.panel.draft_allocations),
                    )
                )

    scenario_data = {}

    def run_scenario(scenario, output_dir: Path) -> int:
        scenario_data["scenario"] = scenario
        scenario_data["output_dir"] = output_dir
        scenario.render()
        context = SimpleNamespace(yield_=Mock())
        scenario.test(context)
        scenario_data["context"] = context
        scenario_data["checks"] = scenario.collect_checks(test_passed)
        scenario_data["details"] = scenario.collect_details()
        return 4

    monkeypatch.setattr(budget_module, "BudgetPanel", FakeBudgetPanel)
    monkeypatch.setattr(budget_module, "_RecordingClient", make_client)
    monkeypatch.setattr(budget_module, "UIRunTelemetry", make_telemetry)
    monkeypatch.setattr(budget_module, "UITestDriver", FakeDriver)
    monkeypatch.setattr(budget_module, "run_imgui_test", run_scenario)
    monkeypatch.setattr(budget_module, "imgui", imgui)
    monkeypatch.setattr(budget_module, "GAMETHEME", theme)
    return clients, driver_calls, telemetry_instances, scenario_data, theme, checks


def test_budget_ui_scenario_collects_successful_interaction_and_geometry(monkeypatch, tmp_path) -> None:
    clients, calls, telemetries, result, theme, imgui_check = install_budget_runtime(monkeypatch)
    output = tmp_path / "budget-ui"

    assert budget_module.run_budget_ui_test(output, (1024, 768)) == 4

    panel = FakeBudgetPanel.instances[0]
    action = clients[0].actions[0]
    assert isinstance(action, ActionUpdateBudget)
    assert action.player_id == "ui-test-player"
    assert action.country_tag == "UKR"
    assert action.allocations == {
        "personal_income_tax_rate": 0.35,
        "budget_infra_ratio": 0.70,
    }
    assert panel.render.call_args.args[1].target_tag == "UKR"
    assert theme.apply.call_count == 1
    assert result["output_dir"] == output
    assert result["scenario"].viewport_size == (1024, 768)
    assert result["scenario"].name == "Budget panel applies a changed tax rate"
    assert result["checks"] and all(check["passed"] for check in result["checks"])
    assert result["details"] == {
        "action": {
            "type": "ActionUpdateBudget",
            "country_tag": "UKR",
            "allocations": action.allocations,
        }
    }
    assert [name for name, *_rest in calls] == [
        "exists",
        "exists",
        "input_value",
        "drag_to_fraction",
        "click",
    ]
    assert [call.args for call in result["context"].yield_.call_args_list] == [
        (2,),
        (2,),
        (2,),
    ]
    assert telemetries[0].viewport_size == (1024, 768)
    assert imgui_check.call_count == 8


def test_budget_ui_scenario_reports_missing_action_and_widgets(monkeypatch, tmp_path) -> None:
    clients, _calls, _telemetries, result, _theme, _imgui_check = install_budget_runtime(
        monkeypatch,
        apply_action=False,
        widgets_available=False,
        test_passed=False,
    )

    assert budget_module.run_budget_ui_test(tmp_path / "budget-ui") == 4

    assert clients[0].actions == []
    assert result["details"] == {"action": None}
    check_results = {check["id"]: check["passed"] for check in result["checks"]}
    assert check_results["test_engine"] is False
    assert check_results["budget.panel.visible"] is False
    assert check_results["budget.panel.inside_viewport"] is False
    assert check_results["budget.apply.enabled"] is False
    assert check_results["budget.action.dispatched"] is False
    assert check_results["budget.tax_rate.applied"] is False


def test_budget_fixture_and_geometry_helpers_cover_valid_and_invalid_rectangles() -> None:
    state = budget_module._fixture_state()
    country = state.get_table("countries").to_dicts()[0]
    assert country["id"] == "UKR"
    assert country["personal_income_tax_rate"] == 0.20

    inside = {"x": 0, "y": 0, "width": 1280, "height": 1000}
    outside = {"x": 1279, "y": 0, "width": 2, "height": 10}
    child = {"x": 110, "y": 200, "width": 20, "height": 30}
    parent = {"x": 100, "y": 100, "width": 200, "height": 200}

    assert budget_module._rect_inside(inside, (1280, 1000)) is True
    assert budget_module._rect_inside(outside, (1280, 1000)) is False
    assert budget_module._rect_inside(None, (1280, 1000)) is False
    assert budget_module._rect_within(child, parent) is True
    assert budget_module._rect_within(outside, parent) is False
    assert budget_module._rect_within(child, None) is False
    assert budget_module._check("sample", 1, "checked") == {
        "id": "sample",
        "passed": True,
        "message": "checked",
    }


def test_recording_client_stores_actions_and_interaction_checks_use_imgui(monkeypatch) -> None:
    checks = Mock()
    monkeypatch.setattr(
        budget_module,
        "imgui",
        SimpleNamespace(test_engine=SimpleNamespace(
            TestCheckFlags_=SimpleNamespace(none=0),
            check=checks,
        )),
    )
    client = budget_module._RecordingClient()
    action = ActionUpdateBudget("player-1", "UKR", {"budget_infra_ratio": 0.7})

    client.send_action(action)
    budget_module._check_interaction(True, "action recorded")

    assert client.player_id == "ui-test-player"
    assert client.actions == [action]
    checks.assert_called_once_with(
        budget_module.__file__,
        "interact",
        0,
        0,
        True,
        "action recorded",
    )
