from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from src.client.services.imgui_service import ImGuiService
from src.client.ui.core import composer as composer_module
from src.client.ui.core.composer import UIComposer
from src.client.ui.core.primitives import UIPrimitives


def native_ui(**overrides):
    methods = {
        "Cond_": SimpleNamespace(first_use_ever=1, always=2),
        "WindowFlags_": SimpleNamespace(no_collapse=4, no_title_bar=8, no_resize=16, no_move=32),
        "StyleVar_": SimpleNamespace(window_border_size=1, window_rounding=2, window_padding=3),
        "HoveredFlags_": SimpleNamespace(allow_when_disabled=1),
        "PopupFlags_": SimpleNamespace(mouse_button_right=1),
        "MouseButton_": SimpleNamespace(right=1),
        "set_next_window_pos": lambda *args, **kwargs: None,
        "set_next_window_size": lambda *args, **kwargs: None,
        "push_style_var": lambda *args, **kwargs: None,
        "pop_style_var": lambda *args, **kwargs: None,
        "begin": lambda *args, **kwargs: (True, True),
        "end": lambda: None,
        "dummy": lambda *args: None,
        "get_content_region_avail": lambda: SimpleNamespace(x=200.0),
        "get_cursor_pos_x": lambda: 10.0,
        "set_cursor_pos_x": lambda _x: None,
        "calc_text_size": lambda text: SimpleNamespace(x=len(text) * 5.0, y=12.0),
        "text": lambda *_args: None,
        "separator": lambda: None,
        "begin_disabled": lambda *_args: None,
        "end_disabled": lambda: None,
        "is_item_hovered": lambda *_args: False,
        "set_tooltip": lambda *_args: None,
        "ImVec2": lambda *args: args,
        "image": lambda *_args, **_kwargs: None,
        "begin_popup_context_window": lambda *_args: False,
        "open_popup": lambda *_args: None,
        "begin_popup": lambda *_args: False,
        "end_popup": lambda: None,
        "begin_menu": lambda *_args: False,
        "end_menu": lambda: None,
        "menu_item": lambda *_args, **_kwargs: (False, False),
        "get_io": lambda: SimpleNamespace(want_capture_mouse=False),
        "get_mouse_drag_delta": lambda *_args: SimpleNamespace(x=0, y=0),
    }
    methods.update(overrides)
    return SimpleNamespace(**methods)


@pytest.fixture
def composer(monkeypatch):
    monkeypatch.setattr(composer_module, "imgui", native_ui())
    return UIComposer(SimpleNamespace(apply=lambda: None))


def test_theme_frame_panel_and_centered_panel_without_layout(monkeypatch, composer):
    calls = []
    theme = composer.theme
    theme.apply = lambda: calls.append("theme")
    native = native_ui(
        set_next_window_pos=lambda *args: calls.append(("pos", args)),
        set_next_window_size=lambda *args: calls.append(("size", args)),
        begin=lambda *args, **kwargs: calls.append(("begin", args, kwargs)) or (False, True),
        end=lambda: calls.append("end"),
        pop_style_var=lambda count: calls.append(("pop", count)),
    )
    monkeypatch.setattr(composer_module, "imgui", native)
    monkeypatch.setattr(composer_module, "resolve_gml_layout", lambda *args, **kwargs: None)

    composer.setup_frame()
    assert composer.begin_panel("Main", 1, 2, 300, 200) == (False, True)
    assert composer.begin_centered_panel("Dialog", 800, 600, force_size=True, size_override=(400, 200)) is False

    assert "theme" in calls
    assert ("pos", ((200.0, 200.0),)) in calls
    assert ("pop", 2) in calls
    assert calls[-1] == "end"
    composer.end_panel()
    assert calls[-1] == "end"


