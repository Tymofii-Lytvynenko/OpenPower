from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from src.client.ui.core import instrumented_imgui as instrumentation
from src.client.ui.core.testability import Rect, UIRunTelemetry, set_widget_value
from src.client.ui.testing.driver import UITestDriver
from src.client.ui.testing.journey import (
    _assert_action,
    _assert_rect,
    _relative_rect_check_applies,
)
from src.client.ui.testing.layout_checks import analyze_layout


def test_journey_rectangle_assertion_checks_selected_source_dimensions():
    _assert_rect(
        {"x": 15.0, "y": 30.0, "width": 274.0, "height": 362.0},
        {"width": 274, "height": 362},
        tolerance=0.25,
    )


def test_journey_rectangle_assertion_reports_dimension_mismatch():
    with pytest.raises(AssertionError, match="Rectangle width"):
        _assert_rect({"x": 0.0, "y": 0.0, "width": 500.0, "height": 360.0},
                     {"width": 274.0, "height": 362.0})


def test_relative_geometry_can_be_limited_to_reference_viewports():
    step = {
        "relative_rect_min_viewport_width": 1280,
        "relative_rect_min_viewport_height": 720,
    }

    assert not _relative_rect_check_applies(step, (800, 600))
    assert not _relative_rect_check_applies(step, (1280, 600))
    assert _relative_rect_check_applies(step, (1280, 720))


class FakeImGui:
    def __init__(self):
        self.next_id = 1
        self.last_id = 0
        self.calls = []

    def begin(self, title):
        return True, True

    def end(self):
        pass

    def begin_child(self, title):
        return True

    def end_child(self):
        pass

    def begin_disabled(self, disabled=True):
        pass

    def end_disabled(self):
        pass

    def button(self, label):
        self.last_id = self.next_id
        self.calls.append(label)
        return False

    def checkbox(self, label, checked):
        self.last_id = self.next_id
        return False, checked

    def text(self, label):
        self.last_id = 0

    def get_window_pos(self):
        return SimpleNamespace(x=0, y=0)

    def get_window_size(self):
        return SimpleNamespace(x=200, y=200)

    def get_item_id(self):
        return self.last_id

    def get_item_rect_min(self):
        return SimpleNamespace(x=10, y=10)

    def get_item_rect_max(self):
        return SimpleNamespace(x=100, y=30)

    def is_item_visible(self):
        return True


@pytest.fixture
def facade(monkeypatch):
    native = FakeImGui()
    monkeypatch.setattr(instrumentation, "native_imgui", native)
    return instrumentation.ImGuiFacade(native)


def test_facade_preserves_native_behavior_when_recording_is_disabled(facade):
    assert facade.button("Save") is False
    assert facade._native.calls == ["Save"]


def test_cached_wrapper_resolves_a_replaced_native_function(facade, monkeypatch):
    facade.button("First")
    monkeypatch.setattr(facade._native, "button", lambda label: label == "Patched")
    assert facade.button("Patched") is True


def test_automatic_ids_survive_changed_labels_and_native_ids(facade):
    recorder = UIRunTelemetry((200, 200))
    ids = []
    for label in ("Save", "Save changes"):
        with recorder.frame():
            facade.begin("Window")
            facade.button(label)
            facade.end()
        ids.append(next(w["id"] for w in recorder.to_dict()["widgets"] if w["present"]))
        facade._native.next_id += 1
    assert ids[0] == ids[1]
    widget = recorder.widget(ids[1])
    assert widget["label"] == "Save changes"
    assert widget["imgui_id"] == 2
    assert widget["source"]["line"] > 0


def test_nested_regions_and_disabled_state_are_recorded(facade):
    recorder = UIRunTelemetry((200, 200))
    with recorder.frame():
        facade.begin("Window")
        facade.begin_child("Child")
        facade.begin_disabled()
        facade.checkbox("Toggle", True)
        facade.end_disabled()
        facade.end_child()
        facade.end()
    snapshot = recorder.to_dict()
    widget = snapshot["widgets"][0]
    assert widget["enabled"] is False
    assert widget["value"] is True
    child = next(r for r in snapshot["regions"] if r["kind"] == "child")
    assert widget["parent_id"] == child["id"]
    assert child["parent_id"] is not None


def test_custom_widget_value_can_update_after_native_item_recording():
    recorder = UIRunTelemetry((200, 200))
    with recorder.frame():
        recorder.record_widget("lock", "", "invisible_button", True, True, Rect(0, 0, 20, 20))
        set_widget_value("lock", True)
    assert recorder.widget("lock")["value"] is True


def test_removed_widgets_become_absent_instead_of_remaining_visible(facade):
    recorder = UIRunTelemetry((200, 200))
    with recorder.frame():
        facade.begin("Window")
        facade.button("Save")
        facade.end()
    widget_id = recorder.to_dict()["widgets"][0]["id"]
    with recorder.frame():
        facade.begin("Window")
        facade.end()
    widget = recorder.widget(widget_id)
    assert widget["present"] is False
    assert widget["visible"] is False
    assert widget["ever_visible"] is True


