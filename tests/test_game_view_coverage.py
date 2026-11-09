from types import SimpleNamespace
from unittest.mock import Mock

import arcade
import pytest

from src.client.views import game_view as game_view_module
from src.client.views.game_view import GameView
from src.shared.actions import ActionDispatchUnitDeployment


def view_with(**overrides):
    view = GameView.__new__(GameView)
    imgui = overrides.pop("imgui", None)
    nav = overrides.pop("nav", None)
    defaults = {
        "player_tag": "UKR",
        "unit_interactions": Mock(),
        "layout": Mock(),
        "viewport_ctrl": Mock(),
        "renderer": Mock(),
        "battle_effect_renderer": Mock(),
        "window": SimpleNamespace(height=720),
        "selected_region_id": None,
        "_drag_threshold": 5.0,
        "_drag_start_pos": None,
        "_selection_rect_start": None,
        "_selection_rect_current": None,
        "_right_drag_start_pos": None,
        "_right_context_unit_id": None,
        "_context_click_pos": None,
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        setattr(view, name, value)
    if imgui is not None:
        view.window.imgui = imgui
    if nav is not None:
        view.window.nav = nav
    return view


def install_init_dependencies(monkeypatch, shared_renderer):
    window = SimpleNamespace(shared_renderer=shared_renderer, settings=object())
    monkeypatch.setattr(game_view_module.BaseImGuiView, "__init__", lambda instance: setattr(instance, "window", window))

    camera = Mock()
    renderer = SimpleNamespace(
        camera=camera, width=200, height=100, globe_radius=50,
        set_overlay_style=Mock(),
    )
    world_camera = Mock()
    network = Mock()
    viewport = Mock()
    unit_renderer = Mock()
    event_renderer = Mock()
    battle_renderer = Mock()
    details = Mock()
    map_information = Mock()
    interactions = Mock()
    layout = Mock()
    context_menu = Mock()
    order_prompt = Mock()

    monkeypatch.setattr(game_view_module, "NetworkClient", Mock(return_value=network))
    monkeypatch.setattr(game_view_module.arcade, "Camera2D", Mock(return_value=world_camera))
    monkeypatch.setattr(game_view_module, "CameraController", Mock(return_value=camera))
    map_renderer = Mock(return_value=renderer)
    monkeypatch.setattr(game_view_module, "MapRenderer", map_renderer)
    monkeypatch.setattr(game_view_module, "ViewportController", Mock(return_value=viewport))
    monkeypatch.setattr(game_view_module, "UnitRenderer", Mock(return_value=unit_renderer))
    monkeypatch.setattr(game_view_module, "EventRenderer", Mock(return_value=event_renderer))
    monkeypatch.setattr(game_view_module, "BattleEffectRenderer", Mock(return_value=battle_renderer))
    monkeypatch.setattr(game_view_module, "UnitDetailsWindow", Mock(return_value=details))
    monkeypatch.setattr(game_view_module, "MapInformationWindows", Mock(return_value=map_information))
    monkeypatch.setattr(game_view_module, "UnitInteractionController", Mock(return_value=interactions))
    monkeypatch.setattr(game_view_module, "GameLayout", Mock(return_value=layout))
    monkeypatch.setattr(game_view_module, "UnitContextMenu", Mock(return_value=context_menu))
    monkeypatch.setattr(game_view_module, "UnitOrderTargetingPrompt", Mock(return_value=order_prompt))

    config = Mock()
    config.get_asset_path.side_effect = lambda path: f"asset:{path}"
    session = SimpleNamespace(map_data=SimpleNamespace(height=100))
    return SimpleNamespace(
        window=window, camera=camera, renderer=renderer, world_camera=world_camera,
        network=network, viewport=viewport, unit_renderer=unit_renderer,
        event_renderer=event_renderer, battle_renderer=battle_renderer,
        details=details, map_information=map_information, interactions=interactions,
        layout=layout, context_menu=context_menu, order_prompt=order_prompt,
        config=config, session=session, map_renderer=map_renderer,
    )


def test_init_reuses_shared_renderer_and_composes_services(monkeypatch):
    shared_renderer = SimpleNamespace(
        camera=Mock(), width=200, height=100, globe_radius=50, set_overlay_style=Mock(),
    )
    deps = install_init_dependencies(monkeypatch, shared_renderer)
    shared_renderer.camera = deps.camera

    view = GameView(deps.session, deps.config, "UKR", initial_pos=(20, 30))

    assert view.renderer is shared_renderer
    assert view.cam_ctrl is shared_renderer.camera
    shared_renderer.set_overlay_style.assert_called_once_with(enabled=True, opacity=0.90)
    deps.map_renderer.assert_not_called()
    deps.camera.look_at_pixel_coords.assert_called_once_with(20, 70, 200, 100)
    assert view._deployment_drag_unit_ids == ()
    assert view._visible_owners_cache is None


def test_init_builds_fallback_renderer_and_wires_owned_selection(monkeypatch):
    deps = install_init_dependencies(monkeypatch, None)

    view = GameView(deps.session, deps.config, "UKR")

    deps.map_renderer.assert_called_once_with(
        camera=deps.camera,
        map_data=deps.session.map_data,
        map_img_path="asset:map/regions.png",
        terrain_img_path="asset:map/terrain.png",
    )
    deps.camera.look_at_pixel_coords.assert_not_called()
    assert view.viewport_ctrl is deps.viewport
    assert view.renderer is deps.renderer
    assert view.cam_ctrl is deps.camera
    interaction_kwargs = game_view_module.UnitInteractionController.call_args.kwargs
    assert interaction_kwargs["can_box_select_unit"](SimpleNamespace(owner="ukr")) is True
    assert interaction_kwargs["can_box_select_unit"](SimpleNamespace(owner="POL")) is False


def test_view_callbacks_update_selection_readiness_and_refresh_on_show():
    view = view_with(unit_interactions=Mock(), viewport_ctrl=Mock(), window=SimpleNamespace())
    view.on_selection_changed(42)
    view._set_unit_readiness("unit-1", "reserve")

    assert view.selected_region_id == 42
    assert view.unit_interactions.selected_unit_ids == {"unit-1"}
    view.unit_interactions.set_selected_units_readiness.assert_called_once_with("reserve")

    view.on_show_view()

    assert view.window.background_color == (10, 10, 10, 255)
    view.viewport_ctrl.refresh_map_layer.assert_called_once_with()


def test_start_deployment_drag_normalizes_and_deduplicates_ids():
    view = view_with()
    view._start_deployment_drag([" unit-1 ", "", None, "unit-1", "unit-2"])
    assert view._deployment_drag_unit_ids == ("unit-1", "unit-2")
    view._start_deployment_drag(" unit-3 ")
    assert view._deployment_drag_unit_ids == ("unit-3",)
    view._start_deployment_drag([" ", ""])
    assert view._deployment_drag_unit_ids == ()


def test_deployment_mouse_release_falls_back_to_base_without_pending_drag(monkeypatch):
    view = view_with()
    base_release = Mock()
    monkeypatch.setattr(game_view_module.BaseImGuiView, "on_mouse_release", base_release)

    GameView.on_mouse_release(view, 1, 2, arcade.MOUSE_BUTTON_RIGHT, 3)
    view._deployment_drag_unit_ids = ("unit-1",)
    GameView.on_mouse_release(view, 1, 2, arcade.MOUSE_BUTTON_RIGHT, 3)

    assert base_release.call_count == 2


@pytest.mark.parametrize(
    ("region_id", "over_ui", "expected"),
    [(8, False, 1), (0, False, 0), (8, True, 0)],
)
def test_deployment_mouse_release_only_dispatches_valid_world_drops(monkeypatch, region_id, over_ui, expected):
    imgui = SimpleNamespace(on_mouse_release=Mock())
    monkeypatch.setattr(GameView, "imgui", property(lambda _self: imgui))
    renderer = Mock()
    renderer.get_region_id_at_screen_pos.return_value = region_id
    network = Mock(player_id="player-1")
    view = view_with(
        renderer=renderer, net=network, _deployment_drag_unit_ids=("unit-1",),
        _deployment_drop_over_ui=over_ui,
    )

    GameView.on_mouse_release(view, 10, 20, arcade.MOUSE_BUTTON_LEFT, 0)

    assert view._deployment_drag_unit_ids == ()
    imgui.on_mouse_release.assert_called_once_with(10, 20, arcade.MOUSE_BUTTON_LEFT, 0)
    assert len(network.send_action.call_args_list) == expected
    if expected:
        assert network.send_action.call_args.args[0] == ActionDispatchUnitDeployment(
            player_id="player-1", unit_id="unit-1", destination_region_id=8,
        )


def test_update_forwards_delta_and_pending_navigation():
    view = view_with(imgui=Mock(), layout=Mock(), nav=Mock())

    GameView.on_game_update(view, 0.25)

    view.imgui.update_time.assert_called_once_with(0.25)
    view.layout.dispatch_pending_navigation.assert_called_once_with(view.nav)


def test_draw_renders_world_overlays_and_ui_with_cached_owner_filter(monkeypatch):
    ctx = SimpleNamespace(DEPTH_TEST=1, BLEND=2, enable_only=Mock())
    window = SimpleNamespace(
        ctx=ctx, get_size=Mock(return_value=(1920, 1080)), use=Mock(), height=720,
        settings=SimpleNamespace(settings=SimpleNamespace(reduce_motion=True)),
    )
    imgui = Mock()
    native_imgui = SimpleNamespace(
        HoveredFlags_=SimpleNamespace(any_window=7),
        is_window_hovered=Mock(return_value=True),
    )
    monkeypatch.setattr(game_view_module, "imgui", native_imgui)
    state = object()
    view = view_with(
        window=window, imgui=imgui, clear=Mock(), net=Mock(),
        viewport_ctrl=Mock(), renderer=Mock(), unit_interactions=Mock(),
        unit_renderer=Mock(), event_renderer=Mock(), battle_effect_renderer=Mock(),
        layout=Mock(), unit_context_menu=Mock(), unit_order_targeting_prompt=Mock(),
        unit_details_window=Mock(), map_information=Mock(), nav=Mock(),
        _active_selection_rect=Mock(return_value=(1, 2, 3, 4)),
        _render_map_information=Mock(), _visible_unit_owners=Mock(return_value={"UKR", "POL"}),
    )
    view.net.get_state.return_value = state
    view.net.get_display_total_minutes.return_value = 120
    view.viewport_ctrl.show_all_units = False
    view.viewport_ctrl.selected_country_tag = "POL"
    view.viewport_ctrl.show_engagement_zones = True
    view.unit_interactions.selected_unit_id = "unit-1"
    view.unit_interactions.selected_unit_ids = {"unit-1"}
    view.unit_interactions.hovered_unit_id = "unit-2"
    view.unit_interactions.drag_preview = "preview"
    imgui.real_fps = 60

    GameView.on_draw(view)

    assert ctx.scissor is None
    assert ctx.viewport == (0, 0, 1920, 1080)
    ctx.enable_only.assert_called_once_with(1, 2)
    view.clear.assert_called_once_with()
    imgui.new_frame.assert_called_once_with()
    view.viewport_ctrl.refresh_map_layer_if_stale.assert_called_once_with(state)
    view.renderer.draw.assert_called_once_with()
    window.use.assert_called_once_with()
    view._visible_unit_owners.assert_called_once_with(state, "POL")
    unit_render = view.unit_renderer.render.call_args.kwargs
    assert unit_render["state"] is state
    assert unit_render["visible_owners"] == {"UKR", "POL"}
    assert unit_render["selection_rect"] == (1, 2, 3, 4)
    assert unit_render["show_engagement_zones"] is True
    view.event_renderer.render.assert_called_once_with(state)
    view.battle_effect_renderer.render.assert_called_once_with(state, 120, reduce_motion=True)
    view.layout.render.assert_called_once_with(
        None, 60, view.nav, state=state, presentation_total_minutes=120,
    )
    view.unit_order_targeting_prompt.render.assert_called_once_with(
        view.unit_interactions.pending_order_mode,
        view.unit_interactions.cancel_order_targeting,
    )
    view._render_map_information.assert_called_once_with(state)
    imgui.render.assert_called_once_with()


def test_draw_without_state_skips_visibility_lookup_and_contains_ui_errors(monkeypatch, capsys):
    window = SimpleNamespace(
        ctx=SimpleNamespace(DEPTH_TEST=1, BLEND=2, enable_only=Mock()),
        get_size=Mock(return_value=(800, 600)), use=Mock(), height=600,
    )
    imgui = Mock()
    native_imgui = SimpleNamespace(
        HoveredFlags_=SimpleNamespace(any_window=1),
        is_window_hovered=Mock(return_value=False),
    )
    monkeypatch.setattr(game_view_module, "imgui", native_imgui)
    view = view_with(
        window=window, imgui=imgui, clear=Mock(), net=Mock(),
        viewport_ctrl=Mock(), renderer=Mock(), unit_interactions=Mock(),
        unit_renderer=Mock(), event_renderer=Mock(), battle_effect_renderer=Mock(),
        layout=Mock(), unit_context_menu=Mock(), unit_order_targeting_prompt=Mock(),
        unit_details_window=Mock(), nav=Mock(), _active_selection_rect=Mock(return_value=None),
        _render_map_information=Mock(), _visible_unit_owners=Mock(),
    )
    view.net.get_state.return_value = None
    view.net.get_display_total_minutes.return_value = 0
    view.viewport_ctrl.show_all_units = False
    view.viewport_ctrl.show_engagement_zones = False
    view.layout.render.side_effect = RuntimeError("widget failed")

    GameView.on_draw(view)

    view._visible_unit_owners.assert_not_called()
    view.unit_renderer.render.assert_called_once()
    view.unit_context_menu.render.assert_not_called()
    assert "UI Rendering Error: widget failed" in capsys.readouterr().out
    imgui.render.assert_called_once_with()


def test_visible_owner_cache_uses_country_and_diplomacy_revisions():
    from src.client.utils import diplomacy_utils

    view = view_with(_visible_owners_cache_key=None, _visible_owners_cache=None)
    state = SimpleNamespace(table_revisions={"countries_treaties": 1, "countries_wars": 2})
    with pytest.MonkeyPatch.context() as monkeypatch:
        allies = Mock(return_value={"POL"})
        enemies = Mock(return_value={"RUS"})
        monkeypatch.setattr(diplomacy_utils, "get_military_allies", allies)
        monkeypatch.setattr(diplomacy_utils, "get_military_enemies", enemies)

        first = GameView._visible_unit_owners(view, state, "UKR")
        second = GameView._visible_unit_owners(view, state, "UKR")
        state.table_revisions["countries_wars"] = 3
        third = GameView._visible_unit_owners(view, state, "UKR")

    assert first == second == third == {"UKR", "POL", "RUS"}
    assert allies.call_count == 2
    assert enemies.call_count == 2


def test_context_ordering_requires_owned_selected_unit_and_resets_gestures():
    view = view_with(
        unit_interactions=Mock(), _selection_rect_start=(1, 2), _selection_rect_current=(3, 4),
        _drag_start_pos=(5, 6), _right_drag_start_pos=(7, 8), _right_context_unit_id="enemy",
    )
    view.unit_interactions.focus_context_unit.return_value = True
    view.unit_interactions.selected_unit_ids = {"own", "enemy", "missing"}
    view.unit_interactions.get_unit_by_id.side_effect = lambda unit_id: {
        "own": SimpleNamespace(owner="ukr"),
        "enemy": SimpleNamespace(owner="pol"),
    }.get(unit_id)
    view.unit_interactions.selected_unit_id = "enemy"

    GameView._begin_context_move_targeting(view, "own")

    assert view.unit_interactions.selected_unit_ids == {"own"}
    assert view.unit_interactions.selected_unit_id == "own"
    view.unit_interactions.begin_move_order_targeting.assert_called_once_with()
    assert view._drag_start_pos is None
    assert view._selection_rect_start is None
    assert view._selection_rect_current is None
    assert view._right_drag_start_pos is None
    assert view._right_context_unit_id is None


def test_context_attack_only_starts_for_owned_focused_units():
    view = view_with(unit_interactions=Mock())
    view.unit_interactions.focus_context_unit.return_value = True
    view.unit_interactions.selected_unit_ids = {"enemy"}
    view.unit_interactions.get_unit_by_id.return_value = SimpleNamespace(owner="POL")

    GameView._begin_context_attack_targeting(view, "enemy")

    view.unit_interactions.begin_attack_move_targeting.assert_not_called()
    view.unit_interactions.focus_context_unit.return_value = False
    assert GameView._prepare_owned_context_selection(view, "enemy") is False

    view.unit_interactions.focus_context_unit.return_value = True
    view.unit_interactions.selected_unit_ids = {"own"}
    view.unit_interactions.get_unit_by_id.return_value = SimpleNamespace(owner="ukr")
    GameView._begin_context_attack_targeting(view, "own")
    view.unit_interactions.begin_attack_move_targeting.assert_called_once_with()


def test_right_click_context_attacks_shows_unit_menu_or_opens_region_menu():
    interactions = Mock()
    interactions.selected_unit_ids = {"own"}
    interactions.get_unit_by_id.return_value = SimpleNamespace(owner="UKR")
    view = view_with(
        unit_interactions=interactions, unit_context_menu=Mock(), layout=Mock(),
        viewport_ctrl=Mock(), _right_context_unit_id="enemy",
    )

    interactions.attack_selected_units.return_value = True
    GameView._open_right_click_context(view, 10, 20)
    interactions.attack_selected_units.assert_called_once_with("enemy")
    view.unit_context_menu.show.assert_not_called()

    interactions.attack_selected_units.return_value = False
    view._right_context_unit_id = "own"
    GameView._open_right_click_context(view, 30, 40)
    interactions.focus_context_unit.assert_called_once_with("own")
    view.unit_context_menu.show.assert_called_once_with("own", orders_enabled=True)

    view._right_context_unit_id = None
    view.viewport_ctrl.get_region_at.return_value = 9
    GameView._open_right_click_context(view, 50, 60)
    view.layout.show_context_menu.assert_called_once_with(9)


def test_context_move_uses_last_right_click_position_when_available():
    view = view_with(unit_interactions=Mock(), _context_click_pos=None)
    GameView._move_selected_units_from_context(view)
    view.unit_interactions.move_selected_units_to_screen_pos.assert_not_called()

    view._context_click_pos = (100, 200)
    GameView._move_selected_units_from_context(view)
    view.unit_interactions.move_selected_units_to_screen_pos.assert_called_once_with(100, 200)


def test_selection_rect_and_click_thresholds_handle_empty_small_and_boundary_cases():
    view = view_with()
    assert GameView._active_selection_rect(view) is None
    assert GameView._is_small_drag(view, None, 0, 0) is False
    view._selection_rect_start = (10, 10)
    view._selection_rect_current = (12, 13)
    assert GameView._active_selection_rect(view) is None
    assert GameView._is_small_drag(view, (10, 10), 12, 13) is True
    view._selection_rect_current = (16, 10)
    assert GameView._active_selection_rect(view) == (10, 10, 16, 10)
    assert GameView._is_small_drag(view, (10, 10), 15, 10) is False


def test_mouse_press_handles_pending_targeting_selection_and_right_click_gestures():
    interactions = Mock()
    imgui = SimpleNamespace(io=SimpleNamespace(want_capture_mouse=False))
    view = view_with(unit_interactions=interactions, imgui=imgui)

    interactions.pending_order_mode = "move"
    imgui.io.want_capture_mouse = True
    GameView.on_game_mouse_press(view, 1, 2, arcade.MOUSE_BUTTON_LEFT, 0)
    interactions.resolve_order_target_click.assert_not_called()

    imgui.io.want_capture_mouse = False
    view._right_drag_start_pos = (4, 5)
    GameView.on_game_mouse_press(view, 1, 2, arcade.MOUSE_BUTTON_LEFT, 0)
    interactions.resolve_order_target_click.assert_called_once_with(1, 2)
    assert view._right_drag_start_pos is None

    interactions.pending_order_mode = None
    interactions.on_mouse_press.return_value = True
    view._selection_rect_start = (9, 9)
    GameView.on_game_mouse_press(view, 3, 4, arcade.MOUSE_BUTTON_LEFT, 0)
    assert view._drag_start_pos is None
    assert view._selection_rect_start is None

    interactions.on_mouse_press.return_value = False
    GameView.on_game_mouse_press(view, 5, 6, arcade.MOUSE_BUTTON_LEFT, 0)
    assert view._drag_start_pos == (5, 6)
    assert view._selection_rect_start == (5, 6)
    assert view._selection_rect_current == (5, 6)

    interactions.cancel_order_targeting.return_value = True
    GameView.on_game_mouse_press(view, 7, 8, arcade.MOUSE_BUTTON_RIGHT, 0)
    assert view._right_drag_start_pos is None
    interactions.cancel_order_targeting.return_value = False
    imgui.io.want_capture_mouse = True
    GameView.on_game_mouse_press(view, 7, 8, arcade.MOUSE_BUTTON_RIGHT, 0)
    assert view._right_drag_start_pos is None
    imgui.io.want_capture_mouse = False
    interactions.get_unit_at.return_value = SimpleNamespace(unit_id="target")
    GameView.on_game_mouse_press(view, 7, 8, arcade.MOUSE_BUTTON_RIGHT, 0)
    assert view._right_drag_start_pos == (7, 8)
    assert view._right_context_unit_id == "target"


def test_mouse_release_routes_right_clicks_and_clears_drag_selection_state():
    interactions = Mock()
    layout = Mock()
    viewport = Mock()
    view = view_with(
        unit_interactions=interactions, layout=layout, viewport_ctrl=viewport,
        battle_effect_renderer=Mock(), window=SimpleNamespace(height=720),
        _drag_start_pos=(10, 20), _selection_rect_start=(10, 20), _selection_rect_current=(30, 40),
        _right_drag_start_pos=(5, 5), _right_context_unit_id="unit",
    )
    interactions.on_mouse_release.return_value = True
    GameView.on_game_mouse_release(view, 1, 2, arcade.MOUSE_BUTTON_LEFT, 0)
    assert view._drag_start_pos is None
    assert view._selection_rect_start is None
    assert view._selection_rect_current is None

    interactions.on_mouse_release.return_value = False
    view._right_drag_start_pos = (5, 5)
    view._open_right_click_context = Mock()
    GameView.on_game_mouse_release(view, 6, 6, arcade.MOUSE_BUTTON_RIGHT, 0)
    view._open_right_click_context.assert_called_once_with(6, 6)
    assert view._right_drag_start_pos is None
    assert view._right_context_unit_id is None

    view._drag_start_pos = (10, 20)
    view._is_small_drag = Mock(return_value=True)
    layout.select_battle_at.return_value = False
    GameView.on_game_mouse_release(view, 11, 21, arcade.MOUSE_BUTTON_LEFT, 0)
    interactions.clear_selection.assert_called_once_with()
    viewport.on_mouse_press.assert_called_once_with(10, 20, arcade.MOUSE_BUTTON_LEFT)
    assert view._drag_start_pos is None

    interactions.clear_selection.reset_mock()
    view._drag_start_pos = (10, 20)
    view._is_small_drag.return_value = False
    GameView.on_game_mouse_release(view, 30, 40, arcade.MOUSE_BUTTON_LEFT, 1)
    interactions.select_units_in_rect.assert_called_once_with(10, 20, 30, 40, 1)
    interactions.clear_selection.assert_not_called()


def test_mouse_drag_motion_scroll_key_and_resize_delegate_to_their_services():
    interactions = Mock()
    viewport = Mock()
    world_camera = Mock()
    view = view_with(unit_interactions=interactions, viewport_ctrl=viewport, world_cam=world_camera)

    interactions.on_mouse_drag.return_value = True
    GameView.on_game_mouse_drag(view, 1, 2, 3, 4, arcade.MOUSE_BUTTON_LEFT, 0)
    viewport.on_mouse_drag.assert_not_called()
    interactions.on_mouse_drag.return_value = False
    view._selection_rect_start = (0, 0)
    GameView.on_game_mouse_drag(view, 8, 9, 8, 9, arcade.MOUSE_BUTTON_LEFT, 0)
    assert view._selection_rect_current == (8, 9)
    view._selection_rect_start = None
    GameView.on_game_mouse_drag(view, 8, 9, 8, 9, arcade.MOUSE_BUTTON_RIGHT, 0)
    viewport.on_mouse_drag.assert_not_called()
    GameView.on_game_mouse_drag(view, 8, 9, 8, 9, arcade.MOUSE_BUTTON_MIDDLE, 0)
    viewport.on_mouse_drag.assert_called_once_with(8, 9, 8, 9, arcade.MOUSE_BUTTON_MIDDLE)

    GameView.on_game_mouse_motion(view, 10, 11, 1, 2)
    GameView.on_game_mouse_scroll(view, 10, 11, 0, 1)
    GameView.on_game_key_press(view, arcade.key.ESCAPE, 0)
    GameView.on_game_key_press(view, arcade.key.ENTER, 0)
    GameView.on_game_resize(view, 1280, 720)
    interactions.on_mouse_motion.assert_called_once_with(10, 11)
    interactions.cancel_order_targeting.assert_called_once_with()
    viewport.on_mouse_scroll.assert_called_once_with(10, 11, 0, 1)
    world_camera.match_window.assert_called_once_with()
