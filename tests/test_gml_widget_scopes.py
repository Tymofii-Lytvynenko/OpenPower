from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.client.ui.core.gml_widgets import GMLWidgets


def test_input_float_restores_scaled_font_when_rendering_raises():
    native = MagicMock()
    native.get_style.return_value = SimpleNamespace(
        font_scale_main=1.5,
        font_scale_dpi=2.0,
    )
    native.input_float.side_effect = RuntimeError("render failed")

    with patch("src.client.ui.core.gml_widgets.imgui", native):
        with pytest.raises(RuntimeError, match="render failed"):
            GMLWidgets("Panel").input_float(
                "Value", "Value", 1.0, "panel.value", font_size=12.0
            )

    native.push_font.assert_called_once_with(None, 4.0)
    native.begin_disabled.assert_called_once_with(False)
    native.end_disabled.assert_called_once_with()
    native.pop_font.assert_called_once_with()


def test_input_float_without_source_font_does_not_change_font_stack():
    native = MagicMock()
    native.input_float.return_value = (False, 1.0)

    with patch("src.client.ui.core.gml_widgets.imgui", native):
        result = GMLWidgets("Panel").input_float(
            "Value", "Value", 1.0, "panel.value"
        )

    assert result == (False, 1.0)
    native.get_style.assert_not_called()
    native.push_font.assert_not_called()
    native.pop_font.assert_not_called()
