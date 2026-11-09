from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from src.client.ui.layouts import gml_popup


def _install_popup_mocks(
    monkeypatch,
    *,
    opened=True,
    layout=None,
    session=None,
    titlebar_close=None,
):
    ui = MagicMock()
    ui.WindowFlags_ = SimpleNamespace(
        no_title_bar=1, no_resize=2, no_saved_settings=4, no_move=8
    )
    ui.Cond_ = SimpleNamespace(appearing=1)
    ui.StyleVar_ = SimpleNamespace(window_padding=1)
    ui.begin_popup_modal.return_value = (opened, None)
    ui.get_window_pos.return_value = SimpleNamespace(x=100.0, y=200.0)
    ui.get_window_size.return_value = SimpleNamespace(x=221.0, y=95.0)
    ui.button.return_value = False

    layout = layout or SimpleNamespace(
        width=221,
        height=95,
        components=[],
        component=MagicMock(return_value=None),
    )
    session = session or SimpleNamespace(rect_for=MagicMock())
    semantic = MagicMock(side_effect=lambda *_args, **_kwargs: nullcontext())

    monkeypatch.setattr(gml_popup, "imgui", ui)
    monkeypatch.setattr(gml_popup, "get_gml_layout", lambda _name: layout)
    monkeypatch.setattr(gml_popup, "gml_style", nullcontext)
    monkeypatch.setattr(gml_popup, "create_gml_layout_session", lambda *_args: session)
    monkeypatch.setattr(gml_popup, "use_gml_layout", lambda _session: nullcontext())
    monkeypatch.setattr(gml_popup, "semantic_region", semantic)
    monkeypatch.setattr(gml_popup, "apply_gml_message_geometry", MagicMock())
    monkeypatch.setattr(gml_popup, "render_gml_title", MagicMock())
    monkeypatch.setattr(
        gml_popup,
        "gml_titlebar_close",
        MagicMock(return_value=titlebar_close),
    )
    return ui, layout, session, semantic


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


@pytest.mark.parametrize("test_id", [None, "dialog.confirmation"])
def test_closed_popup_yields_false_and_marks_optional_semantic_region_hidden(monkeypatch, test_id):
    ui, _layout, _session, semantic = _install_popup_mocks(monkeypatch, opened=False)

    with gml_popup.gml_popup_modal("popup", "Save_Confirmation_Window", test_id=test_id) as opened:
        assert opened is False

    ui.end_popup.assert_not_called()
    if test_id:
        semantic.assert_called_once_with(test_id, "Save_Confirmation_Window", visible=False)
    else:
        semantic.assert_not_called()


@pytest.mark.parametrize("test_id", [None, "dialog.question"])
def test_open_popup_applies_dynamic_geometry_and_yields_visibility(monkeypatch, test_id):
    ui, layout, session, semantic = _install_popup_mocks(monkeypatch)
    geometry = SimpleNamespace(window_height=143)

    with gml_popup.gml_popup_modal(
        "popup",
        "Question_Window",
        test_id=test_id,
        message_geometry=geometry,
        movable=True,
    ) as opened:
        assert opened is True

    ui.set_next_window_size.assert_called_once_with((layout.width, 143), ui.Cond_.appearing)
    gml_popup.apply_gml_message_geometry.assert_called_once_with(session, geometry)
    if test_id:
        semantic.assert_called_once_with(test_id, "Question_Window", visible=True)
    else:
        semantic.assert_not_called()
    ui.end_popup.assert_called_once()
    ui.dummy.assert_not_called()


def test_title_close_fallback_clamps_hitbox_and_closes_popup(monkeypatch):
    close_component = SimpleNamespace(component_id="btnExit", path="/frmTitle/btnExit")
    unrelated_component = SimpleNamespace(component_id="other", path="/frmBody/other")
    inner_frame = SimpleNamespace(component_id="frmInner")
    close_rect = SimpleNamespace(x=300.0, y=-8.0, width=30.0, height=12.0)
    inner_rect = SimpleNamespace(x=10.0, y=20.0)
    layout = SimpleNamespace(
        width=221,
        height=95,
        components=[unrelated_component, close_component],
        component=MagicMock(return_value=inner_frame),
    )

    def rect_for(component):
        return close_rect if component is close_component else inner_rect

    session = SimpleNamespace(rect_for=MagicMock(side_effect=rect_for))
    ui, _layout, _session, semantic = _install_popup_mocks(
        monkeypatch,
        layout=layout,
        session=session,
    )
    ui.button.return_value = True

    with gml_popup.gml_popup_modal(
        "popup",
        "Save_Confirmation_Window",
        title="Confirm save",
        test_id="save.confirmation",
        movable=True,
    ) as opened:
        assert opened is False

    gml_popup.gml_titlebar_close.assert_called_once_with(layout)
    gml_popup.render_gml_title.assert_called_once_with(layout, "Confirm save", session)
    ui.button.assert_called_once_with(
        "×",
        (close_rect.width, close_rect.height),
        test_id="save.confirmation.close",
    )
    assert ui.set_cursor_screen_pos.call_args_list == [
        call((291.0, 200.0)),
        call((110.0, 220.0)),
    ]
    semantic.assert_called_once_with("save.confirmation", "Confirm save", visible=False)
    ui.close_current_popup.assert_called_once()
    ui.dummy.assert_called_once_with((1.0, 1.0))
    ui.end_popup.assert_called_once()
