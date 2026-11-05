from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from imgui_bundle import imgui, implot

import src.client.services.imgui_service as imgui_service_module
import src.client.ui.core.font_loader as font_loader_module
from src.client.services.imgui_service import ImGuiService
from src.client.ui.core.font_loader import FontLoader


def _window() -> SimpleNamespace:
    return SimpleNamespace(
        switch_to=Mock(),
        get_pixel_ratio=lambda: 1.0,
        get_size=lambda: (1280, 720),
        height=720,
        ctx=SimpleNamespace(scissor=None),
    )


def test_imgui_service_pairs_implot_context_and_destroys_it_before_imgui(monkeypatch):
    monkeypatch.setattr(imgui_service_module, "OpenGL3Backend", Mock)
    monkeypatch.setattr(imgui, "new_frame", Mock())
    monkeypatch.setattr(imgui, "end_frame", Mock())
    service = ImGuiService(_window(), enable_implot=True)
    imgui_context = service._context
    implot_context = service._plot_context

    service.new_frame()

    assert imgui.get_current_context() == imgui_context
    assert implot.get_current_context() == implot_context

    service.shutdown()

    assert service._context is None
    assert service._plot_context is None


def test_imgui_service_can_skip_implot_for_views_that_do_not_plot(monkeypatch):
    monkeypatch.setattr(imgui_service_module, "OpenGL3Backend", Mock)
    service = ImGuiService(_window(), enable_implot=False)

    assert service._plot_context is None

    service.shutdown()


def test_font_loader_keeps_logical_metrics_for_dynamic_dpi_fonts(monkeypatch, tmp_path):
    style = SimpleNamespace(font_scale_main=0.5)
    io = SimpleNamespace()
    load_font = Mock()
    monkeypatch.setattr(FontLoader, "load_primary_font", load_font)
    monkeypatch.setattr(font_loader_module.imgui, "get_style", lambda: style)

    font_path = tmp_path / "main_font.ttf"
    FontLoader.configure_ui(io, font_path)

    load_font.assert_called_once_with(
        io,
        font_path,
        size_pixels=14.0,
        load_cjk=False,
        load_icons=True,
    )
    assert style.font_scale_main == 1.0
