from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.client.ui.testing import driver as driver_module
from src.client.ui.testing.driver import UITestDriver


class FakeTestRef:
    def __init__(self, item_id):
        self.id = item_id


class FakeTelemetry:
    def __init__(self):
        self.widgets = {}
        self.regions = {}
        self.movable_window_ids = set()
        self.snapshot = {"widgets": [], "regions": []}

    def widget(self, test_id):
        return self.widgets.get(test_id)

    def region(self, region_id):
        return self.regions.get(region_id)

    def to_dict(self):
        return self.snapshot


def make_widget(*, parent="panel", imgui_id=7, widget_type="button", enabled=True,
                visible=True, present=True, rect=None, **extra):
    value = {
        "id": "save", "present": present, "visible": visible, "enabled": enabled,
        "interactive": True, "imgui_id": imgui_id, "type": widget_type,
        "label": "Save", "parent_id": parent,
        "rect": rect or {"x": 10.0, "y": 20.0, "width": 40.0, "height": 20.0},
    }
    value.update(extra)
    return value


def setup(monkeypatch):
    telemetry = FakeTelemetry()
    telemetry.regions["panel"] = {
        "id": "panel", "present": True, "visible": True, "kind": "window",
        "label": "Panel", "rect": {"x": 0, "y": 0, "width": 200, "height": 200},
    }
    context = MagicMock()
    native = SimpleNamespace(
        test_engine=SimpleNamespace(TestRef=FakeTestRef),
        ImVec2=lambda x, y: SimpleNamespace(x=x, y=y),
    )
    monkeypatch.setattr(driver_module, "imgui", native)
    return UITestDriver(context, telemetry), context, telemetry


def test_resolution_and_matching_support_exact_and_semantic_selectors(monkeypatch):
    driver, _context, telemetry = setup(monkeypatch)
    telemetry.widgets["save"] = make_widget()
    telemetry.snapshot = {
        "widgets": [
            {"id": "save", "present": True, "label": "Save", "type": "button",
             "source": {"path": "src/panel.py"}, "parent_id": "settings"},
            {"id": "hidden", "present": False, "label": "Save", "type": "button",
             "source": {"path": "src/other.py"}, "parent_id": "settings"},
        ],
        "regions": [
            {"id": "settings", "parent_id": "main", "label": "Settings"},
            {"id": "main", "parent_id": None, "label": "Main Window"},
        ],
    }

    assert driver.find("save") == "save"
    assert driver.find({"label": "Save", "type": "button", "source": "panel.py", "region": "Main Window"}) == "save"
    assert driver.matches({"id": "save"}) == ["save"]
    assert driver.matches("hidden") == []
    assert driver.matches({"region": "Settings"}) == ["save"]
    assert driver.matches({"source": "missing.py"}) == []
    assert driver.matches({"region": "Unknown"}) == []
    with pytest.raises(ValueError, match="Unsupported or empty"):
        driver.matches({})
    with pytest.raises(ValueError, match="Unsupported or empty"):
        driver.matches({"text": "Save"})
    with pytest.raises(ValueError, match="matched 0"):
        driver.find({"label": "Missing"})
    telemetry.snapshot["widgets"].append(dict(telemetry.snapshot["widgets"][0], id="save-2"))
    with pytest.raises(ValueError, match="matched 2"):
        driver.find({"label": "Save"})


def test_exists_checks_presence_visibility_and_native_item_id(monkeypatch):
    driver, context, telemetry = setup(monkeypatch)
    assert driver.exists("missing") is False
    telemetry.widgets["gone"] = make_widget(present=False)
    assert driver.exists("gone") is False

    telemetry.widgets["display"] = make_widget(imgui_id=0, visible=True)
    assert driver.exists("display") is True
    telemetry.widgets["hidden-display"] = make_widget(imgui_id=0, visible=False)
    assert driver.exists("hidden-display") is False

    telemetry.widgets["save"] = make_widget()
    context.item_exists.return_value = True
    assert driver.exists("save") is True
    context.item_exists.assert_called_once()
    assert context.item_exists.call_args.args[0].id == 7


