from types import SimpleNamespace

import pytest

from src.client.ui.core import instrumented_imgui as instrumentation
from src.client.ui.core.testability import Rect, UIRunTelemetry
from src.client.ui.testing.driver import UITestDriver
from src.client.ui.testing.layout_checks import analyze_layout


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


def test_layout_diagnostics_detect_invalid_geometry_and_viewport_overflow():
    snapshot = {"viewport": {"width": 100, "height": 100}, "widgets": [],
                "regions": [{"id": "window", "kind": "window", "visible": True,
                             "rect": Rect(90, 90, 50, 50).to_dict()}]}
    assert analyze_layout(snapshot)[0]["code"] == "window_outside_viewport"
    snapshot["regions"][0]["rect"]["width"] = -1
    assert "invalid_geometry" in [f["code"] for f in analyze_layout(snapshot)]
