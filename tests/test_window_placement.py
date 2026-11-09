from unittest.mock import Mock

from src.client.ui.core.window_placement import (
    WindowPlacement,
    WindowPlacementPolicy,
    WindowPlacementRequest,
    center_window,
    max_unoccupied_horizontal_width,
    resolve_non_overlapping_position,
    resolve_window_placement,
)
from src.client.ui.core.window_placement_registry import (
    WindowPlacementRegistry,
    WindowPlacementUpdate,
)
from src.client.ui.core.containers import WindowManager


def test_centered_window_is_viewport_relative_even_when_oversized():
    assert center_window((800, 600), (358, 248)) == (221, 176)
    assert center_window((200, 100), (358, 248)) == (-79, -74)


def test_right_anchored_panel_tracks_viewport_resize():
    previous = WindowPlacement(1909, 991, 1655, 129, 244, 450)

    placement = resolve_window_placement(
        (1655, 129),
        (244, 450),
        (1518, 836),
        previous,
        horizontal_anchor="right",
        horizontal_margin=10,
    )

    assert placement.viewport_changed
    assert (placement.x, placement.y, placement.width, placement.height) == (1264, 129, 244, 450)


def test_user_moved_panel_keeps_its_position_when_it_still_fits():
    previous = WindowPlacement(1909, 991, 714, 160, 257, 440)

    placement = resolve_window_placement(
        (260, 100),
        (257, 440),
        (1518, 836),
        previous,
        horizontal_anchor="left",
    )

    assert (placement.x, placement.y) == (714, 160)


def test_user_moved_right_anchored_panel_keeps_its_position_when_it_still_fits():
    previous = WindowPlacement(1909, 991, 714, 160, 257, 440)

    placement = resolve_window_placement(
        (1652, 160),
        (257, 440),
        (1518, 836),
        previous,
        horizontal_anchor="right",
        horizontal_margin=10,
    )

    assert (placement.x, placement.y) == (714, 160)


def test_user_moved_panel_is_clamped_back_into_view():
    previous = WindowPlacement(1909, 991, 1800, 900, 257, 440)

    placement = resolve_window_placement(
        (260, 100),
        (257, 440),
        (1518, 836),
        previous,
    )

    assert (placement.x, placement.y) == (1261, 396)


def test_window_size_is_capped_to_a_smaller_viewport():
    previous = WindowPlacement(1518, 836, 1264, 129, 244, 450)

    placement = resolve_window_placement(
        (1264, 129),
        (244, 450),
        (200, 160),
        previous,
        horizontal_anchor="right",
        horizontal_margin=10,
    )

    assert (placement.x, placement.y, placement.width, placement.height) == (0, 0, 200, 160)


def test_user_resized_non_gml_window_keeps_its_size_after_viewport_resize():
    previous = WindowPlacement(1909, 991, 500, 100, 520, 430)

    placement = resolve_window_placement(
        (300, 100),
        (400, 300),
        (1518, 836),
        previous,
        fixed_size=False,
    )

    assert (placement.width, placement.height) == (520, 430)


def test_same_viewport_does_not_force_a_position_update():
    previous = WindowPlacement(1518, 836, 714, 160, 257, 440)

    placement = resolve_window_placement(
        (260, 100),
        (257, 440),
        (1518, 836),
        previous,
    )

    assert not placement.viewport_changed
    assert (placement.x, placement.y) == (260, 100)


def test_overlap_avoidance_places_objectives_between_active_pillars():
    occupied = [
        WindowPlacement(1518, 836, 0, 0, 245, 408),
        WindowPlacement(1518, 836, 700, 164, 255, 389),
        WindowPlacement(1518, 836, 965, 180, 274, 362),
    ]

    position = resolve_non_overlapping_position(
        (980, 120),
        (354, 336),
        (1518, 836),
        occupied,
        margin=10,
        bottom_clearance=112,
    )

    assert position == (336, 120)
    assert position[1] + 336 <= 836 - 112
    for panel in occupied:
        assert position[0] + 354 + 10 <= panel.x or panel.x + panel.width + 10 <= position[0]


