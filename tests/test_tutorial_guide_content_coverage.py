from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import src.client.ui.components.tutorial_guide_content as tutorial_module
from src.client.ui.components.tutorial_guide_content import (
    TutorialGuideContent,
    TutorialGuideLayout,
    TutorialStep,
    resolve_tutorial_guide_layout,
)


def _imgui_mock(monkeypatch):
    imgui = Mock()
    imgui.calc_text_size.return_value = SimpleNamespace(y=20.0)
    imgui.get_cursor_pos_x.return_value = 10.0

    @contextmanager
    def semantic_region(*_args, **_kwargs):
        yield

    monkeypatch.setattr(tutorial_module, "imgui", imgui)
    monkeypatch.setattr(tutorial_module, "semantic_region", semantic_region)
    return imgui


def test_closed_guide_properties_and_unknown_guide():
    content = TutorialGuideContent()

    assert content.is_open is False
    assert content.title == "TUTORIAL"
    assert content.arrow_target is None
    assert content.arrow_targets == ()
    assert content.window_size(window_width=320.0) == (320.0, 180.0)
    content.on_interaction("mini_map.navigate")
    content.advance_if_ready(lambda _panel_id: True)

    with pytest.raises(ValueError, match="Unknown tutorial guide"):
        content.open("unknown")


