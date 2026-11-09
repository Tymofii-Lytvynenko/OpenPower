from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.core.window_setup import WindowSetupPolicy


def test_layout_size_override_viewport_fallback_and_overlap_filter():
    layout = SimpleNamespace(width=100, height=80)
    request = SimpleNamespace(
        gml_template="dialog",
        test_id="dialog.test",
        title="Dialog",
        w=400,
        h=300,
        size_override=(320, 200),
        avoid_overlaps=True,
    )

    resolved_layout, width, height = WindowSetupPolicy._resolve_layout_and_size(
        request,
        lambda *_args, **_kwargs: layout,
    )
    assert resolved_layout is layout
    assert (width, height) == (320, 200)

    imgui = Mock()
    imgui.get_io.return_value.display_size = SimpleNamespace(x=0, y=0)
    imgui.get_main_viewport.return_value.size = SimpleNamespace(x=640, y=480)
    assert WindowSetupPolicy._resolve_viewport_size(None, imgui) == (640, 480)

    current = object()
    other = object()
    assert WindowSetupPolicy._occupied_placements(
        request,
        "current",
        {"current": current, "other": other},
    ) == (other,)


def test_geometry_waits_for_a_valid_viewport_and_releases_the_wait_on_recovery():
    policy = WindowSetupPolicy(Mock())
    request = SimpleNamespace(follow_position=False, avoid_overlaps=False)
    placement = SimpleNamespace(
        x=5,
        y=6,
        width=300,
        height=200,
        viewport_changed=False,
    )
    imgui = Mock()
    imgui.Cond_.always = 1
    imgui.Cond_.first_use_ever = 2

    policy._schedule_geometry(
        request,
        None,
        "dialog",
        (0, 0),
        placement,
        has_layout=False,
        imgui_api=imgui,
    )
    assert policy._waiting_for_viewport == {"dialog"}

    imgui.set_next_window_pos.reset_mock()
    policy._schedule_geometry(
        request,
        None,
        "dialog",
        (800, 600),
        placement,
        has_layout=False,
        imgui_api=imgui,
    )

    assert policy._waiting_for_viewport == set()
    imgui.set_next_window_pos.assert_called_once_with((5, 6), imgui.Cond_.always)
    assert WindowSetupPolicy._position_condition(
        None,
        SimpleNamespace(follow_position=True, avoid_overlaps=False),
        "dialog",
        imgui,
    ) == imgui.Cond_.always
