from types import SimpleNamespace

import pytest

from src.client.ui.core import instrumented_imgui as instrumentation
from src.client.ui.core.testability import Rect, UIRunTelemetry


class FakeNative:
    def __init__(self):
        self.item_id = 7
        self.visible = True
        self.calls = []
        self.id_count = 0
        self.draw_list = SimpleNamespace(add_rect=lambda *args, **kwargs: "rect")
        self.constant = 42

    def get_item_id(self):
        return self.item_id

    def get_id(self, label):
        self.id_count += 1
        return 100 + self.id_count

    def get_item_rect_min(self):
        return SimpleNamespace(x=10, y=10)

    def get_item_rect_max(self):
        return SimpleNamespace(x=100, y=30)

    def get_window_pos(self):
        return SimpleNamespace(x=2, y=3)

    def get_window_size(self):
        return SimpleNamespace(x=200, y=150)

    def get_style(self):
        return SimpleNamespace(item_inner_spacing=SimpleNamespace(x=4))

    def is_item_visible(self):
        return self.visible

    def get_scroll_x(self):
        return 0

    def get_scroll_y(self):
        return 0

    def get_cursor_pos_x(self):
        return 0

    def calc_text_size(self, value):
        return SimpleNamespace(x=len(value) * 5, y=10)

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == "begin":
                return True, True
            if name in {"begin_child", "begin_tooltip", "begin_group"}:
                return True
            if name.startswith("begin_"):
                return False
            if name == "button":
                return True
            if name == "checkbox":
                return False, kwargs.get("checked", False)
            if name == "get_window_draw_list":
                return self.draw_list
            if name == "set_tooltip":
                return "native-tooltip"
            return None

        return call


@pytest.fixture
def facade():
    return instrumentation.ImGuiFacade(FakeNative())


def test_cached_site_id_falls_back_when_source_cannot_be_parsed(monkeypatch):
    instrumentation._cached_site_id.cache_clear()
    monkeypatch.setattr(
        instrumentation,
        "_sites",
        lambda _path: (_ for _ in ()).throw(OSError("unavailable")),
    )

    assert instrumentation._cached_site_id("missing.py", 17, "button") == "missing.py/17/button"


def test_label_uses_keyword_fallbacks_and_text_colored_argument_position():
    assert instrumentation._label("button", (), {"name": "Save"}) == "Save"
    assert instrumentation._label("button", (), {"str_id": "Cancel"}) == "Cancel"
    assert instrumentation._label("text_colored", ((1, 1, 1), "Status"), {}) == "Status"


def test_tutorial_anchor_filters_targets_and_records_visible_display_geometry(monkeypatch):
    native = FakeNative()
    recorded = []
    monkeypatch.setattr(instrumentation.UIAnchorRegistry, "is_target", lambda item: item == "target")
    monkeypatch.setattr(instrumentation.UIAnchorRegistry, "record", lambda *args: recorded.append(args))

    instrumentation._record_tutorial_anchor(native, "text", "other")
    instrumentation._record_tutorial_anchor(native, "unknown", "target")
    native.visible = False
    instrumentation._record_tutorial_anchor(native, "button", "target")
    native.visible = True
    instrumentation._record_tutorial_anchor(native, "text", "target")

    assert recorded == [("target", 10.0, 10.0, 90.0, 20.0)]


def test_record_item_handles_scalar_ids_clipping_and_unsupported_values(monkeypatch):
    native = FakeNative()
    native.item_id = 0
    recorder = UIRunTelemetry((200, 150))
    value = object()
    monkeypatch.setattr(instrumentation.UIAnchorRegistry, "is_target", lambda _item: False)

    with recorder.frame():
        instrumentation._record_item(
            recorder,
            "input_int",
            "Age##age",
            {"path": "tests/test_instrumented_imgui_branch_coverage.py", "line": 1},
            (False, value),
            layout_enabled=False,
            layout_clip_rect=Rect(20, 0, 60, 15),
            native=native,
        )

    widget = recorder.to_dict()["widgets"][0]
    assert widget["label"] == "Age"
    assert widget["imgui_id"] == 101
    assert widget["interactive"] is True
    assert widget["enabled"] is False
    assert widget["value"] == str(value)
    assert widget["rect"] == Rect(20, 10, 60, 5).to_dict()