def test_overlap_avoidance_keeps_windows_in_viewport_when_no_free_slot_exists():
    occupied = [
        WindowPlacement(800, 600, 10, 80, 240, 520),
        WindowPlacement(800, 600, 260, 80, 250, 520),
        WindowPlacement(800, 600, 516, 126, 274, 362),
    ]

    position = resolve_non_overlapping_position(
        (436, 120),
        (354, 336),
        (800, 600),
        occupied,
        margin=10,
        bottom_clearance=112,
    )

    assert 0 <= position[0] <= 800 - 354
    assert 0 <= position[1] <= 600 - 336 - 112


def test_overlap_avoidance_reserves_top_system_bar_clearance():
    occupied = [
        WindowPlacement(800, 600, 223, 0, 577, 38),
        WindowPlacement(800, 600, 260, 100, 255, 391),
    ]

    position = resolve_non_overlapping_position(
        (24, 78),
        (400, 186),
        (800, 600),
        occupied,
        margin=8,
        top_clearance=46,
        bottom_clearance=112,
    )

    assert position[1] >= 46
    assert position == (400.0, 46)


def test_tutorial_can_use_free_horizontal_strip_beside_military_panel():
    occupied = [WindowPlacement(800, 600, 260, 100, 255, 391)]

    width = max_unoccupied_horizontal_width(800, occupied, margin=8)

    assert width == 277.0


def test_window_placement_policy_preserves_previous_position_and_resolves_overlap():
    previous = WindowPlacement(800, 600, 120, 90, 100, 80)
    request = WindowPlacementRequest(
        requested_position=(20, 30),
        requested_size=(100, 80),
        viewport_size=(800, 600),
        previous=previous,
        occupied=(),
        avoid_overlaps=True,
        horizontal_anchor="left",
        horizontal_margin=0,
        fixed_size=True,
        placement_margin=8,
        top_clearance=0,
        bottom_clearance=0,
    )

    resolved = WindowPlacementPolicy().resolve(request)

    assert (resolved.x, resolved.y) == (120, 90)
    assert (resolved.width, resolved.height) == (100, 80)
    assert not resolved.viewport_changed


def test_window_placement_policy_only_reuses_previous_position_for_same_viewport():
    previous = WindowPlacement(800, 600, 120, 90, 100, 80)

    def request_for(previous_placement, *, viewport_size=(800, 600), avoid_overlaps=True):
        return WindowPlacementRequest(
            requested_position=(20, 30),
            requested_size=(100, 80),
            viewport_size=viewport_size,
            previous=previous_placement,
            occupied=(),
            avoid_overlaps=avoid_overlaps,
            horizontal_anchor="left",
            horizontal_margin=0,
            fixed_size=True,
            placement_margin=8,
            top_clearance=0,
            bottom_clearance=0,
        )

    assert WindowPlacementPolicy._previous_placement_for_same_viewport(
        request_for(None)
    ) is None
    assert WindowPlacementPolicy._previous_placement_for_same_viewport(
        request_for(previous, viewport_size=(801, 600))
    ) is None
    assert WindowPlacementPolicy._previous_placement_for_same_viewport(
        request_for(previous, viewport_size=(800, 601))
    ) is None
    assert WindowPlacementPolicy._previous_placement_for_same_viewport(
        request_for(previous, avoid_overlaps=False)
    ) is None


def test_horizontal_unoccupied_width_is_zero_for_nonpositive_viewport():
    assert max_unoccupied_horizontal_width(0, ()) == 0.0
    assert max_unoccupied_horizontal_width(-100, ()) == 0.0


