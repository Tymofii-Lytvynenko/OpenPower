from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.client.ui.layouts import gml_popup


@pytest.mark.parametrize(("movable", "expected_flags"), [(True, 7), (False, 15)])
def test_popup_balances_imgui_scopes_when_content_raises(monkeypatch, movable, expected_flags):
    ui = MagicMock()
    ui.WindowFlags_ = SimpleNamespace(
        no_title_bar=1, no_resize=2, no_saved_settings=4, no_move=8
    )
    ui.Cond_ = SimpleNamespace(appearing=1)
    ui.StyleVar_ = SimpleNamespace(window_padding=1)
    ui.begin_popup_modal.return_value = (True, None)
    ui.get_window_pos.return_value = SimpleNamespace(x=0, y=0)
    ui.get_window_size.return_value = SimpleNamespace(x=221, y=95)
    monkeypatch.setattr(gml_popup, "imgui", ui)
    monkeypatch.setattr(gml_popup, "get_gml_layout", lambda _name: SimpleNamespace(width=221, height=95))
    monkeypatch.setattr(gml_popup, "gml_style", nullcontext)
    monkeypatch.setattr(gml_popup, "create_gml_layout_session", lambda *_args: object())
    monkeypatch.setattr(gml_popup, "use_gml_layout", lambda _session: nullcontext())

    with pytest.raises(RuntimeError, match="content failure"):
        with gml_popup.gml_popup_modal("popup", "Save_Confirmation_Window", movable=movable):
            raise RuntimeError("content failure")

    ui.begin_popup_modal.assert_called_once_with("popup", None, expected_flags)
    ui.pop_style_var.assert_called_once()
    ui.end_popup.assert_called_once()
