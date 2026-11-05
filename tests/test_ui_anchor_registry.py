from src.client.ui.core.containers import WindowManager
from src.client.ui.core.ui_anchor_registry import UIAnchorRegistry


def test_registry_tracks_only_the_requested_anchor_for_the_current_frame() -> None:
    UIAnchorRegistry.set_targets(("hud.panel.mil",))
    UIAnchorRegistry.begin_frame()

    UIAnchorRegistry.record("hud.panel.mil", 10.0, 20.0, 40.0, 30.0)
    UIAnchorRegistry.record("hud.panel.pol", 60.0, 20.0, 40.0, 30.0)

    assert UIAnchorRegistry.get("hud.panel.mil").x == 10.0
    assert UIAnchorRegistry.get("hud.panel.pol") is None

    WindowManager.begin_frame()
    assert UIAnchorRegistry.get("hud.panel.mil") is None
    UIAnchorRegistry.set_targets(())


def test_registry_discards_geometry_when_the_tutorial_target_changes() -> None:
    UIAnchorRegistry.set_targets(("hud.country",))
    UIAnchorRegistry.record("hud.country", 1.0, 2.0, 30.0, 20.0)

    UIAnchorRegistry.set_targets(("hud.relations",))

    assert UIAnchorRegistry.get("hud.country") is None
    assert UIAnchorRegistry.get("hud.relations") is None
    UIAnchorRegistry.set_targets(())