def test_selector_rejects_ambiguity(facade):
    recorder = UIRunTelemetry((200, 200))
    with recorder.frame():
        facade.begin("Window")
        facade.button("Save")
        facade._native.next_id = 2
        facade.button("Save")
        facade.end()
    with pytest.raises(ValueError, match="matched 2 widgets"):
        UITestDriver(None, recorder).find({"label": "Save", "type": "button"})


def test_action_assertion_accepts_an_expected_absence():
    _assert_action({"type": "ActionSave", "count": 0}, [])


def test_action_assertion_rejects_unexpected_absence():
    with pytest.raises(AssertionError, match="Unexpected count for ActionSave: 0"):
        _assert_action({"type": "ActionSave"}, [])


def test_action_assertion_still_checks_the_selected_payload():
    @dataclass
    class ActionSave:
        value: str

    with pytest.raises(AssertionError, match="value: expected 'new', received 'old'"):
        _assert_action({"type": "ActionSave", "fields": {"value": "new"}}, [ActionSave("old")])


def test_layout_diagnostics_detect_invalid_geometry_and_viewport_overflow():
    snapshot = {"viewport": {"width": 100, "height": 100}, "widgets": [],
                "regions": [{"id": "window", "kind": "window", "visible": True,
                             "rect": Rect(90, 90, 50, 50).to_dict()}]}
    assert analyze_layout(snapshot)[0]["code"] == "window_outside_viewport"
    snapshot["regions"][0]["rect"]["width"] = -1
    assert "invalid_geometry" in [f["code"] for f in analyze_layout(snapshot)]


def test_layout_diagnostics_detect_text_over_disabled_actions():
    snapshot = {"viewport": {"width": 200, "height": 200}, "regions": [], "widgets": [
        {"id": "live_status", "type": "text_disabled", "visible": True, "enabled": True,
         "parent_id": "military", "rect": Rect(20, 20, 100, 12).to_dict()},
        {"id": "buy", "type": "button", "interactive": True, "visible": True, "enabled": False,
         "parent_id": "military", "rect": Rect(20, 25, 100, 18).to_dict()},
    ]}
    assert any(f["code"] == "text_overlap" and f["severity"] == "error" for f in analyze_layout(snapshot))
    snapshot["widgets"][1]["parent_id"] = "another_window"
    assert not analyze_layout(snapshot)


@pytest.mark.parametrize('opened, expected', [(False, ['begin', 'end']), (True, ['begin'])])
def test_disabled_conditional_container_keeps_scope_only_when_open(facade, monkeypatch, opened, expected):
    calls = []
    monkeypatch.setattr(facade, 'begin_disabled', lambda value: calls.append('begin'))
    monkeypatch.setattr(facade, 'end_disabled', lambda: calls.append('end'))
    result = facade._invoke_unclipped(
        'begin_combo', lambda: opened, (), {}, SimpleNamespace(enabled=False),
    )
    assert result is opened
    assert calls == expected


def test_disabled_widget_restores_scope_when_native_call_raises(facade, monkeypatch):
    calls = []
    monkeypatch.setattr(facade, 'begin_disabled', lambda value: calls.append('begin'))
    monkeypatch.setattr(facade, 'end_disabled', lambda: calls.append('end'))

    def fail():
        raise RuntimeError('native failure')

    with pytest.raises(RuntimeError, match='native failure'):
        facade._invoke_unclipped('button', fail, (), {}, SimpleNamespace(enabled=False))
    assert calls == ['begin', 'end']


@pytest.mark.parametrize('name', ['text', 'text_wrapped'])
def test_gml_text_clipping_restores_native_stacks_after_failure(facade, name):
    calls = []
    facade._native = SimpleNamespace(
        get_scroll_x=lambda: 0, get_scroll_y=lambda: 0,
        get_cursor_pos_x=lambda: 0,
        push_clip_rect=lambda *args: calls.append('clip'),
        pop_clip_rect=lambda: calls.append('unclip'),
        push_text_wrap_pos=lambda *args: calls.append('wrap'),
        pop_text_wrap_pos=lambda: calls.append('unwrap'),
    )
    session = SimpleNamespace(
        window_position=(10, 20), rect_for=lambda component: Rect(0, 0, 100, 14),
    )
    component = SimpleNamespace(enabled=True, text_offset=(0, 0))

    def fail():
        raise RuntimeError('text failure')

    with pytest.raises(RuntimeError, match='text failure'):
        facade._invoke_layout_widget(name, fail, (), {}, session, component)
    expected = ['clip', 'wrap', 'unwrap', 'unclip'] if name == 'text_wrapped' else ['clip', 'unclip']
    assert calls == expected