def test_window_manager_reanchors_live_panel_after_viewport_resize(tmp_path):
    from imgui_bundle import imgui as native

    from src.client.ui.core.containers import WindowManager
    from src.client.ui.core.instrumented_imgui import imgui

    test_id = "window-placement.resize.integration"
    WindowManager._placements.pop(test_id, None)
    context = native.create_context()
    try:
        io = native.get_io()
        io.display_size = native.ImVec2(1909.0, 991.0)
        io.display_framebuffer_scale = native.ImVec2(1.0, 1.0)
        io.delta_time = 1.0 / 60.0
        io.backend_flags |= native.BackendFlags_.renderer_has_textures
        io.set_ini_filename(str(tmp_path / "window.ini"))

        native.new_frame()
        with WindowManager.window(
            "ECONOMY",
            x=1600,
            y=100,
            w=244,
            h=450,
            test_id=test_id,
            horizontal_anchor="right",
            horizontal_margin=10,
        ) as opened:
            assert opened
            first_position = imgui.get_window_pos()
            assert (first_position.x, first_position.y) == (1655, 100)
        native.end_frame()

        io.display_size = native.ImVec2(1518.0, 836.0)
        native.new_frame()
        with WindowManager.window(
            "ECONOMY",
            x=1600,
            y=100,
            w=244,
            h=450,
            test_id=test_id,
            horizontal_anchor="right",
            horizontal_margin=10,
        ) as opened:
            assert opened
            resized_position = imgui.get_window_pos()
            assert (resized_position.x, resized_position.y) == (1264, 100)
        native.end_frame()
    finally:
        WindowManager._placements.pop(test_id, None)
        native.destroy_context(context)


def test_gml_panel_ignores_saved_position_from_a_different_viewport(tmp_path):
    from imgui_bundle import imgui as native

    from src.client.ui.core.containers import WindowManager
    from src.client.ui.core.instrumented_imgui import imgui

    test_id = "economy.panel"
    WindowManager._placements.pop(test_id, None)
    ini_path = tmp_path / "window.ini"
    ini_path.write_text(
        "\n".join((
            "[Window][ECONOMY##openpower.gml.v1:economy.panel]",
            "Pos=1655,261",
            "Size=244,450",
            "Collapsed=0",
        )),
        encoding="utf-8",
    )
    context = native.create_context()
    try:
        io = native.get_io()
        io.display_size = native.ImVec2(1518.0, 836.0)
        io.display_framebuffer_scale = native.ImVec2(1.0, 1.0)
        io.delta_time = 1.0 / 60.0
        io.backend_flags |= native.BackendFlags_.renderer_has_textures
        io.set_ini_filename(str(ini_path))
        native.load_ini_settings_from_disk(str(ini_path))

        native.new_frame()
        with WindowManager.window(
            "ECONOMY",
            x=1600,
            y=100,
            w=244,
            h=450,
            test_id=test_id,
            gml_template="Economic_Window",
            horizontal_anchor="right",
            horizontal_margin=10,
        ) as opened:
            assert opened
            position = imgui.get_window_pos()
            assert (position.x, position.y) == (1264, 100)
        native.end_frame()
    finally:
        WindowManager._placements.pop(test_id, None)
        native.destroy_context(context)


def test_standard_panel_clamps_stale_ini_position_into_viewport(tmp_path):
    from imgui_bundle import imgui as native

    from src.client.ui.core.containers import WindowManager
    from src.client.ui.core.instrumented_imgui import imgui

    test_id = "window-placement.stale-ini.integration"
    WindowManager._placements.pop(test_id, None)
    ini_path = tmp_path / "window.ini"
    ini_path.write_text(
        "\n".join((
            "[Window][MIGRATION]",
            "Pos=1600,700",
            "Size=520,600",
            "Collapsed=0",
        )),
        encoding="utf-8",
    )
    context = native.create_context()
    try:
        io = native.get_io()
        io.display_size = native.ImVec2(1518.0, 836.0)
        io.display_framebuffer_scale = native.ImVec2(1.0, 1.0)
        io.delta_time = 1.0 / 60.0
        io.backend_flags |= native.BackendFlags_.renderer_has_textures
        io.set_ini_filename(str(ini_path))
        native.load_ini_settings_from_disk(str(ini_path))

        native.new_frame()
        with WindowManager.window(
            "MIGRATION",
            x=80,
            y=90,
            w=520,
            h=600,
            test_id=test_id,
        ) as opened:
            assert opened
            position = imgui.get_window_pos()
            size = imgui.get_window_size()
            assert (position.x, position.y) == (998, 236)
            assert (size.x, size.y) == (520, 600)
        native.end_frame()
    finally:
        WindowManager._placements.pop(test_id, None)
        native.destroy_context(context)