def test_record_item_records_options_and_vector_component_geometry(monkeypatch):
    native = FakeNative()
    recorder = UIRunTelemetry((200, 150))
    monkeypatch.setattr(instrumentation.UIAnchorRegistry, "is_target", lambda _item: False)

    with recorder.frame():
        instrumentation._record_item(
            recorder,
            "input_int3",
            "Position",
            {"path": "tests/test_instrumented_imgui_branch_coverage.py", "line": 2},
            None,
            component_width=100,
            native=native,
        )
        instrumentation._record_item(
            recorder,
            "combo",
            "Mode",
            {"path": "tests/test_instrumented_imgui_branch_coverage.py", "line": 3},
            (True, 1),
            explicit_id="mode",
            options=["Fast", "Safe"],
            native=native,
        )

    widgets = recorder.to_dict()["widgets"]
    vector = next(item for item in widgets if item["type"] == "input_int3")
    combo = next(item for item in widgets if item["id"] == "mode")
    assert [part["rect"]["x"] for part in vector["components"]] == [10, 44, 78]
    assert combo["options"] == ["Fast", "Safe"]


def test_tooltip_delegates_native_arguments_and_renders_gml_text(monkeypatch, facade):
    calls = []
    from src.client.ui.core import gml_tooltip

    monkeypatch.setattr(gml_tooltip, "render_gml_tooltip", lambda native, text: calls.append((native, text)) or "gml")

    assert facade.set_tooltip("native", 0.5) == "native-tooltip"
    assert facade.set_tooltip(None) is None
    assert facade.set_tooltip("") is None
    assert facade.set_tooltip("help") == "gml"
    assert calls == [(facade._native, "help")]


def test_container_layout_and_disabled_scopes_resume_only_matching_ends(monkeypatch, facade):
    from src.client.ui.layouts import gml_layout

    resumed = []
    monkeypatch.setattr(gml_layout, "suspend_gml_layout", lambda: "token")
    monkeypatch.setattr(gml_layout, "resume_gml_layout", lambda token: resumed.append(token))
    ended = []
    monkeypatch.setattr(facade, "end_disabled", lambda: ended.append("end"))

    facade._suspend_layout_for_container("begin_combo", True, SimpleNamespace(enabled=False))
    facade._resume_layout_after_container("end_popup")
    facade._end_disabled_container("end_popup")
    assert len(facade._layout_suspensions) == 1
    assert len(facade._container_disabled_scopes) == 1

    facade._resume_layout_after_container("end_combo")
    facade._end_disabled_container("end_combo")
    assert resumed == ["token"]
    assert ended == ["end"]


def test_container_helpers_ignore_noncontainers_and_closed_conditional_containers(monkeypatch, facade):
    from src.client.ui.layouts import gml_layout

    monkeypatch.setattr(gml_layout, "suspend_gml_layout", lambda: "token")
    facade._suspend_layout_for_container("button", True)
    facade._suspend_layout_for_container("begin_group", True)
    facade._suspend_layout_for_container("begin_combo", False)
    assert facade._layout_suspensions == []


def test_finish_recorded_container_refreshes_geometry_or_reports_imbalance(facade):
    recorder = UIRunTelemetry((200, 150))
    with recorder.frame():
        recorder.record_region("table", "Stats", True, Rect(0, 0, 1, 1), kind="table")
        recorder.push_region("table")
        recorder._containers.append(("end_table", "table", "table"))
        facade._finish_recorded_container("end_table", recorder, {"path": "test.py"})
        facade._finish_recorded_container("end_table", recorder, {"path": "test.py"})

    assert recorder.region("table")["rect"] == Rect(10, 10, 90, 20).to_dict()
    assert recorder.errors[-1]["message"] == "Unbalanced container: end_table"


def test_record_container_handles_combo_item_and_closed_child_region(facade, monkeypatch):
    recorder = UIRunTelemetry((200, 150))
    monkeypatch.setattr(instrumentation.UIAnchorRegistry, "is_target", lambda _item: False)

    with recorder.frame():
        facade._record_container(
            "begin_combo", recorder, "Mode", {"path": "test.py", "line": 1}, False, None, None
        )
        facade._record_container(
            "begin_child", recorder, "Rows##row", {"path": "test.py", "line": 2}, False, "rows", None
        )

    assert recorder.region("rows/row")["visible"] is False
    assert any(widget["type"] == "begin_combo" for widget in recorder.to_dict()["widgets"])


def test_disabled_conditional_container_restores_scope_on_exception(facade, monkeypatch):
    calls = []
    monkeypatch.setattr(facade, "begin_disabled", lambda value: calls.append(("begin", value)))
    monkeypatch.setattr(facade, "end_disabled", lambda: calls.append(("end",)))

    with pytest.raises(RuntimeError, match="native failure"):
        facade._invoke_unclipped(
            "begin_combo",
            lambda: (_ for _ in ()).throw(RuntimeError("native failure")),
            (),
            {},
            SimpleNamespace(enabled=False),
        )

    assert calls == [("begin", True), ("end",)]


