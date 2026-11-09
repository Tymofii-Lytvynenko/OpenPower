import sys
from types import SimpleNamespace

from src.client.ui.core import testability
from src.client.ui.core.testability import Rect, UIRunTelemetry


def test_duplicate_semantic_widget_ids_are_reported_once_per_frame() -> None:
    recorder = UIRunTelemetry((100, 100))

    with recorder.frame():
        for _ in range(2):
            recorder.record_widget("save", "Save", "button", True, True, Rect(1, 2, 3, 4))

    assert recorder.to_dict()["errors"] == [
        {"source": "save", "message": "Duplicate semantic widget ID in one frame."}
    ]


def test_record_last_item_replaces_automatic_widget_and_keeps_anchor_geometry(monkeypatch) -> None:
    recorder = UIRunTelemetry((100, 100))
    rect_min = SimpleNamespace(x=10, y=20)
    rect_max = SimpleNamespace(x=50, y=36)
    imgui = SimpleNamespace(
        get_item_rect_min=lambda: rect_min,
        get_item_rect_max=lambda: rect_max,
        is_item_visible=lambda: True,
        get_item_id=lambda: 7,
    )
    monkeypatch.setitem(sys.modules, "imgui_bundle", SimpleNamespace(imgui=imgui))
    anchors = []
    monkeypatch.setattr(
        testability.UIAnchorRegistry,
        "is_target",
        staticmethod(lambda test_id: test_id == "anchor"),
    )
    monkeypatch.setattr(
        testability.UIAnchorRegistry,
        "record",
        staticmethod(lambda *args: anchors.append(args)),
    )

    with recorder.frame():
        recorder.record_widget(
            "auto/7",
            "Native button",
            "button",
            True,
            False,
            Rect(10, 20, 40, 16),
            imgui_id=7,
            source={"line": 42},
            value="draft",
        )
        recorder.set_components("auto/7", [{"id": "amount"}])
        recorder.set_options("auto/7", ["draft", "final"])
        testability.record_last_item("save", "Save", "button")

    widget = recorder.widget("save")
    assert recorder.widget("auto/7") is None
    assert widget["enabled"] is False
    assert widget["rect"] == {"x": 10, "y": 20, "width": 40, "height": 16}
    assert widget["source"] == {"line": 42}
    assert widget["value"] == "draft"
    assert widget["components"] == [{"id": "amount"}]
    assert widget["options"] == ["draft", "final"]
    assert anchors == []

    testability.record_last_item("anchor", "Anchor", "button")
    assert anchors == [("anchor", 10.0, 20.0, 40.0, 16.0)]


def test_automatic_item_replacement_ignores_a_stale_mapping() -> None:
    recorder = UIRunTelemetry((100, 100))
    recorder._automatic_by_native[9] = ["auto/stale"]

    assert recorder.replace_automatic_item(9) == {}
