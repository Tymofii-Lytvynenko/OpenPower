from contextlib import contextmanager
from importlib import import_module
from types import SimpleNamespace

import pytest

from src.client.ui.components.shared.history_tooltip_window import (
    HistoryEventMarker,
    HistoryTooltipWindow,
)


class _FakeImgui:
    WindowFlags_ = SimpleNamespace(
        no_title_bar=1,
        no_resize=2,
        no_move=4,
        no_collapse=8,
        no_saved_settings=16,
        no_scrollbar=32,
        no_scroll_with_mouse=64,
    )

    def __init__(self, *, mouse=(0.0, 0.0), text_size=(80.0, 30.0), style=(1.0, 1.0)):
        self.mouse = SimpleNamespace(x=mouse[0], y=mouse[1])
        self.text_size = SimpleNamespace(x=text_size[0], y=text_size[1])
        self.style = SimpleNamespace(font_scale_main=style[0], font_scale_dpi=style[1])
        self.calls = []
        self.text_error = None

    def get_mouse_pos(self):
        return self.mouse

    def get_style(self):
        return self.style

    def push_font(self, font, size):
        self.calls.append(("push_font", font, size))

    def pop_font(self):
        self.calls.append(("pop_font",))

    def calc_text_size(self, text, *, wrap_width):
        self.calls.append(("calc_text_size", text, wrap_width))
        return self.text_size

    def text_wrapped(self, text, **kwargs):
        self.calls.append(("text_wrapped", text, kwargs))
        if self.text_error:
            raise self.text_error


def _install_ui(
    monkeypatch,
    *,
    imgui,
    window_open=True,
    layout_font_size=9.0,
    active_font_size=None,
):
    module = import_module("src.client.ui.components.shared.history_tooltip_window")
    window_calls = []

    @contextmanager
    def window(*args, **kwargs):
        window_calls.append((args, kwargs))
        yield window_open

    layout = SimpleNamespace(
        component=lambda _component_id: SimpleNamespace(font_size=layout_font_size)
    )
    if active_font_size is None:
        active_session = None
    else:
        active_session = SimpleNamespace(
            layout=SimpleNamespace(
                component=lambda _component_id: SimpleNamespace(font_size=active_font_size)
            )
        )
    monkeypatch.setattr(module, "imgui", imgui)
    monkeypatch.setattr(module, "WindowManager", SimpleNamespace(window=window))
    monkeypatch.setattr(module, "get_gml_layout", lambda _template: layout)
    monkeypatch.setattr(module, "active_gml_layout", lambda: active_session)
    return window_calls


def test_update_hover_tracks_marker_keeps_tooltip_under_mouse_then_hides(monkeypatch):
    imgui = _FakeImgui(mouse=(155.0, 120.0), style=(0.0, 1.0))
    _install_ui(monkeypatch, imgui=imgui, layout_font_size=0.0)
    tooltip = HistoryTooltipWindow()
    marker = HistoryEventMarker("event-1", 150.0, 100.0, "Treaty signed")

    tooltip.update_hover(
        [], None, parent_origin=(100.0, 50.0), parent_size=(300.0, 200.0),
    )
    assert tooltip.render() is False

    tooltip.update_hover(
        [marker], marker.test_id, parent_origin=(100.0, 50.0), parent_size=(300.0, 200.0),
    )
    assert tooltip._text == "Treaty signed"
    assert tooltip._marker_position == (150.0, 100.0)

    tooltip.update_hover(
        [marker], None, parent_origin=(100.0, 50.0), parent_size=(300.0, 200.0),
    )
    assert tooltip._text == "Treaty signed"
    assert any(call[0] == "calc_text_size" for call in imgui.calls)

    imgui.mouse = SimpleNamespace(x=0.0, y=0.0)
    tooltip.update_hover(
        [marker], None, parent_origin=(100.0, 50.0), parent_size=(300.0, 200.0),
    )
    assert tooltip._text == ""
    assert tooltip._marker_position is None
    assert any(call == ("push_font", None, 90.0) for call in imgui.calls)


def test_window_size_clamps_to_parent_and_has_eight_pixel_minimum(monkeypatch):
    imgui = _FakeImgui(text_size=(100.0, 0.0))
    _install_ui(monkeypatch, imgui=imgui)
    tooltip = HistoryTooltipWindow()
    tooltip._text = "x"

    tooltip._parent_size = (50.0, 10.0)
    assert tooltip._window_size() == (50.0, 8.0)

    tooltip._parent_size = (0.0, 0.0)
    assert tooltip._window_size() == (8.0, 8.0)
    assert imgui.calls.count(("pop_font",)) == 2


def test_tooltip_position_handles_missing_marker_edges_and_parent_clamping(monkeypatch):
    _install_ui(monkeypatch, imgui=_FakeImgui())
    tooltip = HistoryTooltipWindow()
    tooltip._parent_origin = (20.0, 30.0)
    tooltip._parent_size = (100.0, 100.0)

    assert tooltip._tooltip_position(40.0, 20.0) == (20.0, 30.0)

    tooltip._marker_position = (110.0, 220.0)
    assert tooltip._tooltip_position(40.0, 50.0) == (80.0, 80.0)

    tooltip._marker_position = (10.0, 31.0)
    assert tooltip._tooltip_position(150.0, 120.0) == (20.0, 30.0)


def test_render_returns_false_when_window_is_closed(monkeypatch):
    imgui = _FakeImgui()
    _install_ui(monkeypatch, imgui=imgui, window_open=False)
    tooltip = HistoryTooltipWindow()
    tooltip._text = "Event"
    tooltip._marker_position = (50.0, 60.0)
    tooltip._parent_size = (300.0, 200.0)

    assert tooltip.render() is False
    assert not any(call[0] == "text_wrapped" for call in imgui.calls)


def test_render_uses_active_layout_font_and_restores_font(monkeypatch):
    imgui = _FakeImgui(style=(2.0, 0.5))
    window_calls = _install_ui(
        monkeypatch,
        imgui=imgui,
        active_font_size=12.0,
    )
    tooltip = HistoryTooltipWindow()
    tooltip._text = "Event details"
    tooltip._marker_position = (50.0, 60.0)
    tooltip._parent_origin = (10.0, 20.0)
    tooltip._parent_size = (300.0, 200.0)

    assert tooltip.render() is True

    assert imgui.calls.count(("push_font", None, 12.0)) == 1
    assert imgui.calls.count(("pop_font",)) == 2
    assert ("text_wrapped", "Event details", {
        "gml_id": "History_Tooltip_Window/txtText",
        "test_id": "history.tooltip.text",
    }) in imgui.calls
    assert window_calls[0][0] == ("##history_event_tooltip",)
    assert window_calls[0][1]["flags"] == 127
    assert window_calls[0][1]["size_override"] == (88.0, 38.0)


def test_render_restores_font_when_text_rendering_raises(monkeypatch):
    imgui = _FakeImgui()
    imgui.text_error = RuntimeError("draw failed")
    _install_ui(monkeypatch, imgui=imgui)
    tooltip = HistoryTooltipWindow()
    tooltip._text = "Event details"
    tooltip._marker_position = (50.0, 60.0)
    tooltip._parent_size = (300.0, 200.0)

    with pytest.raises(RuntimeError, match="draw failed"):
        tooltip.render()

    assert imgui.calls.count(("pop_font",)) == 2
