from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.client.ui.core import window_lifecycle as lifecycle_module
from src.client.ui.core.window_lifecycle import WindowLifecycle
from src.client.ui.layouts.gml_layout import GMLWindowLayout


def test_custom_titlebar_removes_conflicting_menu_bar_flag():
    imgui = SimpleNamespace(
        WindowFlags_=SimpleNamespace(no_collapse=1, no_title_bar=2, menu_bar=4)
    )

    flags = WindowLifecycle._resolve_flags(4, True, imgui)

    assert flags == 3


def test_titlebar_close_and_pending_close_request_hide_the_window():
    request = SimpleNamespace(closable=True, test_id=None, title="Dialog")
    setup = SimpleNamespace(window_key="dialog")
    with patch.object(
        WindowLifecycle,
        "_prepare_layout_scope",
        return_value=(None, True),
    ):
        with WindowLifecycle.body(
            request,
            setup,
            SimpleNamespace(),
            expanded=True,
            opened=True,
            close_requests=set(),
        ) as opened:
            assert opened is False

    close_requests = {"dialog"}
    assert not WindowLifecycle._apply_close_request(
        request,
        setup,
        True,
        close_requests,
    )
    assert close_requests == set()


def test_layout_session_scales_the_source_frame_to_a_narrow_viewport():
    layout = GMLWindowLayout(
        template="dialog",
        width=100,
        height=80,
        sections=(),
        components=(),
    )
    window_position = SimpleNamespace(x=10, y=20)
    imgui = Mock()
    imgui.get_window_pos.return_value = window_position
    imgui.get_window_size.return_value = SimpleNamespace(x=50, y=80)
    session = Mock()

    with patch.object(lifecycle_module, "GMLLayoutSession", return_value=session):
        actual_session, actual_position = WindowLifecycle._create_layout_session(
            layout,
            True,
            imgui,
        )

    assert actual_session is session
    assert actual_position is window_position
    session.scale_subtree_x.assert_called_once_with("dialog", 0.5)
    session.apply_base_window_titlebar_rules.assert_called_once_with()


def test_custom_titlebar_close_button_reports_a_close_click():
    close_component = object()
    inner_component = object()
    layout = Mock()
    layout.template = "dialog"
    layout.component.return_value = inner_component
    layout_session = Mock()
    layout_session.rect_for.side_effect = [
        SimpleNamespace(x=3, y=4, width=20, height=15),
        SimpleNamespace(x=8, y=9),
    ]
    imgui = Mock()
    imgui.button.return_value = True

    with (
        patch.object(lifecycle_module, "gml_titlebar_close", return_value=close_component),
        patch.object(lifecycle_module, "render_gml_title"),
    ):
        closed = WindowLifecycle._render_titlebar(
            layout,
            "Dialog",
            layout_session,
            SimpleNamespace(x=10, y=20),
            closable=True,
            test_id="dialog",
            imgui_api=imgui,
        )

    assert closed is True
    imgui.button.assert_called_once_with(
        "×",
        (20, 15),
        test_id="dialog.close",
    )
