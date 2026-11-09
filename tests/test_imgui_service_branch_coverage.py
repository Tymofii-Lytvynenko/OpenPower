import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import arcade
import numpy as np
import pytest
from imgui_bundle import imgui, implot

from src.client.services import imgui_service as imgui_service_module
from src.client.services.imgui_service import ImGuiService
from src.client.ui.core.font_loader import FontLoader


class FakeIO:
    def __init__(self):
        self.config_flags = 0
        self.want_capture_mouse = True
        self.want_capture_keyboard = True
        self.events = []

    def add_mouse_pos_event(self, *args):
        self.events.append(("mouse_pos", args))

    def add_mouse_button_event(self, *args):
        self.events.append(("mouse_button", args))

    def add_mouse_wheel_event(self, *args):
        self.events.append(("wheel", args))

    def add_key_event(self, *args):
        self.events.append(("key", args))

    def add_input_character(self, *args):
        self.events.append(("character", args))


def bare_service(window=None, io=None):
    service = object.__new__(ImGuiService)
    service.window = window or SimpleNamespace(height=100, get_size=lambda: (800, 600), get_pixel_ratio=lambda: 1.0)
    service.io = io or FakeIO()
    service._context = "imgui-context"
    service._plot_context = None
    service._frame_started = False
    service._current_delta_time = 1 / 60
    service._real_fps = 60.0
    service._ui_bridge = None
    service.renderer = SimpleNamespace(render=lambda _data: None)
    service.key_map = {arcade.key.A: imgui.Key.a}
    return service


def test_constructor_loads_optional_font_and_live_bridge(monkeypatch, tmp_path):
    from src.client.ui.testing import live_bridge

    events = []
    context = object()
    io = FakeIO()
    window = SimpleNamespace(switch_to=lambda: events.append("switch"), dispatch_event="dispatch")
    bridge = SimpleNamespace()

    class FakeBridge:
        def __init__(self, path, **kwargs):
            events.append(("bridge", path, kwargs))
            bridge.kwargs = kwargs

        def close(self):
            pass

    monkeypatch.setenv("OPENPOWER_UI_ARTIFACTS", str(tmp_path / "artifacts"))
    monkeypatch.setattr(live_bridge, "LiveUIBridge", FakeBridge)
    monkeypatch.setattr(imgui_service_module.imgui, "create_context", lambda: context)
    monkeypatch.setattr(imgui_service_module.imgui, "get_io", lambda: io)
    monkeypatch.setattr(imgui_service_module, "OpenGL3Backend", lambda: "renderer")
    monkeypatch.setattr(ImGuiService, "_create_key_map", lambda _self: {1: "key"})
    monkeypatch.setattr(FontLoader, "configure_ui", lambda *args: events.append(("font", *args)))

    service = ImGuiService(window, tmp_path / "font.ttf", inspection_provider="inspection")

    assert events[0] == "switch"
    assert events[1] == ("font", io, tmp_path / "font.ttf")
    assert events[2][0:2] == ("bridge", tmp_path / "artifacts")
    assert bridge.kwargs["dispatch_window_event"] == "dispatch"
    assert service._ui_bridge is not None
    assert service.renderer == "renderer"


def test_capture_frame_reads_and_converts_the_current_framebuffer(monkeypatch):
    framebuffer = SimpleNamespace(size=(2, 2), read=lambda components: bytes(range(16)))
    service = bare_service(SimpleNamespace(ctx=SimpleNamespace(screen=framebuffer)))
    converted = []
    cv2 = ModuleType("cv2")
    cv2.COLOR_RGBA2BGRA = 9
    cv2.cvtColor = lambda image, mode: converted.append((image.copy(), mode)) or "converted"
    monkeypatch.setitem(sys.modules, "cv2", cv2)

    assert service._capture_ui_frame(Path("frame.png")) == "converted"
    assert converted[0][0].shape == (2, 2, 4)
    assert converted[0][1] == 9
    assert converted[0][0][0, 0, 0] == 8


