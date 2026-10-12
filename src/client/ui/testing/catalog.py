"""Discover test surfaces from the same registry used by the production HUD."""
from __future__ import annotations

from src.client.ui.components.hud.panel_manager import PanelManager
from src.client.ui.layouts.game_panel_registry import build_game_panel_specs


EXTRA_SURFACES = ("game-hud", "editor-hud", "map-context", "unit-context", "unit-details")


def panel_specs(settings=None, window=None):
    manager = PanelManager()
    specs = build_game_panel_specs(manager, settings, window)
    return manager, specs


def list_surfaces() -> list[dict]:
    _, specs = panel_specs()
    return [{"id": spec.id.lower().replace("_", "-"), "title": spec.title,
             "category": spec.category} for spec in specs] + [
        {"id": name, "title": name, "category": "layout"} for name in EXTRA_SURFACES
    ]


def build_surface(name, state, client, context, settings, window, navigation, viewport):
    from src.client.ui.layouts.game_layout import GameLayout
    from src.client.ui.layouts.editor_layout import EditorLayout
    from src.client.ui.core.composer import UIComposer
    from src.client.ui.core.theme import GAMETHEME
    from src.client.ui.components.hud.unit_context_menu import UnitContextMenu
    from src.client.ui.panels.unit_details_window import UnitDetailsWindow

    normalized = name.lower().replace("_", "-")
    if normalized in {"game-hud", "map-context"}:
        layout = GameLayout(client, context.target_tag, viewport, settings, window)
        if normalized == "map-context":
            layout.show_context_menu(1)
        return lambda: layout.render(context.selected_region_id, 60.0, navigation, state)
    if normalized == "editor-hud":
        layout = EditorLayout(client, viewport)
        return lambda: layout.render(60.0)
    if normalized == "unit-context":
        menu = UnitContextMenu(UIComposer(GAMETHEME), lambda: None, lambda _: None)
        menu.show("unit-1")
        return menu.render
    if normalized == "unit-details":
        panel = UnitDetailsWindow()
        panel.open_for_unit("unit-1")
        return lambda: panel.render(state)
    manager, specs = panel_specs(settings, window)
    for spec in specs:
        manager.register_spec(spec)
    selected = next((s for s in specs if s.id.lower().replace("_", "-") == normalized), None)
    if selected is None:
        raise ValueError(f"Unknown UI surface: {name}. Use 'openpower ui-test list'.")
    manager.set_visible(selected.id, True)
    return lambda: manager.render_all(state, context)
