from __future__ import annotations

from pathlib import Path

from imgui_bundle import imgui

from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.testability import UIRunTelemetry
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.testing.catalog import build_surface
from src.client.ui.testing.harness import UITestScenario, run_imgui_test
from src.client.ui.testing.journey import action_record, run_steps
from src.simulation.ui_testing.fixtures import (
    RecordingClient,
    RecordingNavigation,
    RecordingViewport,
    TestWindow,
    build_test_world,
    test_settings,
)


def run_surface(name: str, output: Path, project_root: Path, size=(1920, 1080),
                journey: dict | None = None, fixture: dict | None = None,
                baseline: Path | None = None, tolerance: float = 0.03) -> int:
    state = build_test_world(project_root, fixture)
    client = RecordingClient(state)
    support = (fixture or {}).get("test_support", {})
    player_country = str(support.get("player_country") or client.player_country).strip().upper()
    client.player_country = player_country
    settings = test_settings()
    window = TestWindow(size)
    from src.shared.config import GameConfig
    window.game_config = GameConfig(project_root)
    if support.get("use_base_region_map"):
        from types import SimpleNamespace

        from src.client.ui.testing.country_info_assets import load_compact_region_map

        window.session = SimpleNamespace(map_data=load_compact_region_map(project_root))
    navigation, viewport = RecordingNavigation(window), RecordingViewport()
    telemetry = UIRunTelemetry(size)
    selected_region_id = int(support.get("selected_region_id", 1))
    context = PanelRenderContext(
        player_country, True, selected_region_id=selected_region_id, net_client=client
    )
    from src.client.renderers.flag_renderer import FlagRenderer
    from src.client.ui.testing.textures import TestTextureUploader
    textures = TestTextureUploader()
    flags = FlagRenderer(textures)
    draw = build_surface(
        name, state, client, context, settings, window, navigation, viewport, fixture
    )
    step_results = []
    interaction_snapshot = {}
    steps = (journey or {}).get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("Journey steps must be a list.")

    def render():
        GAMETHEME.apply()
        draw()

    def interact(ctx):
        run_steps(ctx, telemetry, steps, client.actions, step_results, output / "checkpoints",
                  client.deliver_event, client.deliver_snapshot, viewport.requests,
                  navigation.requests)
        ctx.yield_(3)
        interaction_snapshot.update(telemetry.to_dict())
        visible = any(r["visible"] and r["present"] for r in interaction_snapshot["regions"])
        imgui.test_engine.check(__file__, "interact", 0, imgui.test_engine.TestCheckFlags_.none,
                                visible, "UI surface rendered a visible region")

    def checks(passed):
        # The test engine dismisses popups during cleanup. Validate the frame
        # actually tested, not that cleanup frame, for popup-only surfaces.
        snapshot = interaction_snapshot or telemetry.to_dict()
        return [
            {"id": "test_engine", "passed": passed, "message": "Interaction scenario completed."},
            {"id": "surface.visible", "passed": any(r["visible"] and r["present"] for r in snapshot["regions"]),
             "message": "At least one UI region is visible."},
            {"id": "widgets.recorded", "passed": any(w["present"] for w in snapshot["widgets"]),
             "message": "Rendered elements are exposed to agents."},
            {"id": "journey.steps", "passed": len(step_results) == len(steps) and all(s["passed"] for s in step_results),
             "message": f"{sum(s['passed'] for s in step_results)}/{len(steps)} journey steps passed."},
            {"id": "journey.checkpoint_geometry",
             "passed": not any(step.get("geometry_errors") for step in step_results),
             "message": "Check every captured destination, including dialogs closed before the final frame."},
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
        font_path=window.game_config.get_asset_path("fonts/main_font.ttf"),
    ), output)
