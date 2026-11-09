from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from src.client.ui.panels.military import unit_research_panel as module
from src.client.ui.panels.military.unit_research_panel import UnitResearchPanel
from src.client.ui.components.shared.dirty_close_confirmation import CloseDecision


class Ui:
    def __init__(self, *, buttons=(), toggles=None, sliders=None, tabs=(), rects=None):
        self.buttons = set(buttons)
        self.toggles = toggles or {}
        self.sliders = sliders or {}
        self.tabs = set(tabs)
        self.rects = rects or {}
        self.frames = []
        self.texts = []
        self.text_at_calls = []
        self.meters = []
        self.slider_calls = []
        self.tab_calls = []

    def frame(self, slot):
        self.frames.append(slot)

    def button(self, _slot, _label, test_id, **kwargs):
        return test_id in self.buttons and kwargs.get("enabled", True)

    def toggle(self, _slot, value, test_id, **_kwargs):
        return self.toggles.get(test_id, (False, value))

    def meter_slider(self, slot, value, test_id, _color, **_kwargs):
        self.slider_calls.append((slot, value, test_id))
        return self.sliders.get(test_id, (False, value))

    def text(self, *args, **kwargs):
        self.texts.append((args, kwargs))

    def text_at(self, *args, **kwargs):
        self.text_at_calls.append((args, kwargs))

    def meter(self, *args, **kwargs):
        self.meters.append((args, kwargs))

    def rect(self, slot):
        return self.rects.get(slot, SimpleNamespace(x=0.0, y=0.0, width=100.0, height=80.0))

    def button_at(self, _slot, _label, test_id, **_kwargs):
        self.tab_calls.append(test_id)
        return test_id in self.tabs


class Client:
    player_id = "player-7"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def _tracks():
    return {
        "ground": {"branch": "ground", "funding_ratio": 0.4, "focus": "Armor", "research_level": 2, "progress": 0.35},
        "air": {"branch": "air", "funding_ratio": 0.3},
        "naval": {"branch": "naval", "funding_ratio": 0.2},
        "strategic": {"branch": "strategic", "funding_ratio": 0.1},
        "strategic_program": {"branch": "strategic_program", "funding_ratio": 0.5, "research_level": 3, "progress": 0.6},
        "strategic_weapons": {"branch": "strategic_weapons", "funding_ratio": 0.3, "research_level": 2, "progress": 0.4},
        "strategic_defense": {"branch": "strategic_defense", "funding_ratio": 0.2, "research_level": 1, "progress": 0.8},
    }


def test_research_controls_draw_frames_edit_funding_and_show_program_details(monkeypatch):
    panel = UnitResearchPanel()
    panel._draft_country_tag = "USA"
    panel._funding_baseline = {"ground": 0.4, "air": 0.3, "naval": 0.2, "strategic": 0.1}
    panel._funding_draft = panel._funding_baseline.copy()
    panel._apply_funding_draft = Mock()
    ui = Ui(
        buttons={"unit_research.apply"},
        toggles={"unit_research.branch.strategic": (True, True)},
        sliders={"unit_research.funding.ground": (True, 0.6)},
    )
    monkeypatch.setattr(module, "semantic_region", lambda *_args: nullcontext())
    tracks = _tracks()
    context = SimpleNamespace()
    state = SimpleNamespace()

    panel._draw_frames(ui)
    panel._render_categories(ui)
    panel._render_funding_controls(ui, tracks, context, True)
    panel._render_title_controls(ui, tracks, context, True, state)
    panel._render_program_view(ui, tracks)

    assert len(ui.frames) == 8
    panel._apply_funding_draft.assert_called_once_with(tracks, context, state)
    assert panel._selected_branch == "strategic"
    assert sum(panel._funding_draft[key] for key in ("ground", "air", "naval", "strategic")) == pytest.approx(1.0)
    assert any(args[1] == "STRATEGIC RESEARCH" for args, _kwargs in ui.text_at_calls)
    assert any(args[1] == "PROGRAM: LEVEL 3  60%" for args, _kwargs in ui.text_at_calls)
    assert any("WEAPONS: LEVEL 2" in args[1] for args, _kwargs in ui.text_at_calls)


