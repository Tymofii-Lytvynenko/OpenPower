from __future__ import annotations

from pathlib import Path

import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.testability import UIRunTelemetry
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.budget_panel import BudgetPanel
from src.client.ui.testing.driver import UITestDriver
from src.client.ui.testing.harness import UITestScenario, run_imgui_test
from src.shared.actions import ActionUpdateBudget
from src.shared.state import GameState


def _check_interaction(result: bool, message: str) -> None:
    # Importing imgui.test_engine_checks replaces the public native imgui binding
    # with a namespace package in bundle 1.92.5, breaking later UI imports.
    imgui.test_engine.check(
        __file__, "interact", 0, imgui.test_engine.TestCheckFlags_.none,
        result, message,
    )


class _RecordingClient:
    def __init__(self) -> None:
        self.player_id = "ui-test-player"
        self.actions: list[object] = []

    def send_action(self, action: object) -> None:
        self.actions.append(action)


def run_budget_ui_test(
    output_dir: Path,
    viewport_size: tuple[int, int] = (1280, 1000),
) -> int:
    panel = BudgetPanel()
    state = _fixture_state()
    client = _RecordingClient()
    telemetry = UIRunTelemetry(viewport_size)
    render_context = PanelRenderContext(
        target_tag="UKR",
        is_own_country=True,
        net_client=client,
    )

    def render() -> None:
        GAMETHEME.apply()
        panel.render(state, render_context)

    def interact(ctx: imgui.test_engine.TestContext) -> None:
        driver = UITestDriver(ctx, telemetry)
        _check_interaction(driver.exists("budget.income_tax_rate"), "Income tax slider exists")
        _check_interaction(driver.exists("budget.apply"), "Apply button exists")

        driver.input_value("budget.income_tax_rate", 35.0)
        ctx.yield_(2)
        _check_interaction(
            abs(panel.draft_allocations[panel.PERSONAL_INCOME_TAX_KEY] - 0.35) < 0.01,
            "Tax input updates the draft to 35 percent",
        )

        driver.drag_to_fraction("budget.allocation.budget_infra_ratio", 0.70)
        ctx.yield_(2)
        _check_interaction(
            abs(panel.draft_allocations["budget_infra_ratio"] - 0.70) < 0.02,
            "Infrastructure drag updates the draft to 70 percent",
        )

        driver.click("budget.apply")
        ctx.yield_(2)
        _check_interaction(len(client.actions) == 1, "Apply dispatches exactly one action")
        if client.actions:
            action = client.actions[-1]
            _check_interaction(isinstance(action, ActionUpdateBudget), "Action is ActionUpdateBudget")
            if isinstance(action, ActionUpdateBudget):
                _check_interaction(
                    abs(action.allocations[panel.PERSONAL_INCOME_TAX_KEY] - 0.35) < 0.01,
                    "Action contains 35 percent income tax",
                )
                _check_interaction(
                    abs(action.allocations["budget_infra_ratio"] - 0.70) < 0.02,
                    "Action contains 70 percent infrastructure allocation",
                )

    def collect_checks(test_passed: bool) -> list[dict[str, object]]:
        panel_region = telemetry.region("budget.panel")
        tax_slider = telemetry.widget("budget.income_tax_rate")
        allocation_slider = telemetry.widget("budget.allocation.budget_infra_ratio")
        apply_button = telemetry.widget("budget.apply")
        action = client.actions[-1] if client.actions else None
        action_is_budget_update = isinstance(action, ActionUpdateBudget)
        panel_inside_viewport = _rect_inside(
            panel_region.get("rect") if panel_region else None,
            viewport_size,
        )
        panel_rect = panel_region.get("rect") if panel_region else None
        return [
            _check("test_engine", test_passed, "ImGui Test Engine scenario completed successfully."),
            _check(
                "budget.panel.visible",
                bool(panel_region and panel_region["visible"]),
                "Budget window was reported as visible.",
            ),
            _check(
                "budget.panel.inside_viewport",
                panel_inside_viewport,
                "Budget window rectangle fits inside the test viewport.",
            ),
            _check(
                "budget.income_tax_rate.inside_panel",
                _rect_within(tax_slider.get("rect") if tax_slider else None, panel_rect),
                "Income tax slider rectangle is contained by the Budget window.",
            ),
            _check(
                "budget.income_tax_rate.visible",
                bool(tax_slider and tax_slider["ever_visible"]),
                "Income tax slider was visible to the UI runtime.",
            ),
            _check(
                "budget.apply.enabled",
                bool(apply_button and apply_button["ever_enabled"]),
                "Apply button became enabled after the slider changed.",
            ),
            _check(
                "budget.allocation.budget_infra_ratio.visible",
                bool(allocation_slider and allocation_slider["ever_visible"]),
                "Infrastructure allocation drag target was visible.",
            ),
            _check(
                "budget.allocation.budget_infra_ratio.inside_panel",
                _rect_within(
                    allocation_slider.get("rect") if allocation_slider else None,
                    panel_rect,
                ),
                "Infrastructure allocation drag target is inside the Budget window.",
            ),
            _check(
                "budget.apply.inside_panel",
                _rect_within(apply_button.get("rect") if apply_button else None, panel_rect),
                "Apply button rectangle is contained by the Budget window.",
            ),
            _check(
                "budget.action.dispatched",
                action_is_budget_update,
                "Apply dispatched an ActionUpdateBudget command.",
            ),
            _check(
                "budget.tax_rate.applied",
                bool(
                    action_is_budget_update
                    and abs(action.allocations[panel.PERSONAL_INCOME_TAX_KEY] - 0.35) < 0.01
                ),
                "Dispatched action contains a 35 percent personal income tax rate.",
            ),
            _check(
                "budget.allocation.applied",
                bool(
                    action_is_budget_update
                    and abs(action.allocations["budget_infra_ratio"] - 0.70) < 0.02
                ),
                "Dispatched action contains the updated infrastructure allocation.",
            ),
        ]

    def collect_details() -> dict[str, object]:
        action = client.actions[-1] if client.actions else None
        if not isinstance(action, ActionUpdateBudget):
            return {"action": None}
        return {
            "action": {
                "type": type(action).__name__,
                "country_tag": action.country_tag,
                "allocations": action.allocations,
            }
        }

    scenario = UITestScenario(
        category="OpenPower UI",
        name="Budget panel applies a changed tax rate",
        window_title="OpenPower UI test: Budget",
        viewport_size=viewport_size,
        telemetry=telemetry,
        render=render,
        test=interact,
        collect_checks=collect_checks,
        collect_details=collect_details,
    )
    return run_imgui_test(scenario, output_dir)


