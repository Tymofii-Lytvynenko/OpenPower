from unittest.mock import MagicMock

from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.primitives import UIPrimitives


def test_gml_button_delegates_without_losing_disabled_or_source_identity(
    monkeypatch,
):
    native = MagicMock()
    native.is_item_hovered.return_value = True
    calls = []
    monkeypatch.setattr("src.client.ui.core.gml_widgets.imgui", native)
    monkeypatch.setattr(
        UIPrimitives,
        "button",
        lambda label, **kwargs: calls.append((label, kwargs)) or True,
    )
    widgets = GMLWidgets("Settings_Window/frmInner")

    clicked = widgets.button(
        "btnApply",
        "Apply",
        "settings.apply",
        enabled=False,
        tooltip="Changes are not valid yet.",
        dynamic_enabled=True,
    )

    assert clicked is True
    assert calls == [
        (
            "Apply",
            {
                "test_id": "settings.apply",
                "enabled": False,
                "gml_id": "Settings_Window/frmInner/btnApply",
                "gml_enabled": False,
            },
        )
    ]
    native.begin_disabled.assert_called_once_with(True)
    native.end_disabled.assert_called_once_with()
    native.pop_style_var.assert_called_once_with()
    native.is_item_hovered.assert_called_once_with(
        native.HoveredFlags_.allow_when_disabled
    )
    native.set_tooltip.assert_called_once_with("Changes are not valid yet.")
