from types import SimpleNamespace

import pytest

from src.client.ui.core import theme as theme_module
from src.client.ui.core.theme import UIColors, UITheme, with_alpha


class ColorIndex:
    def __init__(self):
        self.names = []

    def __getattr__(self, name):
        self.names.append(name)
        return name


def test_with_alpha_preserves_rgb_and_returns_a_new_color_tuple():
    original = (0.1, 0.2, 0.3, 0.9)

    adjusted = with_alpha(original, 0.4)

    assert adjusted == (0.1, 0.2, 0.3, 0.4)
    assert original == (0.1, 0.2, 0.3, 0.9)
    assert adjusted is not original


def test_colors_expose_default_palette_and_allow_semantic_overrides():
    colors = UIColors()
    assert colors.text_main == (1.0, 1.0, 1.0, 1.0)
    assert colors.bg_child == (0.0, 0.0, 0.0, 0.0)
    assert colors.accent == colors.info
    assert colors.positive == colors.economy
    assert colors.negative == colors.military
    assert colors.interaction_active == colors.pressed_neutral

    custom = UIColors(accent=(0.2, 0.3, 0.4, 1.0), warning=(1.0, 0.5, 0.0, 1.0))
    assert custom.accent == (0.2, 0.3, 0.4, 1.0)
    assert custom.warning == (1.0, 0.5, 0.0, 1.0)


def test_theme_applies_geometry_and_full_palette_to_imgui(monkeypatch):
    style = SimpleNamespace(set_color_=lambda index, color: calls.append((index, color)))
    calls = []
    color_index = ColorIndex()
    monkeypatch.setattr(
        theme_module,
        "imgui",
        SimpleNamespace(get_style=lambda: style, Col_=color_index),
    )
    colors = UIColors(accent=(0.2, 0.4, 0.6, 1.0), text_dim=(0.5, 0.5, 0.5, 1.0))
    theme = UITheme(colors=colors, rounding=5.0)

    theme.apply()

    assert style.window_padding == (14, 14)
    assert style.frame_padding == (8, 5)
    assert style.item_spacing == (10, 8)
    assert style.window_rounding == 5.0
    assert style.frame_rounding == 5.0
    assert style.popup_rounding == 5.0
    assert style.grab_rounding == 5.0
    assert style.tab_rounding == 5.0
    assert style.window_border_size == 0.0
    assert style.frame_border_size == 0.0
    assert len(calls) == len(color_index.names)
    assert len(calls) > 40
    assert ("text", colors.text_main) in calls
    assert ("text_disabled", colors.text_dim) in calls
    assert ("check_mark", colors.accent) in calls
    assert ("text_selected_bg", (0.2, 0.4, 0.6, 0.4)) in calls
    assert ("tab_dimmed", (0.5, 0.5, 0.5, 0.2)) in calls
    assert ("table_row_bg_alt", (1.0, 1.0, 1.0, 0.02)) in calls


def test_theme_apply_reads_the_current_imgui_style(monkeypatch):
    first = SimpleNamespace(set_color_=lambda *_args: None)
    second = SimpleNamespace(set_color_=lambda *_args: None)
    styles = iter([first, second])
    monkeypatch.setattr(
        theme_module,
        "imgui",
        SimpleNamespace(get_style=lambda: next(styles), Col_=ColorIndex()),
    )

    theme = UITheme()
    theme.apply()
    theme.apply()

    assert first.window_rounding == second.window_rounding == 0.0
