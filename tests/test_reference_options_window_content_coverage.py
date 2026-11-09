from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.components import reference_options_window_content as options_module
from src.client.ui.components.reference_options_window_content import REFERENCEOptionsWindowContent


class FakeWidgets:
    clicks = set()
    toggles = {}
    rects = {}
    calls = []

    def __init__(self, root):
        self.root = root

    def path(self, slot):
        return f"{self.root}/{slot}"

    def frame(self, slot):
        self.calls.append(("frame", self.root, slot))

    def button_at(self, slot, label, test_id, **kwargs):
        self.calls.append(("button_at", self.root, slot, label, test_id, kwargs))
        return test_id in self.clicks

    def text(self, slot, value, **kwargs):
        self.calls.append(("text", self.root, slot, value, kwargs))

    def text_at(self, slot, value, **kwargs):
        self.calls.append(("text_at", self.root, slot, value, kwargs))

    def meter(self, slot, value, color, **kwargs):
        self.calls.append(("meter", self.root, slot, value, color, kwargs))

    def toggle(self, slot, value, test_id, **kwargs):
        self.calls.append(("toggle", self.root, slot, value, test_id, kwargs))
        return self.toggles.get(test_id, (False, value))

    def combo_at(self, slot, label, index, items, test_id, **kwargs):
        self.calls.append(("combo_at", self.root, slot, label, index, items, test_id, kwargs))

    def hitbox(self, slot, test_id, **kwargs):
        self.calls.append(("hitbox", self.root, slot, test_id, kwargs))

    def rect(self, slot):
        self.calls.append(("rect", self.root, slot))
        return self.rects.get(slot)


class FakeSettingsContent:
    def __init__(self, *, autosave_enabled=True, validation_error=""):
        self.options = SimpleNamespace(
            autosave_enabled=autosave_enabled,
            autosave_incremental=True,
            autosave_interval_minutes=10,
            autosave_name="autosave",
        )
        self.autosave_validation_error = validation_error
        self.begin_session = Mock()
        self.discard = Mock()
        self.apply = Mock(return_value=True)
        self.render = Mock()
        self.render_content = Mock()
        self.updates = []

    def update_options(self, **changes):
        self.updates.append(changes)
        for name, value in changes.items():
            setattr(self.options, name, value)


class FakeSession:
    def __init__(self, *, tab_layout=True, button_rects=None):
        self.window_position = (100.0, 200.0)
        self.tab_layout = SimpleNamespace(
            tab_names=("Tab1", "Tab2", "Tab3"),
            button_offset_left=4.0,
            button_width=80.0,
            button_distance=2.0,
            button_height=18.0,
        )
        self.layout = SimpleNamespace(
            component=lambda _path: SimpleNamespace(tab_layout=self.tab_layout)
        )
        self.button_rects = button_rects or {
            0: SimpleNamespace(x=10, y=20, width=80, height=18),
            1: SimpleNamespace(x=92, y=20, width=80, height=18),
            2: SimpleNamespace(x=174, y=20, width=80, height=18),
            3: None,
        }
        self._tab_layout_result = object() if tab_layout else None
        self.apply_tab_page_runtime_geometry = Mock(return_value=self._tab_layout_result)
        self.rect_for = Mock(return_value=SimpleNamespace(x=5, y=6))
        self.tab_button_rect = Mock(side_effect=lambda _path, index: self.button_rects.get(index))


def install(monkeypatch, *, session=None):
    imgui = Mock()
    imgui.Col_ = SimpleNamespace(button="button")
    imgui.HoveredFlags_ = SimpleNamespace(allow_when_disabled="allow_disabled")
    imgui.get_scroll_x.return_value = 2.0
    imgui.get_scroll_y.return_value = 3.0
    imgui.is_item_hovered.return_value = False
    imgui.get_cursor_screen_pos.return_value = (7.0, 8.0)
    FakeWidgets.clicks = set()
    FakeWidgets.toggles = {}
    FakeWidgets.rects = {}
    FakeWidgets.calls = []
    monkeypatch.setattr(options_module, "imgui", imgui)
    monkeypatch.setattr(options_module, "GMLWidgets", FakeWidgets)
    monkeypatch.setattr(options_module, "active_gml_layout", lambda: session)

    @contextmanager
    def region(*_args, **_kwargs):
        yield

    monkeypatch.setattr(options_module, "semantic_region", region)
    return imgui