def test_click_hold_hover_and_timed_hold_restore_mouse_button(monkeypatch):
    driver, context, telemetry = setup(monkeypatch)
    telemetry.widgets["save"] = make_widget()

    driver.click("save")
    context.mouse_teleport_to_pos.assert_called_with((30.0, 30.0))
    context.mouse_click.assert_called_once()
    driver.hold("save", 4)
    context.mouse_down.assert_called_once()
    context.yield_.assert_called_with(4)
    context.mouse_up.assert_called_once()
    driver.hover("save")
    context.mouse_teleport_to_pos.assert_called_with((30.0, 30.0))

    times = iter([10.0, 10.002, 10.004, 10.006])
    monkeypatch.setattr(driver_module.time, "perf_counter", lambda: next(times))
    context.reset_mock()
    driver.hold_for("save", 5)
    assert context.yield_.call_count == 2
    context.mouse_up.assert_called_once()

    telemetry.widgets["save"]["enabled"] = False
    with pytest.raises(ValueError, match="disabled"):
        driver.click("save")
    with pytest.raises(ValueError, match="disabled"):
        driver.hold("save", 1)
    with pytest.raises(ValueError, match="disabled"):
        driver.hold_for("save", 1)
    for invalid in (0, -1, 10001):
        with pytest.raises(ValueError, match="Timed hold"):
            driver.hold_for("save", invalid)


def test_timed_hold_releases_mouse_when_engine_yield_raises(monkeypatch):
    driver, context, telemetry = setup(monkeypatch)
    telemetry.widgets["save"] = make_widget()
    monkeypatch.setattr(driver_module.time, "perf_counter", lambda: 1.0)
    context.yield_.side_effect = RuntimeError("engine stopped")

    with pytest.raises(RuntimeError, match="engine stopped"):
        driver.hold_for("save", 100)

    context.mouse_up.assert_called_once()


def test_input_value_handles_vectors_sliders_and_text_fields(monkeypatch):
    driver, context, telemetry = setup(monkeypatch)
    telemetry.widgets["vector"] = make_widget(
        imgui_id=0,
        components=[{"imgui_id": 10}, {"imgui_id": 11}],
    )
    driver.input_value("vector", [1, "2"])
    assert [call.args[0].id for call in context.item_input_value.call_args_list] == [10, 11]
    with pytest.raises(ValueError, match="one value per component"):
        driver.input_value("vector", [1])

    telemetry.widgets["float"] = make_widget(widget_type="slider_float", imgui_id=12)
    driver.input_value("float", "1.25")
    telemetry.widgets["integer"] = make_widget(widget_type="slider_int", imgui_id=13)
    driver.input_value("integer", 3.7)
    assert context.item_input_value.call_args_list[-2].args[1] == 1.25
    assert context.item_input_value.call_args_list[-1].args[1] == 3

    telemetry.widgets["name"] = make_widget(widget_type="input_text")
    driver.input_value("name", "hello")
    context.mouse_click.assert_called_once()
    context.key_chars_replace_enter.assert_called_once_with("hello")
    telemetry.widgets["no-id"] = make_widget(imgui_id=0, widget_type="input_text")
    with pytest.raises(ValueError, match="no native input ID"):
        driver.input_value("no-id", "value")


def test_focused_replacements_validate_text_widget_type(monkeypatch):
    driver, context, telemetry = setup(monkeypatch)
    telemetry.widgets["name"] = make_widget(widget_type="input_text")
    driver.replace_focused_value("name", 12)
    driver.replace_focused_text("name", "new text")
    context.key_chars_replace_enter.assert_called_once_with("12")
    context.key_chars_replace.assert_called_once_with("new text")
    telemetry.widgets["other"] = make_widget(widget_type="button")
    with pytest.raises(ValueError, match="native text input"):
        driver.replace_focused_value("other", "x")
    with pytest.raises(ValueError, match="native text input"):
        driver.replace_focused_text("other", "x")