def test_resize_and_timekeeping_clamp_nonpositive_deltas(monkeypatch):
    service = bare_service()
    sizes = []
    monkeypatch.setattr(imgui, "ImVec2", lambda width, height: sizes.append((width, height)) or (width, height))

    service.resize(1280, 720)
    service.update_time(-1)

    assert service.io.display_size == (1280.0, 720.0)
    assert service._current_delta_time == 1e-6
    assert service.real_fps == pytest.approx(100053.99999999999)


def test_new_frame_aborts_previous_bridge_frame_and_syncs_display_and_dpi(monkeypatch):
    service = bare_service()
    service._plot_context = "plot-context"
    service._frame_started = True
    service._current_delta_time = 0.25
    calls = []
    bridge = SimpleNamespace(
        abort_frame=lambda: calls.append("abort"),
        before_frame=lambda size: calls.append(("before", size)),
        start_frame=lambda size: calls.append(("start", size)),
    )
    service._ui_bridge = bridge
    monkeypatch.setattr(imgui, "set_current_context", lambda context: calls.append(("imgui-context", context)))
    monkeypatch.setattr(implot, "set_current_context", lambda context: calls.append(("plot-context", context)))
    monkeypatch.setattr(imgui, "end_frame", lambda: calls.append("end"))
    monkeypatch.setattr(imgui, "new_frame", lambda: calls.append("new"))
    monkeypatch.setattr(imgui, "ImVec2", lambda x, y: (x, y))
    service.window.get_size = lambda: (1280, 720)
    service.window.get_pixel_ratio = lambda: 1.5

    service.new_frame()

    assert service._frame_started is True
    assert service.io.delta_time == 0.25
    assert service.io.display_size == (1280.0, 720.0)
    assert service.io.display_framebuffer_scale == (1.5, 1.5)
    assert calls == [
        ("imgui-context", "imgui-context"),
        ("plot-context", "plot-context"),
        "end",
        "abort",
        ("before", (1280, 720)),
        "new",
        ("start", (1280, 720)),
    ]


def test_render_finalizes_imgui_and_resets_scissor_state(monkeypatch):
    service = bare_service(SimpleNamespace(ctx=SimpleNamespace(scissor=(1, 2, 3, 4))))
    service._frame_started = True
    service._plot_context = "plot-context"
    service.renderer = SimpleNamespace(render=lambda data: events.append(("renderer", data)))
    service._ui_bridge = SimpleNamespace(finish_frame=lambda: events.append("finish"))
    events = []
    monkeypatch.setattr(imgui, "set_current_context", lambda context: events.append(("context", context)))
    monkeypatch.setattr(implot, "set_current_context", lambda context: events.append(("plot-context", context)))
    monkeypatch.setattr(imgui, "render", lambda: events.append("render"))
    monkeypatch.setattr(imgui, "get_draw_data", lambda: "draw-data")

    service.render()

    assert service._frame_started is False
    assert service.window.ctx.scissor is None
    assert events == [
        ("context", "imgui-context"),
        ("plot-context", "plot-context"),
        "render",
        ("renderer", "draw-data"),
        "finish",
    ]


def test_render_noops_without_a_started_frame():
    service = bare_service()
    service._frame_started = False
    service.render()


def test_render_uses_pyglet_scissor_fallback_when_arcade_context_rejects_reset(monkeypatch):
    calls = []

    class BrokenContext:
        @property
        def scissor(self):
            return "active"

        @scissor.setter
        def scissor(self, _value):
            raise RuntimeError("setter unsupported")

    pyglet = ModuleType("pyglet")
    pyglet.__path__ = []
    gl = ModuleType("pyglet.gl")
    gl.GL_SCISSOR_TEST = 99
    gl.glDisable = lambda flag: calls.append(flag)
    pyglet.gl = gl
    monkeypatch.setitem(sys.modules, "pyglet", pyglet)
    monkeypatch.setitem(sys.modules, "pyglet.gl", gl)
    service = bare_service(SimpleNamespace(ctx=BrokenContext()))
    service._frame_started = True
    monkeypatch.setattr(imgui, "set_current_context", lambda _context: None)
    monkeypatch.setattr(imgui, "render", lambda: None)
    monkeypatch.setattr(imgui, "get_draw_data", lambda: None)

    service.render()

    assert calls == [99]