def test_session_lifecycle_forwards_optional_settings_callbacks():
    settings = FakeSettingsContent()
    content = REFERENCEOptionsWindowContent(settings, "menu")

    content.begin_session()
    content.discard()
    assert content.apply() is True

    settings.apply = None
    assert content.apply() is None


def test_render_falls_back_without_layout_or_tab_geometry(monkeypatch):
    install(monkeypatch, session=None)
    settings = FakeSettingsContent()
    content = REFERENCEOptionsWindowContent(settings, "menu")

    content.render(max_height=120)
    settings.render.assert_called_once_with(max_height=120)

    session = FakeSession(tab_layout=False)
    install(monkeypatch, session=session)
    content.render(max_height=90)
    session.apply_tab_page_runtime_geometry.assert_called_once_with(
        "Options_Window/frmInner/tabOptions",
    )
    settings.render.assert_called_with(max_height=90)


def test_tab_buttons_use_existing_rectangles_and_synthesize_final_source_tab(monkeypatch):
    imgui = install(monkeypatch)
    session = FakeSession(button_rects={
        0: SimpleNamespace(x=20, y=30, width=80, height=18),
        1: None,
        2: SimpleNamespace(x=184, y=30, width=82, height=19),
        3: None,
    })
    content = REFERENCEOptionsWindowContent(FakeSettingsContent(), "pause")

    content._render_tab_buttons(FakeWidgets("Options_Window/frmInner"), session)

    buttons = [call for call in FakeWidgets.calls if call[0] == "button_at"]
    assert [button[4] for button in buttons] == [
        "pause.options.tab.profile",
        "pause.options.tab.sound",
        "pause.options.tab.openpower",
    ]
    assert buttons[0][5]["offset"] == (15, 24)
    assert buttons[0][5]["size"] == (80, 18)
    assert buttons[-1][5]["offset"] == (250.0, 0.0)
    assert buttons[-1][5]["size"] == (80.0, 18.0)
    assert imgui.push_style_color.call_count == 3
    assert imgui.pop_style_color.call_count == 3


def test_render_profile_updates_autosave_settings_and_reports_validation(monkeypatch):
    imgui = install(monkeypatch, session=FakeSession())
    settings = FakeSettingsContent(validation_error="Name contains invalid characters")
    content = REFERENCEOptionsWindowContent(settings, "pause")
    FakeWidgets.toggles = {
        "options.source.profile.autosave": (False, True),
        "options.source.profile.incremental": (True, False),
    }
    imgui.input_int.return_value = (True, 0)
    imgui.input_text.side_effect = lambda _label, current, *_args, **kwargs: (
        (False, current)
        if kwargs.get("test_id") == "options.source.profile.player_name"
        else (True, "bad/name")
    )
    imgui.is_item_hovered.return_value = True

    content.render(max_height=200)

    assert settings.updates == [
        {"autosave_incremental": False},
        {"autosave_interval_minutes": 1},
        {"autosave_name": "bad/name"},
    ]
    assert imgui.set_tooltip.call_args.args[0] == "OpenPower has no player profile-name setting."
    assert any(
        call[0] == "text_at" and call[3] == "Invalid save name"
        and call[4]["test_id"] == "options.source.profile.filename.error"
        for call in FakeWidgets.calls
    )
    assert imgui.begin_disabled.call_count == 1
    assert imgui.end_disabled.call_count == 1


def test_profile_autosave_toggle_can_turn_off_and_skip_nested_controls(monkeypatch):
    install(monkeypatch, session=FakeSession())
    settings = FakeSettingsContent()
    FakeWidgets.toggles = {"options.source.profile.autosave": (True, False)}
    content = REFERENCEOptionsWindowContent(settings, "pause")

    content.render()

    assert settings.updates == [{"autosave_enabled": False}]
    assert not any(call[0] == "frame" and call[2] == "Tab1/frmAutosave" for call in FakeWidgets.calls)