def test_research_detail_tabs_render_program_and_edit_strategic_funding(monkeypatch):
    panel = UnitResearchPanel()
    panel._selected_branch = "strategic"
    panel._draft_country_tag = "USA"
    panel._funding_draft = {
        "ground": 0.4, "air": 0.3, "naval": 0.2, "strategic": 0.1,
        "strategic_program": 0.5, "strategic_weapons": 0.3, "strategic_defense": 0.2,
    }
    panel._funding_baseline = panel._funding_draft.copy()
    panel._pending_funding_by_country["USA"] = {"strategic_weapons": 0.3}
    tracks = _tracks()
    ui = Ui(
        tabs={"unit_research.tab.funding"},
        sliders={"unit_research.funding.strategic_program": (True, 0.6)},
    )
    imgui = MagicMock()
    imgui.get_item_rect_min.return_value = SimpleNamespace(x=5.0, y=7.0)
    imgui.get_item_rect_max.return_value = SimpleNamespace(x=105.0, y=24.0)
    imgui.get_color_u32.return_value = 99
    imgui.get_window_draw_list.return_value = MagicMock()
    monkeypatch.setattr(module, "imgui", imgui)
    monkeypatch.setattr(module, "semantic_region", lambda *_args: nullcontext())
    context = SimpleNamespace()

    panel._render_detail_tabs(ui, tracks, context, True)

    assert panel._selected_tab == "funding"
    assert "unit_research.tab.technology" in ui.tab_calls
    assert "unit_research.tab.funding" in ui.tab_calls
    assert imgui.get_window_draw_list.return_value.add_line.call_count == 2
    assert any(args[1] == "PROGRAM" for args, _kwargs in ui.texts)
    assert any(args[1] == "60%" for args, _kwargs in ui.text_at_calls)


@pytest.mark.parametrize(
    ("tab", "expected_unavailable"),
    [
        (("technology", "TECHNOLOGY", "Tab1"), "Per-characteristic technology ceilings are not tracked in OpenPower."),
        (("progress", "PROGRESS", "Tab2"), "Per-characteristic progress is not tracked in OpenPower."),
        (("funding", "FUNDING", "Tab3"), "Funding is controlled per branch in the left panel."),
    ],
)
def test_detail_pages_keep_untracked_metrics_explicit(monkeypatch, tab, expected_unavailable):
    panel = UnitResearchPanel()
    panel._selected_branch = "ground"
    ui = Ui()
    monkeypatch.setattr(module, "semantic_region", lambda *_args: nullcontext())

    panel._render_detail_page(ui, _tracks(), SimpleNamespace(), False, tab)

    assert len(ui.meters) == 12
    assert any(kwargs.get("tooltip") == expected_unavailable for _args, kwargs in ui.texts)


def test_program_view_shows_category_summary_for_non_strategic_branch(monkeypatch):
    panel = UnitResearchPanel()
    panel._selected_branch = "ground"
    panel._funding_draft = {"ground": 0.35}
    ui = Ui()
    monkeypatch.setattr(module, "semantic_region", lambda *_args: nullcontext())

    panel._render_program_view(ui, _tracks())

    values = [args[1] for args, _kwargs in ui.text_at_calls]
    assert "GROUND RESEARCH" in values
    assert "Research level: 2" in values
    assert "Branch progress: 35%" in values
    assert "Branch funding: 35%" in values
    assert "Per-stat metrics unavailable." in values