def test_centered_panel_layout_opens_and_closes_gml_scope(monkeypatch, composer):
    layout = SimpleNamespace(width=500, height=300, template="resolved")
    calls = []
    native = native_ui(
        begin=lambda *args, **kwargs: (True, True),
        pop_style_var=lambda count: calls.append(("pop", count)),
        get_window_pos=lambda: SimpleNamespace(x=20, y=30),
        get_window_size=lambda: SimpleNamespace(x=500, y=300),
        end=lambda: calls.append("end"),
    )
    scope = nullcontext()
    monkeypatch.setattr(composer_module, "imgui", native)
    monkeypatch.setattr(composer_module, "resolve_gml_layout", lambda *args, **kwargs: layout)
    monkeypatch.setattr(composer_module, "create_gml_layout_session", lambda *args: "session")
    monkeypatch.setattr(composer_module, "render_gml_title", lambda *args: calls.append("title"))
    monkeypatch.setattr(composer_module, "use_gml_layout", lambda _session: scope)

    assert composer.begin_centered_panel("Dialog", 800, 600, test_id="dialog") is True
    assert composer._gml_layout_scopes == [scope]
    assert calls == [("pop", 3), "title"]

    composer.end_panel()

    assert composer._gml_layout_scopes == []
    assert calls[-1] == "end"


def test_centered_panel_ends_invisible_layout_and_size_override_wins(monkeypatch, composer):
    layout = SimpleNamespace(width=500, height=300, template="resolved")
    calls = []
    native = native_ui(
        begin=lambda *args, **kwargs: (False, False),
        set_next_window_size=lambda size, condition: calls.append(("size", size, condition)),
        pop_style_var=lambda count: calls.append(("pop", count)),
        end=lambda: calls.append("end"),
    )
    monkeypatch.setattr(composer_module, "imgui", native)
    monkeypatch.setattr(composer_module, "resolve_gml_layout", lambda *args, **kwargs: layout)

    assert composer.begin_centered_panel("Dialog", 800, 600, size_override=(420, 240)) is False

    assert ("size", (420.0, 240.0), native.Cond_.always) in calls
    assert ("pop", 3) in calls
    assert calls[-1] == "end"
    assert composer._gml_layout_scopes == []


def test_layout_helpers_center_text_and_draw_title(monkeypatch, composer):
    calls = []
    native = native_ui(
        ImVec2=lambda *args: args,
        dummy=lambda *args: calls.append(("dummy", args)),
        get_content_region_avail=lambda: SimpleNamespace(x=200.0),
        get_cursor_pos_x=lambda: 10.0,
        set_cursor_pos_x=lambda x: calls.append(("cursor", x)),
        calc_text_size=lambda text: SimpleNamespace(x=len(text) * 5.0),
        get_window_width=lambda: 300,
        text=lambda text: calls.append(("text", text)),
        separator=lambda: calls.append("separator"),
    )
    monkeypatch.setattr(composer_module, "imgui", native)

    composer.dummy((2, 3))
    composer.space(15)
    composer.right_align(50)
    composer.right_align(250)
    composer.centered_text("Hello")
    composer.draw_title("Title")

    assert calls[0] == ("dummy", ((2, 3),))
    assert calls[1] == ("dummy", ((15, 0),))
    assert ("cursor", 160.0) in calls
    assert calls.count(("text", "Hello")) == 1
    assert calls.count(("text", "Title")) == 1
    assert calls.count("separator") == 1


def test_menu_button_skips_empty_tooltips_and_restores_disabled_scope(monkeypatch, composer):
    calls = []
    native = native_ui(
        begin_disabled=lambda disabled: calls.append(("begin", disabled)),
        end_disabled=lambda: calls.append("end-disabled"),
        is_item_hovered=lambda *_args: True,
    )
    monkeypatch.setattr(composer_module, "imgui", native)
    monkeypatch.setattr(UIPrimitives, "button", lambda *_args, **_kwargs: True)
    composer.dummy = lambda size: calls.append(("dummy", size))

    assert composer.draw_menu_button("Go", enabled=True, tooltip="") is True
    assert calls == [("begin", False), "end-disabled", ("dummy", (0, 5))]


def test_menu_button_restores_disabled_scope_when_primitive_raises(monkeypatch, composer):
    calls = []
    monkeypatch.setattr(composer_module, "imgui", native_ui(end_disabled=lambda: calls.append("end")))
    monkeypatch.setattr(
        UIPrimitives,
        "button",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("button failed")),
    )

    with pytest.raises(RuntimeError, match="button failed"):
        composer.draw_menu_button("Go")

    assert calls == ["end"]