def test_drag_targets_clamp_slider_and_horizontal_or_vertical_pointer_paths(monkeypatch):
    driver, context, telemetry = setup(monkeypatch)
    telemetry.widgets["slider"] = make_widget(widget_type="slider_float", imgui_id=15)
    driver.drag_to_fraction("slider", 2)
    delta = context.item_drag_with_delta.call_args.args[1]
    assert (delta.x, delta.y) == (19.5, 0.0)

    telemetry.widgets["slider-int"] = make_widget(widget_type="slider_int", imgui_id=16)
    driver.drag_to_fraction("slider-int", -1)
    assert context.item_drag_with_delta.call_args.args[1].x == -19.5

    telemetry.widgets["horizontal"] = make_widget(widget_type="invisible_button", rect={
        "x": 10, "y": 20, "width": 40, "height": 10,
    })
    driver.drag_to_fraction("horizontal", 0.5)
    assert context.mouse_teleport_to_pos.call_args_list[-2].args == ((30.0, 25.0),)
    assert context.mouse_teleport_to_pos.call_args_list[-1].args == ((30.0, 25.0),)
    assert context.mouse_up.call_count == 1

    telemetry.widgets["vertical"] = make_widget(widget_type="invisible_button", rect={
        "x": 10, "y": 20, "width": 10, "height": 40,
    })
    driver.drag_to_fraction("vertical", 0.75)
    assert context.mouse_teleport_to_pos.call_args_list[-1].args == ((15.0, 50.0),)

    telemetry.widgets["button"] = make_widget(widget_type="button")
    with pytest.raises(ValueError, match="not a supported drag target"):
        driver.drag_to_fraction("button", 0.5)


def test_drag_window_validates_geometry_and_checks_result(monkeypatch):
    driver, context, telemetry = setup(monkeypatch)
    base = {"id": "panel", "present": True, "visible": True, "kind": "window",
            "rect": {"x": 20.0, "y": 30.0, "width": 120.0, "height": 80.0}}
    telemetry.regions["panel"] = base
    for dx, dy in ((0, 0), (5, 4), (float("inf"), 0)):
        with pytest.raises(ValueError, match="drag threshold"):
            driver.drag_window("panel", dx, dy)

    telemetry.regions["panel"] = dict(base, visible=False)
    with pytest.raises(ValueError, match="not visible"):
        driver.drag_window("panel", 20, 0)
    telemetry.regions["panel"] = dict(base, kind="child")
    with pytest.raises(ValueError, match="not visible"):
        driver.drag_window("panel", 20, 0)

    moved = dict(base, rect={"x": 40.0, "y": 40.0, "width": 120.0, "height": 80.0})
    telemetry.region = MagicMock(side_effect=[base, moved])
    driver.drag_window("panel", 20, 10)
    assert "panel" in telemetry.movable_window_ids
    assert context.mouse_down.called and context.mouse_up.called
    assert context.mouse_teleport_to_pos.call_count == 5

    telemetry.region = MagicMock(side_effect=[base, dict(base)])
    with pytest.raises(AssertionError, match="did not move"):
        driver.drag_window("panel", 20, 10)


def test_resolve_and_click_reject_missing_widgets_or_missing_semantic_parent(monkeypatch):
    driver, _context, telemetry = setup(monkeypatch)
    with pytest.raises(KeyError, match="No visible UI widget"):
        driver._resolve("absent")
    telemetry.widgets["save"] = make_widget(present=False)
    with pytest.raises(KeyError, match="No visible UI widget"):
        driver.click("save")
    telemetry.widgets["save"] = make_widget(parent="missing")
    with pytest.raises(KeyError, match="No semantic UI region"):
        driver.click("save")