def test_open_guide_exposes_fallback_targets_and_width_sensitive_layout(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    content = TutorialGuideContent()
    content.open("interface")
    assert content.arrow_targets == ("world.viewport",)
    assert content.window_size(window_width=350.0) == (
        350.0,
        resolve_tutorial_guide_layout(20.0, window_width=350.0).window_height,
    )

    content._step_index = 1
    assert content.arrow_target == "mini_map.map"
    assert content.arrow_targets == ("mini_map.map", "world.viewport")

    content.open("military")
    _, height = content.window_size(lambda _panel_id: False, window_width=300.0)
    assert height == resolve_tutorial_guide_layout(20.0, 20.0, 300.0).window_height
    assert imgui.calc_text_size.call_count == 3


def test_interaction_advances_only_the_matching_active_step(monkeypatch):
    content = TutorialGuideContent()
    content.open("interface")
    content._step_index = 1

    content.on_interaction("mini_map.zoom")
    assert content._step_index == 1
    content.on_interaction("mini_map.navigate")
    assert content._step_index == 2

    title, steps = tutorial_module._GUIDES["interface"]
    final_step = replace(steps[-1], advance_on_interaction="final-action")
    monkeypatch.setitem(tutorial_module._GUIDES, "final-action", (title, (final_step,)))
    content.open("final-action")
    content.on_interaction("final-action")
    assert content._step_index == 0


def test_advance_if_ready_requires_auto_advance_and_matching_panel_state(monkeypatch):
    content = TutorialGuideContent()
    content.open("interface")
    content.advance_if_ready(lambda _panel_id: True)
    assert content._step_index == 0

    content.open("military")
    content.advance_if_ready(lambda _panel_id: False)
    assert content._step_index == 0
    content.advance_if_ready(lambda _panel_id: True)
    assert content._step_index == 1

    manual_step = TutorialStep("manual", "body", (("PANEL", True),), auto_advance=False)
    monkeypatch.setitem(tutorial_module._GUIDES, "manual", ("MANUAL", (manual_step,)))
    content.open("manual")
    content.advance_if_ready(lambda _panel_id: True)
    assert content.is_open is True

    final_step = TutorialStep("final", "body", (("PANEL", True),))
    monkeypatch.setitem(tutorial_module._GUIDES, "final", ("FINAL", (final_step,)))
    content.open("final")
    content.advance_if_ready(lambda _panel_id: True)
    assert content.is_open is False


def test_requirements_and_status_report_ready_or_waiting():
    step = TutorialStep("step", "body", (("A", True), ("B", False)))

    assert TutorialGuideContent._requirements_satisfied(step, None) is True
    assert TutorialGuideContent._requirements_satisfied(
        TutorialStep("step", "body"), lambda _panel_id: False,
    ) is True
    visible = {"A": True, "B": False}
    callback = lambda panel_id: visible[panel_id]
    assert TutorialGuideContent._requirements_satisfied(step, callback) is True
    assert TutorialGuideContent._status_text(step, callback) == "Ready"

    visible["B"] = True
    assert TutorialGuideContent._requirements_satisfied(step, callback) is False
    assert TutorialGuideContent._status_text(step, callback) == "Waiting for the requested panel state"


def test_render_emits_body_and_optional_requirement_status(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    content = TutorialGuideContent()
    on_close = Mock()

    content.render(on_close)
    imgui.text_colored.assert_not_called()

    content.open("interface")
    content._render_navigation_controls = Mock()
    content.render(on_close, test_id_prefix="guide", window_width=300.0)
    assert imgui.text_colored.call_count == 2
    imgui.text_wrapped.assert_called_once()
    assert imgui.push_text_wrap_pos.call_count == 1
    assert imgui.pop_text_wrap_pos.call_count == 1
    content._render_navigation_controls.assert_called_once()

    imgui.reset_mock()
    content.open("military")
    content._render_navigation_controls.reset_mock()
    content.render(on_close, panel_visible_cb=lambda _panel_id: False)
    assert imgui.text_colored.call_count == 3
    assert any(call.args[1] == "Waiting for the requested panel state" for call in imgui.text_colored.call_args_list)
    assert imgui.push_text_wrap_pos.call_count == 2
    assert imgui.pop_text_wrap_pos.call_count == 2


def test_navigation_controls_handle_stacked_regular_and_finish_flows(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    content = TutorialGuideContent()
    on_close = Mock()
    content._step_index = 2
    content._render_previous_button = Mock(return_value=True)
    content._render_next_button = Mock(return_value=False)
    imgui.button.return_value = True
    stacked = TutorialGuideLayout(None, 100.0, True, 200.0)

    content._render_navigation_controls(stacked, 300.0, True, on_close, "guide", 8)

    on_close.assert_called_once_with()
    assert content._step_index == 1
    content._render_previous_button.assert_called_once_with(276.0, "guide")
    content._render_next_button.assert_called_once_with(276.0, True, "guide", 8)

    imgui.reset_mock()
    on_close.reset_mock()
    imgui.button.return_value = False
    content._step_index = 2
    content._render_previous_button.return_value = True
    content._render_next_button.return_value = False
    regular = TutorialGuideLayout(None, 100.0, False, 160.0)
    content._render_navigation_controls(regular, 400.0, False, on_close, "guide", 8)
    assert content._step_index == 1
    assert imgui.same_line.call_count == 2
    content._render_previous_button.assert_called_with(108.0, "guide")
    content._render_next_button.assert_called_with(108.0, False, "guide", 8)

    content._step_index = 2
    content._render_previous_button.return_value = False
    content._render_next_button.return_value = True
    content._render_navigation_controls(regular, 400.0, True, on_close, "guide", 8)
    assert content._step_index == 3

    imgui.button.return_value = True
    content._render_next_button.return_value = False
    content._render_navigation_controls(regular, 400.0, True, on_close, "guide", 8)
    on_close.assert_called_once_with()
    on_close.reset_mock()

    imgui.button.return_value = False
    content._step_index = 7
    content._render_previous_button.return_value = False
    content._render_next_button.return_value = True
    content._render_navigation_controls(regular, 400.0, True, on_close, "guide", 8)
    on_close.assert_called_once_with()


def test_previous_and_next_controls_always_restore_disabled_state(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    content = TutorialGuideContent()
    imgui.button.return_value = True

    assert content._render_previous_button(108.0, "guide") is True
    imgui.begin_disabled.assert_called_once_with(True)
    imgui.end_disabled.assert_called_once_with()

    imgui.reset_mock()
    content._step_index = 1
    assert content._render_next_button(108.0, False, "guide", 3) is True
    imgui.begin_disabled.assert_called_once_with(True)
    imgui.button.assert_called_once_with(
        "NEXT", (108.0, tutorial_module.TUTORIAL_GUIDE_BUTTON_HEIGHT),
        test_id="guide.tutorial.next",
    )
    imgui.end_disabled.assert_called_once_with()

    imgui.reset_mock()
    content._step_index = 2
    content._render_next_button(108.0, True, "guide", 3)
    imgui.button.assert_called_once_with(
        "FINISH", (108.0, tutorial_module.TUTORIAL_GUIDE_BUTTON_HEIGHT),
        test_id="guide.tutorial.next",
    )