def _fixture_state() -> GameState:
    country = {
        "id": "UKR",
        "personal_income_tax_rate": 0.20,
        "budget_health_ratio": 0.50,
        "budget_edu_ratio": 0.50,
        "budget_social_ratio": 0.50,
        "budget_gov_ratio": 0.50,
        "budget_env_ratio": 0.50,
        "budget_research_ratio": 0.50,
        "budget_infra_ratio": 0.50,
        "budget_telecom_ratio": 0.50,
        "budget_imf_ratio": 0.50,
        "budget_propaganda_ratio": 0.50,
        "budget_tourism_promo_ratio": 0.50,
        "revenue_tax": 12000.0,
        "trade_income": 4000.0,
        "tourism_income": 1000.0,
        "total_annual_revenue": 17000.0,
        "expense_corruption": 1000.0,
        "security_upkeep": 500.0,
        "diplomacy_upkeep": 250.0,
        "trade_expense": 200.0,
        "expense_military_upkeep": 3000.0,
        "expense_debt_interest": 100.0,
        "money_reserves": 50000.0,
    }
    return GameState(tables={"countries": pl.DataFrame([country])})


def _rect_inside(rect: object, viewport: tuple[int, int]) -> bool:
    if not isinstance(rect, dict):
        return False
    x = float(rect["x"])
    y = float(rect["y"])
    width = float(rect["width"])
    height = float(rect["height"])
    return (
        x >= 0
        and y >= 0
        and x + width <= viewport[0]
        and y + height <= viewport[1]
    )


def _rect_within(rect: object, parent: object) -> bool:
    if not isinstance(rect, dict) or not isinstance(parent, dict):
        return False
    return (
        float(rect["x"]) >= float(parent["x"])
        and float(rect["y"]) >= float(parent["y"])
        and float(rect["x"]) + float(rect["width"])
        <= float(parent["x"]) + float(parent["width"])
        and float(rect["y"]) + float(rect["height"])
        <= float(parent["y"]) + float(parent["height"])
    )


def _check(check_id: str, passed: bool, message: str) -> dict[str, object]:
    return {"id": check_id, "passed": bool(passed), "message": message}