def test_component_wrappers_forward_theme_and_toggle_options(monkeypatch, composer):
    calls = []
    monkeypatch.setattr(UIPrimitives, "header", lambda *args, **kwargs: calls.append(("header", args, kwargs)))
    monkeypatch.setattr(UIPrimitives, "meter", lambda *args, **kwargs: calls.append(("meter", args, kwargs)))
    monkeypatch.setattr(UIPrimitives, "currency_row", lambda *args, **kwargs: calls.append(("currency", args, kwargs)))
    monkeypatch.setattr(UIPrimitives, "progress_bar", lambda *args, **kwargs: calls.append(("progress", args, kwargs)))
    monkeypatch.setattr(UIPrimitives, "icon_toggle", lambda *args, **kwargs: calls.append(("toggle", args, kwargs)) or True)

    composer.draw_section_header("Section", show_more_btn=False)
    composer.draw_meter("Health", 40, (1, 0, 0), show_percentage=False)
    composer.draw_currency_row("Balance", 10)
    composer.draw_progress_bar(0.4)
    assert composer.draw_icon_toggle("star", (1, 1, 1), True) is True

    assert [call[0] for call in calls] == ["header", "meter", "currency", "progress", "toggle"]
    assert calls[-1][2]["show_inactive_indicator"] is True
    assert all(call[2]["theme"] is composer.theme for call in calls)


def test_draw_image_handles_missing_invalid_valid_and_error_textures(monkeypatch, composer):
    calls = []
    composer.dummy = lambda size: calls.append(("dummy", size))
    native = native_ui(
        ImVec2=lambda *args: args,
        image=lambda *args: calls.append(("image", args)),
    )
    monkeypatch.setattr(composer_module, "imgui", native)
    monkeypatch.setattr(ImGuiService, "get_texture_id", staticmethod(lambda texture: texture.gl_id))

    composer.draw_image(None, 10, 20)
    composer.draw_image(SimpleNamespace(gl_id=0), 30, 40)
    composer.draw_image(SimpleNamespace(gl_id=7), 50, 60)

    assert calls[:2] == [("dummy", (10, 20)), ("dummy", (30, 40))]
    assert calls[2][0] == "image"
    assert calls[2][1][0].value == 7
    assert calls[2][1][1] == (50, 60)


def test_draw_image_falls_back_to_reserved_space_when_texture_upload_fails(monkeypatch, composer):
    calls = []
    composer.dummy = lambda size: calls.append(size)
    monkeypatch.setattr(ImGuiService, "get_texture_id", staticmethod(lambda _texture: 7))
    monkeypatch.setattr(composer_module, "imgui", native_ui(image=lambda *_args: (_ for _ in ()).throw(RuntimeError("draw failed"))))

    composer.draw_image(SimpleNamespace(), 8, 9)

    assert calls == [(8, 9)]


def test_popup_menu_and_background_click_helpers(monkeypatch, composer):
    calls = []
    io = SimpleNamespace(want_capture_mouse=True)
    native = native_ui(
        begin_popup_context_window=lambda *args: calls.append(("context", args)) or True,
        open_popup=lambda name: calls.append(("open", name)),
        begin_popup=lambda name: calls.append(("popup", name)) or True,
        end_popup=lambda: calls.append("end-popup"),
        begin_menu=lambda name: calls.append(("menu", name)) or True,
        end_menu=lambda: calls.append("end-menu"),
        menu_item=lambda *args, **kwargs: (True, False),
        get_io=lambda: io,
        get_mouse_drag_delta=lambda *_args: SimpleNamespace(x=2, y=3),
    )
    monkeypatch.setattr(composer_module, "imgui", native)

    assert composer.begin_context_menu() is True
    composer.open_popup("Details")
    assert composer.begin_popup("Details") is True
    composer.end_popup()
    assert composer.begin_menu("Edit") is True
    composer.end_menu()
    assert composer.draw_menu_item("Save", "Ctrl+S", test_id="save") is True
    assert composer.is_background_clicked() is False
    io.want_capture_mouse = False
    assert composer.is_background_clicked() is True
    native.get_mouse_drag_delta = lambda *_args: SimpleNamespace(x=5, y=0)
    assert composer.is_background_clicked() is False
    assert composer.show_if(True) is True
    assert composer.show_if(False) is False

    assert calls[0] == ("context", ("map_context", native.PopupFlags_.mouse_button_right))
    assert ("open", "Details") in calls