def test_standard_panel_clamps_stale_ini_size_to_viewport(tmp_path):
    from imgui_bundle import imgui as native

    from src.client.ui.core.containers import WindowManager
    from src.client.ui.core.instrumented_imgui import imgui

    test_id = "window-placement.stale-size.integration"
    WindowManager._placements.pop(test_id, None)
    ini_path = tmp_path / "window.ini"
    ini_path.write_text(
        "\n".join((
            "[Window][MIGRATION]",
            "Pos=100,80",
            "Size=1800,1000",
            "Collapsed=0",
        )),
        encoding="utf-8",
    )
    context = native.create_context()
    try:
        io = native.get_io()
        io.display_size = native.ImVec2(1518.0, 836.0)
        io.display_framebuffer_scale = native.ImVec2(1.0, 1.0)
        io.delta_time = 1.0 / 60.0
        io.backend_flags |= native.BackendFlags_.renderer_has_textures
        io.set_ini_filename(str(ini_path))
        native.load_ini_settings_from_disk(str(ini_path))

        for frame in range(2):
            native.new_frame()
            with WindowManager.window(
                "MIGRATION",
                x=80,
                y=90,
                w=520,
                h=600,
                test_id=test_id,
            ) as opened:
                assert opened
                position = imgui.get_window_pos()
                size = imgui.get_window_size()
                assert (position.x, position.y) == (0, 0)
                if frame == 1:
                    assert (size.x, size.y) == (1518, 836)
            native.end_frame()
    finally:
        WindowManager._placements.pop(test_id, None)
        native.destroy_context(context)


def test_live_inspection_preserves_moved_window_while_scenario_telemetry_pins_it(tmp_path):
    from imgui_bundle import imgui as native

    from src.client.ui.core.containers import WindowManager
    from src.client.ui.core.testability import UIRunTelemetry
    from src.client.ui.testing.live_bridge import LiveUIBridge

    bridge = LiveUIBridge(tmp_path / "bridge")
    try:
        for label, telemetry, expected in (
            ("live", bridge.telemetry, (160, 150)),
            ("scenario", UIRunTelemetry((800, 600)), (100, 100)),
        ):
            test_id = f"window-placement.telemetry.{label}"
            WindowManager._placements.pop(test_id, None)
            context = native.create_context()
            try:
                io = native.get_io()
                io.display_size = native.ImVec2(800, 600)
                io.display_framebuffer_scale = native.ImVec2(1, 1)
                io.delta_time = 1 / 60
                io.backend_flags |= native.BackendFlags_.renderer_has_textures
                io.set_ini_filename(str(tmp_path / f"{label}.ini"))
                telemetry.viewport_size = (800, 600)
                for frame in range(2):
                    native.new_frame()
                    with telemetry.frame(), WindowManager.window(
                        f"Telemetry {label}", x=100, y=100, w=300, h=200, test_id=test_id
                    ) as opened:
                        assert opened
                        if frame == 0:
                            native.set_window_pos((160, 150), native.Cond_.always)
                        else:
                            position = native.get_window_pos()
                            assert (position.x, position.y) == expected
                    native.end_frame()
            finally:
                WindowManager._placements.pop(test_id, None)
                native.destroy_context(context)
    finally:
        bridge.close()


def test_placement_registry_skips_invalid_viewports_and_exposes_the_frame():
    registry = WindowPlacementRegistry()
    imgui_api = Mock()
    request = WindowPlacementUpdate(
        window_key="invalid.viewport",
        viewport_size=(0.0, 0.0),
        live_placement=True,
        follow_position=False,
        opened=True,
    )

    assert registry.visible_frame_placements() == ()
    registry.update(request, imgui_api=imgui_api)

    assert registry.placements == {}
    assert registry.visible_frame_placements() == ()
    imgui_api.get_window_pos.assert_not_called()


def test_window_manager_forwards_placement_and_close_requests(monkeypatch):
    placements = (WindowPlacement(800, 600, 10, 20, 300, 200),)
    registry = Mock()
    registry.visible_frame_placements.return_value = placements
    monkeypatch.setattr(WindowManager, "_placement_registry", registry)
    monkeypatch.setattr(WindowManager, "_close_requests", set())

    assert WindowManager.visible_frame_placements() is placements
    WindowManager.request_close("test.window")

    assert WindowManager._close_requests == {"test.window"}