def test_shutdown_closes_bridge_then_releases_frame_and_contexts(monkeypatch):
    service = bare_service()
    service._plot_context = "plot"
    service._frame_started = True
    service._ui_bridge = SimpleNamespace(close=lambda: calls.append("close"))
    calls = []
    monkeypatch.setattr(imgui, "set_current_context", lambda context: calls.append(("context", context)))
    monkeypatch.setattr(imgui, "end_frame", lambda: calls.append("end_frame"))
    monkeypatch.setattr(imgui, "destroy_context", lambda context: calls.append(("destroy_imgui", context)))
    monkeypatch.setattr(implot, "destroy_context", lambda context: calls.append(("destroy_plot", context)))

    service.shutdown()

    assert calls == [
        "close",
        ("context", "imgui-context"),
        "end_frame",
        ("destroy_plot", "plot"),
        ("destroy_imgui", "imgui-context"),
    ]
    assert service._context is None
    assert service._plot_context is None
    assert service._frame_started is False


def test_mouse_and_keyboard_handlers_translate_events_and_capture_state():
    service = bare_service()
    io = service.io
    flags = arcade.key.MOD_CTRL | arcade.key.MOD_ALT | arcade.key.MOD_COMMAND

    assert service.on_mouse_press(3, 20, arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert service.on_mouse_press(3, 20, 99, 0) is True
    assert service.on_mouse_release(4, 30, arcade.MOUSE_BUTTON_RIGHT, 0) is True
    assert service.on_mouse_drag(5, 40, 1, 2, 1, flags) is True
    assert service.on_mouse_motion(6, 50, 1, 2) is True
    assert service.on_mouse_scroll(0, 0, 2, -1) is True
    assert service.on_key_press(arcade.key.A, flags) is True
    assert service.on_key_press(999999, 0) is True
    assert service.on_key_release(arcade.key.A, 0) is True
    assert service.on_text("éA") is True

    assert ("mouse_pos", (3, 80)) in io.events
    assert ("mouse_button", (0, True)) in io.events
    assert ("mouse_button", (1, False)) in io.events
    assert ("wheel", (2, -1)) in io.events
    assert ("character", (ord("é"),)) in io.events
    assert ("character", (ord("A"),)) in io.events
    assert ("key", (imgui.Key.a, True)) in io.events
    assert ("key", (imgui.Key.a, False)) in io.events
    assert ("key", (imgui.Key.mod_ctrl, True)) in io.events
    assert ("key", (imgui.Key.mod_shift, False)) in io.events
    assert ("key", (imgui.Key.mod_alt, True)) in io.events
    assert ("key", (imgui.Key.mod_super, True)) in io.events


@pytest.mark.parametrize(
    "button, expected",
    [
        (arcade.MOUSE_BUTTON_LEFT, 0),
        (arcade.MOUSE_BUTTON_RIGHT, 1),
        (arcade.MOUSE_BUTTON_MIDDLE, 2),
        (999, -1),
    ],
)
def test_mouse_button_mapping(button, expected):
    assert bare_service()._map_mouse_button(button) == expected


@pytest.mark.parametrize(
    "texture, expected",
    [
        (SimpleNamespace(glo=SimpleNamespace(glo_id="41")), 41),
        (SimpleNamespace(gl_id="42"), 42),
        (SimpleNamespace(), 0),
    ],
)
def test_texture_id_supports_current_and_legacy_arcade_shapes(texture, expected):
    assert ImGuiService.get_texture_id(texture) == expected