def test_wrapper_records_explicit_ids_and_keyword_labels(facade):
    recorder = UIRunTelemetry((200, 150))

    with recorder.frame():
        facade.button("Save###native", test_id="save")
        facade.checkbox(checked=False, label="Toggle###native", test_id="toggle")

    assert facade._native.calls[0][1][0] == "Save###save"
    assert dict(facade._native.calls[1][2])["label"] == "Toggle###toggle"
    assert {item["id"] for item in recorder.to_dict()["widgets"]} == {"save", "toggle"}


def test_wrapper_handles_id_scopes_disabled_scopes_and_containers(facade):
    recorder = UIRunTelemetry((200, 150))
    with recorder.frame():
        facade.begin("Window")
        facade.push_id("row")
        facade.button("Open")
        facade.pop_id()
        facade.pop_id()
        facade.begin_disabled(False)
        facade.button("Enabled")
        facade.end_disabled()
        facade.end_disabled()
        facade.end()

    assert recorder._id_stack == []
    assert recorder._disabled == []
    assert recorder.to_dict()["regions"][0]["label"] == "Window"


def test_wrapper_captures_combo_options_and_draw_list(facade):
    recorder = UIRunTelemetry((200, 150))
    with recorder.frame():
        facade.combo("Mode", 0, ["Fast", 2])
        facade.list_box("Preset", 0, "One\0Two\0")
        draw = facade.get_window_draw_list()
        assert draw.add_rect((1, 2), (8, 9), 1) == "rect"

    widgets = recorder.to_dict()["widgets"]
    assert next(item for item in widgets if item["label"] == "Mode")["options"] == ["Fast", "2"]
    assert next(item for item in widgets if item["label"] == "Preset")["options"] == ["One", "Two"]
    assert any(item["type"] == "add_rect" for item in widgets)


def test_wrapper_applies_gml_placement_and_vector_width(monkeypatch, facade):
    from src.client.ui.layouts import gml_layout

    placements = []
    component = SimpleNamespace(enabled=False)

    def place_widget(name, args, **kwargs):
        placements.append((name, args, kwargs))
        if name == "button":
            return args, component
        if name == "input_int2":
            return args, SimpleNamespace(enabled=True)
        return None

    layout = SimpleNamespace(
        place_widget=place_widget
    )
    monkeypatch.setattr(gml_layout, "active_gml_layout", lambda: layout)
    monkeypatch.setattr(instrumentation.native_imgui, "calc_item_width", lambda: 100, raising=False)
    recorder = UIRunTelemetry((200, 150))

    with recorder.frame():
        facade.button("Place", gml_id="gml.place", gml_align="right", gml_enabled=False)
        facade.input_int2("Position", (0, 0))

    placed = next(item for item in recorder.to_dict()["widgets"] if item["label"] == "Place")
    assert placed["enabled"] is False
    assert placements[0][2] == {"explicit_id": "gml.place", "align": "right", "enabled_override": False}
    assert any(item["type"] == "input_int2" for item in recorder.to_dict()["widgets"])


def test_wrapper_returns_unobserved_attributes_and_handles_empty_layout_placement(monkeypatch, facade):
    from src.client.ui.layouts import gml_layout

    monkeypatch.setattr(gml_layout, "active_gml_layout", lambda: SimpleNamespace(place_widget=lambda *args, **kwargs: None))
    assert facade.constant == 42
    recorder = UIRunTelemetry((200, 150))
    with recorder.frame():
        facade.button("Flow")
        assert facade.unobserved_call("value") is None


def test_unrecorded_end_wrapper_resumes_matching_layout_and_disabled_scopes(monkeypatch, facade):
    from src.client.ui.layouts import gml_layout

    resumed = []
    ended = []
    monkeypatch.setattr(gml_layout, "resume_gml_layout", lambda token: resumed.append(token))
    monkeypatch.setattr(facade, "end_disabled", lambda: ended.append("disabled"))
    facade._layout_suspensions.append(("end_combo", "token"))
    facade._container_disabled_scopes.append(("end_combo", True))

    facade.end_combo()

    assert resumed == ["token"]
    assert ended == ["disabled"]


def test_draw_list_facade_records_text_bounds_and_passes_through_other_attributes():
    native = FakeNative()
    recorder = UIRunTelemetry((200, 150))
    draw_list = SimpleNamespace(add_text=lambda *args: "text", clear=lambda: "clear")
    facade = instrumentation.DrawListFacade(draw_list, recorder, native)

    assert facade.clear() == "clear"
    with recorder.frame():
        assert facade.add_text((5, 7), 1, "Hi") == "text"
        facade.add_text("no geometry")

    text = next(item for item in recorder.to_dict()["widgets"] if item["type"] == "add_text")
    assert text["rect"] == Rect(5, 7, 10, 10).to_dict()