def test_graphics_and_sound_tabs_render_unsupported_controls(monkeypatch):
    imgui = install(monkeypatch, session=FakeSession())
    settings = FakeSettingsContent()
    content = REFERENCEOptionsWindowContent(settings, "pause")
    FakeWidgets.clicks = {"pause.options.tab.graphics"}

    content.render()

    assert content._active_tab == 1
    assert len([call for call in FakeWidgets.calls if call[0] == "combo_at"]) == 5
    assert len([call for call in FakeWidgets.calls if call[0] == "hitbox"]) == 4
    assert imgui.is_item_hovered.call_count == 5
    FakeWidgets.clicks = {"pause.options.tab.sound"}

    content.render()

    assert content._active_tab == 2
    assert len([call for call in FakeWidgets.calls if call[0] == "meter"]) == 2
    assert len([call for call in FakeWidgets.calls if call[0] == "text_at"]) == 2


def test_unavailable_controls_show_tooltips_and_crossed_toggle_when_layout_exists(monkeypatch):
    session = FakeSession()
    imgui = install(monkeypatch, session=session)
    imgui.is_item_hovered.return_value = True
    rect = SimpleNamespace(x=10, y=12, width=20, height=8)
    FakeWidgets.rects = {"togClouds": rect}
    ui = FakeWidgets("Tab2")

    REFERENCEOptionsWindowContent._unavailable_input(
        ui, "edtName", "player", "No profile setting.",
    )
    REFERENCEOptionsWindowContent._unavailable_combo(
        ui, "cboQuality", "quality", "No renderer setting.",
    )
    REFERENCEOptionsWindowContent._unavailable_toggle(
        ui, "togClouds", "clouds", "No visibility setting.",
    )

    assert imgui.set_tooltip.call_args_list[0].args == ("No profile setting.",)
    assert imgui.set_tooltip.call_args_list[1].args == ("No renderer setting.",)
    draw = imgui.get_window_draw_list.return_value
    draw.add_rect.assert_called_once_with((108.0, 209.0), (128.0, 217.0), imgui.get_color_u32.return_value)
    draw.add_line.assert_called_once()


def test_unavailable_toggle_returns_without_drawing_when_rect_or_session_is_missing(monkeypatch):
    install(monkeypatch, session=None)
    ui = FakeWidgets("Tab2")

    REFERENCEOptionsWindowContent._unavailable_toggle(ui, "togClouds", "clouds", "Unavailable.")
    assert [call[0] for call in FakeWidgets.calls] == ["hitbox", "rect"]

    session = FakeSession()
    install(monkeypatch, session=session)
    FakeWidgets.rects = {"togClouds": SimpleNamespace(x=1, y=1, width=10, height=10)}
    REFERENCEOptionsWindowContent._unavailable_toggle(ui, "togClouds", "clouds", "Unavailable.")
    options_module.imgui.get_window_draw_list.assert_called_once()


def test_openpower_tab_falls_back_to_render_content_or_height_limited_render(monkeypatch):
    session = FakeSession()
    imgui = install(monkeypatch, session=session)
    rect = SimpleNamespace(x=20, y=30, width=240, height=180)
    FakeWidgets.rects = {"Tab1": rect}
    settings = FakeSettingsContent()
    content = REFERENCEOptionsWindowContent(settings, "pause")
    FakeWidgets.clicks = {"pause.options.tab.openpower"}

    content.render()

    settings.render_content.assert_called_once_with()
    settings.render.assert_not_called()
    imgui.end_child.assert_called_once_with()
    imgui.set_cursor_screen_pos.assert_any_call((7.0, 8.0))
    assert imgui.set_cursor_screen_pos.call_args_list[0].args[0] == (118.0, 227.0)

    settings.render_content = None
    settings.render.reset_mock()
    content.render()
    settings.render.assert_called_once_with(max_height=180)


def test_openpower_tab_handles_missing_rect_and_closed_child(monkeypatch):
    session = FakeSession()
    imgui = install(monkeypatch, session=session)
    settings = FakeSettingsContent()
    content = REFERENCEOptionsWindowContent(settings, "pause")
    FakeWidgets.clicks = {"pause.options.tab.openpower"}

    content.render()
    settings.render.assert_called_once_with()
    imgui.begin_child.assert_not_called()

    settings.render.reset_mock()
    FakeWidgets.rects = {"Tab1": SimpleNamespace(x=0, y=0, width=200, height=100)}
    imgui.begin_child.return_value = False
    content.render()
    settings.render.assert_not_called()
    imgui.end_child.assert_called_once_with()
