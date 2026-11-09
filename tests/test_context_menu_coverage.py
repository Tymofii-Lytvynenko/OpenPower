from __future__ import annotations

from unittest.mock import Mock

import polars as pl

from src.client.ui.components.hud.context_menu import ContextMenu


class _Composer:
    def __init__(self, *, menus=(), clicked=()):
        self.menus = set(menus)
        self.clicked = set(clicked)
        self.drawn = []
        self.ended_menus = []

    def begin_popup(self, popup_id):
        return popup_id == "global_map_context"

    def end_popup(self):
        pass

    def begin_menu(self, label):
        return label in self.menus

    def end_menu(self):
        self.ended_menus.append(True)

    def draw_menu_item(self, label, *_args, **_kwargs):
        self.drawn.append(label)
        return label in self.clicked


class _Imgui:
    def __init__(self):
        self.opened_popups = []
        self.menu_item_ids = []
        self.clicked_labels = {"Show All Units Globally", "Show Engagement Zones", "Data Inspector"}

    def open_popup(self, popup_id):
        self.opened_popups.append(popup_id)

    def text_disabled(self, _text):
        pass

    def separator(self):
        pass

    def menu_item(self, label, *_args, test_id=None):
        self.menu_item_ids.append(test_id)
        clicked = label in self.clicked_labels
        clicked |= bool(test_id and test_id.startswith("map.treaty."))
        clicked |= bool(test_id and test_id.startswith("map.context.mode."))
        return (clicked,)


class _Panels:
    def __init__(self):
        self.entries = [Mock(id="DATA_INSPECTOR"), Mock(id="POLITICS")]
        self.visible = {entry.id: False for entry in self.entries}
        self.toggled = []
        self.visibility_changes = []

    def get_entries(self):
        return self.entries

    def is_visible(self, panel_id):
        return self.visible.get(panel_id, False)

    def toggle(self, panel_id):
        self.toggled.append(panel_id)
        self.visible[panel_id] = not self.visible.get(panel_id, False)

    def set_visible(self, panel_id, visible):
        self.visibility_changes.append((panel_id, visible))
        self.visible[panel_id] = visible


class _Viewport:
    def __init__(self):
        self.map_modes = {"political": Mock(name="Political")}
        self.current_mode_key = "political"
        self.show_all_units = True
        self.show_engagement_zones = False
        self.selected_regions = []
        self.focused_regions = []
        self.map_mode_changes = []

    def select_region_by_id(self, region_id):
        self.selected_regions.append(region_id)

    def focus_on_region(self, region_id):
        self.focused_regions.append(region_id)

    def set_map_mode(self, mode):
        self.map_mode_changes.append(mode)


def test_render_dispatches_map_actions_treaties_modes_visibility_and_tools(monkeypatch) -> None:
    import importlib

    module = importlib.import_module("src.client.ui.components.hud.context_menu")
    imgui = _Imgui()
    monkeypatch.setattr(module, "imgui", imgui)
    composer = _Composer(
        menus={"Diplomacy", "Map Mode", "Units Visibility", "Tools"},
        clicked={
            "Occupy Territory",
            "View Details",
            "More Info",
            "Center Camera",
            "Physical (Terrain)",
            "Close All Panels",
        },
    )
    panels = _Panels()
    viewport = _Viewport()
    move_selected = Mock()
    treaties = Mock()
    state = type("State", (), {"tables": {
        "regions": pl.DataFrame([{"id": 7, "controller": "CAN"}]),
        "countries": pl.DataFrame([{"id": "USA"}, {"id": "CAN"}]),
    }})()
    menu = ContextMenu(
        composer,
        panels,
        viewport,
        has_selected_units=lambda: True,
        on_move_selected_units=move_selected,
        on_quick_treaty=treaties,
    )
    menu.show(7)

    menu.render(state, player_tag="USA")

    assert imgui.opened_popups == ["global_map_context"]
    assert move_selected.call_count == 1
    assert panels.visibility_changes[:2] == [("INSPECTOR", True), ("COUNTRY_MORE_INFO", True)]
    assert viewport.selected_regions == [7, 7]
    assert viewport.focused_regions == [7]
    assert viewport.map_mode_changes == ["terrain", "political"]
    assert viewport.show_all_units is False
    assert viewport.show_engagement_zones is True
    assert panels.toggled == ["DATA_INSPECTOR"]
    assert all(not panels.visible[entry.id] for entry in panels.entries)
    assert any(call.args[-1] is False for call in treaties.call_args_list)
    assert any(call.args[-1] is True for call in treaties.call_args_list)
    assert len(composer.ended_menus) == 4


def test_target_country_rejects_missing_regions_and_unmatched_country_rows() -> None:
    menu = ContextMenu(Mock(), Mock(), Mock())
    menu.show(7)
    cases = [
        type("State", (), {"tables": {}})(),
        type("State", (), {"tables": {"regions": pl.DataFrame([{"id": 1}])}})(),
        type("State", (), {"tables": {
            "regions": pl.DataFrame([{"id": 7, "controller": "CAN"}]),
            "countries": pl.DataFrame([{"tag": "CAN"}]),
        }})(),
        type("State", (), {"tables": {
            "regions": pl.DataFrame([{"id": 7, "controller": "CAN"}]),
            "countries": pl.DataFrame([{"id": "USA"}]),
        }})(),
    ]

    for state in cases:
        menu._state = state
        assert menu._target_country() == ""
