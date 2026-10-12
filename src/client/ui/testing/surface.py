from __future__ import annotations

from pathlib import Path

from imgui_bundle import imgui

from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.testability import UIRunTelemetry
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.testing.catalog import build_surface
from src.client.ui.testing.fixtures import (build_test_world, RecordingClient, RecordingNavigation,
                                          RecordingViewport, TestWindow, test_settings)
from src.client.ui.testing.harness import UITestScenario, run_imgui_test
from src.client.ui.testing.journey import action_record, run_steps


def run_surface(name: str, output: Path, project_root: Path, size=(1920, 1080),
                journey: dict | None = None, fixture: dict | None = None,
                baseline: Path | None = None, tolerance: float = 0.03) -> int:
    state = build_test_world(project_root, fixture)
    client = RecordingClient(state)
    settings = test_settings()
    window = TestWindow(size)
    from src.shared.config import GameConfig
    window.game_config = GameConfig(project_root)
    navigation, viewport = RecordingNavigation(window), RecordingViewport()
    telemetry = UIRunTelemetry(size)
    context = PanelRenderContext("UKR", True, selected_region_id=1, net_client=client)
    from src.client.renderers.flag_renderer import FlagRenderer
    from src.client.ui.testing.textures import TestTextureUploader
    textures = TestTextureUploader()
    flags = FlagRenderer(textures)
    draw = build_surface(name, state, client, context, settings, window, navigation, viewport)
    step_results = []
    steps = (journey or {}).get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("Journey steps must be a list.")

    def render():
        GAMETHEME.apply()
        draw()

    def interact(ctx):
        run_steps(ctx, telemetry, steps, client.actions, step_results)
        ctx.yield_(3)
        visible = any(r["visible"] and r["present"] for r in telemetry.to_dict()["regions"])
        imgui.test_engine.check(__file__, "interact", 0, imgui.test_engine.TestCheckFlags_.none,
                                visible, "UI surface rendered a visible region")

    def checks(passed):
        snapshot = telemetry.to_dict()
        return [
            {"id": "test_engine", "passed": passed, "message": "Interaction scenario completed."},
            {"id": "surface.visible", "passed": any(r["visible"] and r["present"] for r in snapshot["regions"]),
             "message": "At least one UI region is visible."},
            {"id": "widgets.recorded", "passed": any(w["present"] for w in snapshot["widgets"]),
             "message": "Rendered elements are exposed to agents."},
            {"id": "journey.steps", "passed": len(step_results) == len(steps) and all(s["passed"] for s in step_results),
             "message": f"{sum(s['passed'] for s in step_results)}/{len(steps)} journey steps passed."},
        ]

    def details():
        from dataclasses import asdict
        return {"surface": name, "fixture": "custom" if fixture else "deterministic_sample",
                "steps": step_results, "actions": [action_record(a) for a in client.actions],
                "requests": client.requests, "settings": asdict(settings.settings),
                "navigation": navigation.requests, "viewport_requests": viewport.requests}

    return run_imgui_test(UITestScenario(
        "OpenPower UI", name, f"OpenPower UI test: {name}", size, telemetry,
        render, interact, checks, details, baseline, tolerance,
        tuple((journey or {}).get("visual_masks", [])), cleanup=textures.close,
    ), output)