def test_strategic_detail_pages_show_track_levels_and_progress(monkeypatch):
    panel = UnitResearchPanel()
    panel._selected_branch = "strategic"
    panel._funding_draft = {"strategic_program": 0.5}
    ui = Ui()
    monkeypatch.setattr(module, "semantic_region", lambda *_args: nullcontext())

    panel._render_detail_page(ui, _tracks(), SimpleNamespace(), False, ("technology", "TECHNOLOGY", "Tab1"))
    technology_values = [args[1] for args, _kwargs in ui.text_at_calls]
    assert "LEVEL 3" in technology_values
    assert "LEVEL 2" in technology_values
    assert "LEVEL 1" in technology_values

    ui = Ui()
    panel._render_detail_page(ui, _tracks(), SimpleNamespace(), False, ("progress", "PROGRESS", "Tab2"))
    assert any(args[1] == "60%" for args, _kwargs in ui.texts)
    assert any(args[1] == "80%" for args, _kwargs in ui.texts)
    assert any(args[0].endswith("/lblValue") and args[1] == "N/A" for args, _kwargs in ui.texts)


def test_detail_tabs_stop_when_the_source_has_no_tab_slot():
    panel = UnitResearchPanel()
    ui = Ui(rects={"frmDetails/tabResearch": None})

    panel._render_detail_tabs(ui, {}, SimpleNamespace(), False)

    assert ui.tab_calls == []


def test_finish_close_discards_draft_to_authoritative_snapshot():
    panel = UnitResearchPanel()
    panel._draft_country_tag = "USA"
    panel._funding_draft["ground"] = 0.9
    panel._presenter.research_tracks_for_country = Mock(return_value=[{
        "branch": "ground", "funding_ratio": 0.45,
    }])

    panel._finish_close(CloseDecision.DISCARD, SimpleNamespace(), SimpleNamespace(), "USA")

    assert panel._funding_draft["ground"] == 0.45
    assert panel._has_changes is False


def test_render_coordinates_snapshot_sync_window_and_dirty_close(monkeypatch):
    panel = UnitResearchPanel()
    tracks = [{"branch": "ground", "funding_ratio": 0.4}]
    panel._presenter.research_tracks_for_country = Mock(return_value=tracks)
    for method in (
        "_draw_frames", "_render_title_controls", "_render_categories",
        "_render_funding_controls", "_render_program_view", "_render_detail_tabs",
    ):
        setattr(panel, method, Mock())
    windows = []
    open_states = [True, True, True, False]

    @contextmanager
    def window(*args, **kwargs):
        windows.append((args, kwargs))
        yield open_states.pop(0)

    monkeypatch.setattr(module.WindowManager, "window", window)
    monkeypatch.setattr(module, "GMLWidgets", lambda _root: Ui())
    imgui = MagicMock()
    imgui.get_io.return_value.display_size = SimpleNamespace(x=1000.0, y=800.0)
    monkeypatch.setattr(module, "imgui", imgui)
    context = SimpleNamespace(
        target_tag=" usa ",
        is_own_country=True,
        net_client=Client(),
        save_confirmation_preferences=None,
    )
    state = SimpleNamespace(journal=SimpleNamespace(command_results=[]))

    assert panel.render(state, context) is True
    assert panel._draft_country_tag == "USA"
    assert windows[0][1]["x"] == 196.5
    panel._render_categories.assert_called_once()

    imgui.get_io.return_value.display_size = SimpleNamespace(x=0.0, y=0.0)
    imgui.get_main_viewport.return_value.size = SimpleNamespace(x=1280.0, y=720.0)
    panel._funding_draft["ground"] = 0.8
    panel.request_close()
    panel._close_confirmation.request_close = Mock(return_value=CloseDecision.DISCARD)
    panel._finish_close = Mock()

    assert panel.render(state, context) is False
    panel._close_confirmation.request_close.assert_called_once()
    panel._finish_close.assert_called_once_with(CloseDecision.DISCARD, state, context, "USA")
    imgui.get_main_viewport.assert_called()

    panel._funding_draft = panel._funding_baseline.copy()
    panel._close_confirmation.render = Mock(return_value=CloseDecision.DISCARD)
    assert panel.render(state, context) is False
    panel._close_confirmation.render.assert_called_once()
    assert panel._finish_close.call_count == 2

    assert panel.render(state, context) is False
