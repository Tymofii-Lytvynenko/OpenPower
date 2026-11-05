from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.client.ui.core.composer import UIComposer
from src.client.ui.core.primitives import UIPrimitives


def _theme():
    return SimpleNamespace(
        colors=SimpleNamespace(
            interaction_active=(0.1, 0.2, 0.3, 1.0),
            bg_input=(0.2, 0.3, 0.4, 1.0),
            text_dim=(0.5, 0.6, 0.7, 1.0),
        )
    )


def test_composer_icon_toggle_delegates_with_its_theme(monkeypatch):
    theme = _theme()
    captured = {}

    def draw_toggle(icon, color, is_active, width, height, **kwargs):
        captured.update(
            icon=icon,
            color=color,
            is_active=is_active,
            width=width,
            height=height,
            **kwargs,
        )
        return True

    monkeypatch.setattr(UIPrimitives, "icon_toggle", draw_toggle)

    clicked = UIComposer(theme).draw_icon_toggle("icon", (1, 0, 0, 1), True, 36, 42)

    assert clicked is True
    assert captured == {
        "icon": "icon",
        "color": (1, 0, 0, 1),
        "is_active": True,
        "width": 36,
        "height": 42,
        "show_inactive_indicator": True,
        "theme": theme,
    }


@pytest.mark.parametrize(
    ("is_active", "expected_background", "expected_indicator"),
    (
        (True, "interaction_active", (1.0, 0.0, 0.0, 1.0)),
        (False, "bg_input", "text_dim"),
    ),
)
def test_icon_toggle_uses_the_supplied_theme(is_active, expected_background, expected_indicator):
    native = MagicMock()
    native.get_item_rect_min.return_value = SimpleNamespace(x=10.0, y=20.0)
    native.get_item_rect_max.return_value = SimpleNamespace(x=60.0, y=70.0)
    native.get_color_u32.side_effect = lambda color: color
    theme = _theme()

    with patch("src.client.ui.core.primitives.imgui", native):
        UIPrimitives.icon_toggle(
            "icon",
            (1.0, 0.0, 0.0, 1.0),
            is_active,
            show_inactive_indicator=True,
            theme=theme,
        )

    native.push_style_color.assert_called_once_with(
        native.Col_.button,
        getattr(theme.colors, expected_background),
    )
    native.get_color_u32.assert_called_once_with(
        getattr(theme.colors, expected_indicator)
        if isinstance(expected_indicator, str)
        else expected_indicator
    )
