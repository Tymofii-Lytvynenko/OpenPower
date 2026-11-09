from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.components.shared.country_profile_window as profile_module
from src.client.services.country_profile import CountryProfileCandidate
from src.client.ui.components.shared.country_profile_window import CountryProfileWindow


def _imgui_mock(monkeypatch, *, checkboxes=None, hovered=None, selections=None, buttons=None,
                child_open=True):
    imgui = Mock()
    imgui.begin_child.return_value = child_open
    imgui.checkbox.side_effect = checkboxes or [(False, True)] * 3
    imgui.is_item_hovered.side_effect = hovered or [False] * 6
    imgui.selectable.side_effect = selections or [(False, False)]
    imgui.button.side_effect = buttons or [False, False]
    monkeypatch.setattr(profile_module, "imgui", imgui)
    return imgui


def _widgets_mock(monkeypatch, *, sliders=None, buttons=None):
    ui = Mock()
    ui.path.side_effect = lambda path: path
    ui.meter_slider.side_effect = sliders or [(False, 0.5)] * 3
    ui.button.side_effect = buttons or [False, False]
    monkeypatch.setattr(profile_module, "GMLWidgets", Mock(return_value=ui))
    return ui


def _candidate():
    return CountryProfileCandidate(
        country_id="USA",
        name="United States",
        economic_rank=1,
        political_rank=2,
        military_rank=3,
        distance=0.0,
    )


def test_show_filters_eligible_countries_and_handles_missing_tables(monkeypatch):
    window = CountryProfileWindow(Mock())
    assert window.is_open is False

    window.show(SimpleNamespace(tables={}), ["usa"])
    assert window._country_rows == []
    assert window.is_open is True

    empty_table = SimpleNamespace(is_empty=Mock(return_value=True), columns=["id"])
    window.show(SimpleNamespace(tables={"countries": empty_table}), ["usa"])
    assert window._country_rows == []

    missing_id_table = SimpleNamespace(is_empty=Mock(return_value=False), columns=["name"])
    window.show(SimpleNamespace(tables={"countries": missing_id_table}), ["usa"])
    assert window._country_rows == []

    countries = SimpleNamespace(
        is_empty=Mock(return_value=False),
        columns=["id", "name"],
        to_dicts=Mock(return_value=[
            {"id": "usa", "name": "Old name"},
            {"id": "can", "name": "Canada"},
        ]),
    )
    state = SimpleNamespace(tables={"countries": countries})
    resolve_name = Mock(side_effect=lambda _state, tag: f"resolved-{tag}")
    monkeypatch.setattr(profile_module, "resolve_country_name", resolve_name)

    window.show(state, [" USA "])

    assert window._country_rows == [{"id": "USA", "name": "resolved-USA"}]
    resolve_name.assert_called_once_with(state, "USA")
    assert window._selected_country_id is None
    assert window._ranking_dirty is True
    window.close()
    assert window.is_open is False


def test_render_skips_closed_window_renders_open_window_and_closes_on_x(monkeypatch):
    state = {"open": True}

    @contextmanager
    def window_context(*_args, **_kwargs):
        yield state["open"]

    monkeypatch.setattr(profile_module.WindowManager, "window", window_context)
    panel = CountryProfileWindow(Mock())
    panel._render_content = Mock()

    panel.render(1280, 720)
    assert panel._render_content.call_count == 0

    panel.show(SimpleNamespace(tables={}), [])
    panel.render(1280, 720)
    assert panel._render_content.call_count == 1
    state["open"] = False
    panel.render(1280, 720)
    assert panel._render_content.call_count == 1
    assert panel.is_open is False


def test_content_shows_empty_state_and_cancel_closes_window(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    ui = _widgets_mock(monkeypatch, buttons=[False, True])
    suggest = Mock(return_value=[])
    monkeypatch.setattr(profile_module, "suggest_country_profiles", suggest)
    on_confirm = Mock()
    panel = CountryProfileWindow(on_confirm)
    panel._open = True

    panel._render_content()

    suggest.assert_called_once_with([], panel._desired_values, panel._enabled_metrics)
    imgui.text_disabled.assert_called_once_with("No eligible countries.")
    assert panel.is_open is False
    assert panel._selected_country_id is None
    on_confirm.assert_not_called()
    assert ui.meter.call_count == 3
    assert all(call.args[1] == 0.0 for call in ui.meter.call_args_list)


def test_metric_changes_clear_selection_recompute_and_allow_candidate_selection(monkeypatch):
    imgui = _imgui_mock(
        monkeypatch,
        checkboxes=[(True, False), (False, True), (False, True)],
        hovered=[True, False, False, True, False, False],
        selections=[(True, False)],
    )
    ui = _widgets_mock(monkeypatch, sliders=[(True, 0.8), (False, 0.5), (False, 0.5)])
    candidate = _candidate()
    suggest = Mock(return_value=[candidate])
    monkeypatch.setattr(profile_module, "suggest_country_profiles", suggest)
    panel = CountryProfileWindow(Mock())
    panel._country_rows = [
        {"id": "USA", "name": "United States"},
        {"id": "CAN", "name": "Canada"},
        {"id": "MEX", "name": "Mexico"},
    ]
    panel._selected_country_id = "USA"
    panel._ranking_dirty = False

    panel._render_content()

    assert panel._enabled_metrics["economic"] is False
    assert panel._desired_values["economic"] == 0.8
    assert panel._selected_country_id == "USA"
    assert panel._ranking_dirty is False
    suggest.assert_called_once_with(panel._country_rows, panel._desired_values, panel._enabled_metrics)
    assert imgui.set_tooltip.call_count == 2
    assert imgui.selectable.call_args.kwargs["test_id"] == "new_game.profile.candidate.USA"
    assert ui.meter_slider.call_count == 3


def test_selected_candidate_confirms_and_renders_rank_values(monkeypatch):
    imgui = _imgui_mock(monkeypatch, selections=[(False, False)])
    ui = _widgets_mock(monkeypatch, buttons=[True, False])
    suggest = Mock()
    monkeypatch.setattr(profile_module, "suggest_country_profiles", suggest)
    candidate = _candidate()
    on_confirm = Mock()
    panel = CountryProfileWindow(on_confirm)
    panel._country_rows = [
        {"id": "USA", "name": "United States"},
        {"id": "CAN", "name": "Canada"},
        {"id": "MEX", "name": "Mexico"},
    ]
    panel._candidates = [candidate]
    panel._selected_country_id = "USA"
    panel._ranking_dirty = False
    panel._open = True

    panel._render_content()

    suggest.assert_not_called()
    on_confirm.assert_called_once_with("USA")
    assert panel.is_open is False
    assert [call.args[1] for call in ui.meter.call_args_list] == [1.0, 2 / 3, 1 / 3]
    imgui.end_child.assert_called_once_with()