def test_open_check_and_combo_selection_validate_and_escape_option_paths(monkeypatch):
    driver, context, telemetry = setup(monkeypatch)
    telemetry.widgets["button"] = make_widget(imgui_id=19)
    driver.open("button")
    driver.check("button", True)
    driver.check("button", False)
    assert context.item_open.call_args.args[0].id == 19
    assert context.item_check.call_args.args[0].id == 19
    assert context.item_uncheck.call_args.args[0].id == 19

    telemetry.widgets["combo"] = make_widget(widget_type="combo", options=["One", "Path/Two"])
    driver.select("combo", "Path/Two")
    assert context.item_click.call_args.args == ("**/Path\\/Two",)
    assert context.yield_.call_count == 2
    driver.select("combo", 0)
    with pytest.raises(ValueError, match="Selection requires a combo"):
        driver.select("button", "One")
    with pytest.raises(ValueError, match="out of range"):
        driver.select("combo", 2)

    telemetry.widgets["long-combo"] = make_widget(
        widget_type="combo", options=[str(index) for index in range(10)],
    )
    driver.select("long-combo", "9")
    context.scroll_to_y.assert_called_once_with("##Combo_00", 9 * 20.0)
    context.item_click.assert_called_with("**/9")


def test_scroll_uses_native_ids_or_nearest_child_for_display_only_rows(monkeypatch):
    driver, context, telemetry = setup(monkeypatch)
    telemetry.widgets["native"] = make_widget(imgui_id=20)
    driver.scroll("native")
    assert context.scroll_to_item_x.call_args.args[0].id == 20
    assert context.scroll_to_item_y.call_args.args[0].id == 20

    telemetry.widgets["visible"] = make_widget(imgui_id=0, visible=True)
    driver.scroll("visible")
    context.mouse_wheel_y.assert_not_called()

    telemetry.regions["list"] = {
        "id": "list", "parent_id": "panel", "kind": "child",
        "rect": {"x": 0, "y": 50, "width": 100, "height": 30},
    }
    telemetry.widgets["above"] = make_widget(imgui_id=0, visible=False, parent="list", rect={
        "x": 10, "y": 20, "width": 10, "height": 10,
    })
    driver.scroll("above")
    context.mouse_wheel_y.assert_called_with(1.0)
    assert context.mouse_teleport_to_pos.call_args.args == ((50.0, 65.0),)

    telemetry.widgets["below"] = make_widget(imgui_id=0, visible=False, parent="list", rect={
        "x": 10, "y": 100, "width": 10, "height": 10,
    })
    driver.scroll("below")
    assert context.mouse_wheel_y.call_args.args == (-1.0,)

    telemetry.widgets["inside"] = make_widget(imgui_id=0, visible=False, parent="list", rect={
        "x": 10, "y": 55, "width": 10, "height": 10,
    })
    count = context.mouse_wheel_y.call_count
    driver.scroll("inside")
    assert context.mouse_wheel_y.call_count == count

    telemetry.regions["orphan-parent"] = {"id": "orphan-parent", "parent_id": "missing", "kind": "window"}
    telemetry.widgets["orphan"] = make_widget(imgui_id=0, visible=False, parent="orphan-parent")
    with pytest.raises(ValueError, match="no ImGui ID or scrollable child"):
        driver.scroll("orphan")


def test_close_window_prefers_custom_control_and_falls_back_to_titlebar(monkeypatch):
    driver, context, telemetry = setup(monkeypatch)
    telemetry.regions["window"] = {
        "id": "window", "present": True, "visible": True, "kind": "window",
        "rect": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 80.0},
    }
    telemetry.widgets["window.close"] = make_widget(parent="window", widget_type="button")
    driver.close_window("window")
    context.mouse_click.assert_called_once()
    context.mouse_teleport_to_pos.assert_called_with((30.0, 30.0))

    telemetry.widgets.pop("window.close")
    driver.close_window("window")
    context.mouse_teleport_to_pos.assert_called_with((96.0, 32.0))
    assert context.mouse_click.call_count == 2

    telemetry.regions["child"] = dict(telemetry.regions["window"], kind="child")
    with pytest.raises(ValueError, match="not a window"):
        driver.close_window("child")
    telemetry.regions["hidden"] = dict(telemetry.regions["window"], visible=False)
    with pytest.raises(KeyError, match="No visible UI window"):
        driver.close_window("hidden")
    with pytest.raises(KeyError, match="No visible UI window"):
        driver.close_window("missing")
