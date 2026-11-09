from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

from src.client.ui.layouts import game_layout as game_layout_module
from src.client.ui.layouts.game_layout import GameLayout


def _layout(**attributes) -> GameLayout:
    layout = GameLayout.__new__(GameLayout)
    for name, value in attributes.items():
        setattr(layout, name, value)
    return layout


def test_dispatch_pending_navigation_consumes_stop_requests_and_uses_navigation_fallback() -> None:
    layout = _layout(_stop_game_requested=False, _navigation=None)
    assert layout.dispatch_pending_navigation() is False

    layout._stop_game_requested = True
    assert layout.dispatch_pending_navigation() is False
    assert layout._stop_game_requested is False

    navigation = SimpleNamespace(stop_game=Mock())
    layout._navigation = navigation
    layout._stop_game_requested = True
    assert layout.dispatch_pending_navigation() is True
    navigation.stop_game.assert_called_once_with()

    explicit_navigation = SimpleNamespace(stop_game=Mock())
    layout._stop_game_requested = True
    assert layout.dispatch_pending_navigation(explicit_navigation) is True
    explicit_navigation.stop_game.assert_called_once_with()


def test_menu_tutorial_context_and_focus_callbacks_delegate_to_their_services() -> None:
    panel_manager = SimpleNamespace(set_visible=Mock())
    tutorial = SimpleNamespace(open=Mock())
    context_menu = SimpleNamespace(show=Mock())
    viewport = SimpleNamespace(focus_on_region=Mock(), focus_on_country=Mock())
    layout = _layout(
        _game_menu_visible=False,
        _stop_game_requested=False,
        panel_manager=panel_manager,
        tutorial_window=tutorial,
        context_menu=context_menu,
        viewport_ctrl=viewport,
    )

    layout._toggle_game_menu()
    assert layout._game_menu_visible is True
    layout._close_game_menu()
    assert layout._game_menu_visible is False
    layout._request_stop_game()
    assert layout._stop_game_requested is True
    assert layout._game_menu_visible is False
    layout._open_tutorial("battle-basics")
    panel_manager.set_visible.assert_called_once_with("TOOLTIP_HELP", False)
    tutorial.open.assert_called_once_with("battle-basics")
    layout.show_context_menu(7)
    layout._on_focus_region(7)
    layout._on_focus_country("CAN")
    context_menu.show.assert_called_once_with(7)
    viewport.focus_on_region.assert_called_once_with(7)
    viewport.focus_on_country.assert_called_once_with("CAN")


def test_dispatch_opens_each_supported_report_and_panel(monkeypatch) -> None:
    state = object()
    net = SimpleNamespace(get_state=Mock(return_value=state))
    battle_summary = SimpleNamespace(show=Mock())
    covert_outcome = SimpleNamespace(show=Mock())
    dispatch_report = SimpleNamespace(enqueue=Mock())
    covert_panel = SimpleNamespace(request_cell=Mock())
    treaty_panel = SimpleNamespace(request_treaty=Mock())
    trade_panel = SimpleNamespace(request_deal=Mock())
    entries = [
        SimpleNamespace(id="COVERT_OPS", instance=covert_panel),
        SimpleNamespace(id="TREATIES", instance=treaty_panel),
        SimpleNamespace(id="TRADE", instance=trade_panel),
    ]
    panel_manager = SimpleNamespace(get_entries=Mock(return_value=entries), set_visible=Mock())
    layout = _layout(
        local_player_tag="USA",
        _cached_target_tag="CAN",
        net=net,
        battle_summary_dialog=battle_summary,
        covert_outcome_dialog=covert_outcome,
        dispatch_report_dialog=dispatch_report,
        panel_manager=panel_manager,
    )
    losses = [{"country": "CAN", "losses": 2}]
    monkeypatch.setattr(
        game_layout_module,
        "MilitaryPresenter",
        lambda: SimpleNamespace(battle_loss_summary=Mock(return_value=losses)),
    )
    monkeypatch.setattr(game_layout_module, "treaty_refusal_report", lambda _state, payload: f"refusal:{payload['id']}")

    layout._open_dispatch({"kind": "battle", "payload": {"battle_id": "battle-1"}})
    battle_summary.show.assert_called_once_with({"battle_id": "battle-1"}, losses=losses)
    layout._open_dispatch({"kind": "covert", "reference": "mission-1"})
    covert_outcome.show.assert_called_once_with("mission-1", "USA")
    layout._open_dispatch({"kind": "covert_ready", "reference": "cell-1", "payload": {"mission_id": "mission-2"}})
    covert_panel.request_cell.assert_called_once_with("cell-1", "mission-2")
    layout._open_dispatch({"kind": "treaty_refusal", "payload": {"id": "refusal-1"}})
    dispatch_report.enqueue.assert_called_once_with("refusal:refusal-1")
    layout._open_dispatch({"kind": "region_control", "body": "Border changed."})
    dispatch_report.enqueue.assert_called_with("Border changed.")
    layout._open_dispatch({"kind": "treaty", "reference": "treaty-1"})
    treaty_panel.request_treaty.assert_called_once_with("treaty-1")
    layout._open_dispatch({"kind": "trade", "reference": "deal-1"})
    trade_panel.request_deal.assert_called_once_with("deal-1")
    assert all(entry.instance for entry in entries)
    panel_manager.set_visible.assert_any_call("COVERT_OPS", True)
    panel_manager.set_visible.assert_any_call("TREATIES", True)
    panel_manager.set_visible.assert_any_call("TRADE", True)
    assert layout._cached_target_tag == "USA"


def test_dispatch_without_matching_panel_is_a_noop() -> None:
    panel_manager = SimpleNamespace(get_entries=Mock(return_value=[]), set_visible=Mock())
    layout = _layout(local_player_tag="USA", _cached_target_tag="CAN", panel_manager=panel_manager)

    layout._open_dispatch({"kind": "covert_ready", "reference": "cell", "payload": {}})
    layout._open_dispatch({"kind": "treaty", "reference": "treaty"})
    layout._open_dispatch({"kind": "trade", "reference": "deal"})

    panel_manager.set_visible.assert_not_called()


def test_save_load_and_battle_selection_paths(monkeypatch) -> None:
    window = SimpleNamespace(game_config=object())
    navigation = SimpleNamespace(load_saved_game=Mock())
    dialog = SimpleNamespace(enqueue=Mock())
    layout = _layout(
        _window=window,
        _navigation=navigation,
        message_dialog=dialog,
        net=SimpleNamespace(player_id="player-1", get_state=Mock(return_value="state")),
        battle_inspection=SimpleNamespace(open=Mock(return_value=True)),
    )
    monkeypatch.setattr(game_layout_module, "list_available_saves", Mock(return_value=["save-a"]))

    assert layout._list_saves() == ["save-a"]
    layout._load_save("save-a")
    navigation.load_saved_game.assert_called_once_with(window.game_config, "save-a")
    assert layout.select_battle_at(SimpleNamespace(battle_at=Mock(return_value="battle-1")), 1, 2, 600) is True
    layout.battle_inspection.open.assert_called_once_with("state", "battle-1")

    layout._window = None
    assert layout._list_saves() == []
    layout._navigation = None
    layout._load_save("save-b")
    dialog.enqueue.assert_called_once_with("Load game", "No active game configuration.", severity="error")
    layout.battle_inspection.open.return_value = False
    assert layout.select_battle_at(SimpleNamespace(battle_at=Mock(return_value=None)), 0, 0, 600) is False
    assert layout.select_battle_at(SimpleNamespace(battle_at=Mock(return_value="battle-2")), 0, 0, 600) is False


def test_quick_treaty_and_game_menu_rendering_paths(monkeypatch) -> None:
    treaty = SimpleNamespace(prepare=Mock())
    panel_manager = SimpleNamespace(
        get_entries=Mock(return_value=[SimpleNamespace(id="NEW_TREATY", instance=treaty)]),
        set_visible=Mock(),
    )
    game_menu = SimpleNamespace(render=Mock())
    layout = _layout(
        local_player_tag="USA",
        panel_manager=panel_manager,
        game_menu=game_menu,
        _game_menu_visible=False,
    )
    imgui = SimpleNamespace(get_main_viewport=lambda: SimpleNamespace(size=SimpleNamespace(x=1280, y=720)))
    monkeypatch.setattr(game_layout_module, "imgui", imgui)

    layout._open_quick_treaty("CAN", "alliance", invert_sides=True)
    treaty.prepare.assert_called_once_with("USA", "CAN", "alliance", invert_sides=True)
    panel_manager.set_visible.assert_called_once_with("NEW_TREATY", True)
    layout._render_game_menu()
    game_menu.render.assert_not_called()
    layout._game_menu_visible = True
    layout._render_game_menu()
    game_menu.render.assert_called_once_with(1280.0, 720.0)

    panel_manager.get_entries.return_value = []
    layout._open_quick_treaty("CAN", "defense")
    assert treaty.prepare.call_count == 1


def _imgui_stub(button_result=None, begin_result=True):
    from unittest.mock import Mock

    return SimpleNamespace(
        WindowFlags_=SimpleNamespace(
            no_decoration=1,
            no_inputs=2,
            no_background=4,
            always_auto_resize=8,
            no_collapse=16,
        ),
        Col_=SimpleNamespace(window_bg=1, title_bg=2, title_bg_active=3),
        get_io=lambda: SimpleNamespace(display_size=SimpleNamespace(x=1280, y=720)),
        get_main_viewport=lambda: SimpleNamespace(size=SimpleNamespace(x=1280, y=720)),
        set_next_window_pos=Mock(),
        set_next_window_size=Mock(),
        set_next_window_focus=Mock(),
        push_style_color=Mock(),
        pop_style_color=Mock(),
        begin=Mock(return_value=begin_result),
        end=Mock(),
        text_colored=Mock(),
        text_wrapped=Mock(),
        separator=Mock(),
        same_line=Mock(),
        button=Mock(side_effect=button_result or (lambda *_args, **_kwargs: False)),
    )


def test_fps_and_error_banner_report_details_and_clear_errors(monkeypatch) -> None:
    imgui = _imgui_stub(button_result=lambda label, **_kwargs: label == "Details")
    monkeypatch.setattr(game_layout_module, "imgui", imgui)
    message_dialog = SimpleNamespace(enqueue=Mock())
    net = SimpleNamespace(clear_system_errors=Mock())
    layout = _layout(message_dialog=message_dialog, net=net)

    layout._render_fps(59.7)
    imgui.text_colored.assert_called_once_with((1, 1, 1, 1), "60")
    errors = [{"system_id": f"system-{index}", "message": f"failure-{index}"} for index in range(10)]
    layout._render_system_errors_banner(errors)
    details = "\n\n".join(f"[{error['system_id']}] {error['message']}" for error in errors[-8:])
    message_dialog.enqueue.assert_called_once_with("Simulation errors", details, severity="error")
    imgui.set_next_window_focus.assert_called_once_with()
    assert imgui.pop_style_color.call_args.args == (3,)

    imgui.button.side_effect = lambda label, **_kwargs: label == "Clear errors"
    layout._render_system_errors_banner(errors[:1])
    net.clear_system_errors.assert_called_once_with()

    hidden_imgui = _imgui_stub(begin_result=False)
    monkeypatch.setattr(game_layout_module, "imgui", hidden_imgui)
    layout._render_system_errors_banner(errors[:1])
    hidden_imgui.end.assert_called_once_with()
    hidden_imgui.pop_style_color.assert_called_once_with(3)


def test_window_close_is_scheduled_after_frame_presentation(monkeypatch) -> None:
    callbacks = []
    close = Mock()
    monkeypatch.setattr(game_layout_module.arcade, "schedule_once", lambda callback, delay: callbacks.append((callback, delay)))
    layout = _layout(_window=None)

    layout._request_window_close()
    assert callbacks == []
    layout._window = SimpleNamespace(close=close)
    layout._request_window_close()

    assert callbacks[0][1] == 1 / 60
    callbacks[0][0](0.0)
    close.assert_called_once_with()


def test_active_context_falls_back_to_player_and_caches_until_selection_changes() -> None:
    layout = _layout(local_player_tag="USA", _last_selected_id=None, _cached_target_tag="USA")
    state = SimpleNamespace(tables={"regions": pl.DataFrame({
        "id": [1, 2, 3],
        "owner": ["USA", "CAN", "CAN"],
        "controller": ["CAN", None, "None"],
    })})

    assert layout._resolve_active_context(state, 1) == ("CAN", False)
    state.tables["regions"] = state.tables["regions"].with_columns(
        pl.when(pl.col("id") == 1).then(pl.lit("USA")).otherwise(pl.col("controller")).alias("controller"),
    )
    assert layout._resolve_active_context(state, 1) == ("CAN", False)
    assert layout._resolve_active_context(state, 2) == ("CAN", False)
    assert layout._resolve_active_context(state, 3) == ("USA", True)
    assert layout._resolve_active_context(state, 99) == ("USA", True)
    assert layout._resolve_active_context(state, None) == ("USA", True)

    layout._cached_target_tag = "CAN"
    assert layout._resolve_active_context(SimpleNamespace(tables={}), 7) == ("CAN", False)
    assert layout._resolve_active_context(SimpleNamespace(tables={"regions": object()}), 8) == ("USA", True)


def test_game_layout_constructor_registers_each_panel_spec(monkeypatch) -> None:
    class FakePanelManager:
        def __init__(self):
            self.register_spec = Mock()
            self.toggle = Mock()
            self.set_visible = Mock()
            self.is_visible = Mock()
            self.get_entries = Mock(return_value=[])

    state = SimpleNamespace(journal=SimpleNamespace(command_results=[]), tables={})
    net = SimpleNamespace(get_state=Mock(return_value=state), player_id="player-1", send_action=Mock())
    spec = object()
    monkeypatch.setattr(game_layout_module, "PanelManager", FakePanelManager)
    monkeypatch.setattr(game_layout_module, "build_in_game_menu_actions", Mock(return_value=[]))
    monkeypatch.setattr(game_layout_module, "build_game_panel_specs", Mock(return_value=[spec]))
    monkeypatch.setattr(game_layout_module, "UIComposer", Mock())
    monkeypatch.setattr(game_layout_module, "CentralBar", Mock(return_value=SimpleNamespace(flag_renderer=object())))
    constructors = (
        "AutosaveScheduler", "SaveConfirmationPreferences", "GenericMessageDialog", "GenericQuestionDialog",
        "AdvisorRecommendationWindow", "CommandFeedback", "UnitOrderFeedback", "BattleSummaryDialog",
        "GameOverDialog", "CovertOutcomeDialog", "TextNotificationDialog", "BattleInspectionWindows",
        "UnitReorganizationWindows", "UnitMoveOrders", "UnitAttackConfirmation", "SaveGameDialog",
        "MainMenuContent", "GameSettingsContent", "GuidedTutorialWindow", "ToggleBar", "MiniMapPanel",
        "SystemBar", "ContextMenu", "ThematicMapLegend", "FeedPresenter", "MailInboxState",
    )
    for name in constructors:
        monkeypatch.setattr(game_layout_module, name, Mock())

    layout = GameLayout(net, "USA", object())

    layout.panel_manager.register_spec.assert_called_once_with(spec)


def test_render_loads_state_and_routes_system_errors_to_the_banner(monkeypatch) -> None:
    state = SimpleNamespace(tables={}, journal=SimpleNamespace(command_results=[]))
    errors = [{"system_id": "simulation", "message": "system failed"}]
    net = SimpleNamespace(
        get_state=Mock(return_value=state),
        get_system_errors=Mock(return_value=errors),
        player_id="player-1",
    )
    renderable_names = (
        "system_bar", "toggle_bar", "mini_map", "tutorial_window", "context_menu",
        "thematic_map_legend", "save_game_dialog", "battle_summary_dialog", "unit_reorganization",
        "covert_outcome_dialog", "dispatch_report_dialog", "battle_inspection", "unit_attack_confirmation",
        "message_dialog", "advisor_question_dialog", "advisor_recommendation_window",
    )
    layout = _layout(
        net=net,
        local_player_tag="USA",
        viewport_ctrl=SimpleNamespace(focus_on_country=Mock(return_value=None)),
        _on_deployment_drag_start=None,
        save_confirmation_preferences=object(),
        autosave=SimpleNamespace(update=Mock(return_value=[])),
        game_over_dialog=SimpleNamespace(is_game_over=Mock(return_value=False), render=Mock()),
        command_feedback=SimpleNamespace(update=Mock()),
        unit_order_feedback=SimpleNamespace(update=Mock()),
        feed_presenter=SimpleNamespace(build_summary=Mock(return_value="summary")),
        central_bar=SimpleNamespace(render=Mock(return_value=None)),
        panel_manager=SimpleNamespace(
            render_all=Mock(), is_visible=Mock(),
        ),
        _resolve_active_context=Mock(return_value=("USA", True)),
        _render_system_errors_banner=Mock(),
        _render_fps=Mock(),
        _render_game_menu=Mock(),
    )
    for name in renderable_names:
        setattr(layout, name, SimpleNamespace(render=Mock(), enqueue=Mock(), show=Mock(), open=Mock()))
    layout.message_dialog.enqueue = Mock()
    layout.advisor_question_dialog.show = Mock()
    layout.advisor_recommendation_window.open = Mock()
    layout.panel_manager.render_all = Mock()
    monkeypatch.setattr(game_layout_module, "GAMETHEME", SimpleNamespace(apply=Mock()))
    monkeypatch.setattr(game_layout_module, "WindowManager", SimpleNamespace(begin_frame=Mock()))
    monkeypatch.setattr(game_layout_module, "resolve_country_status", Mock(return_value="status"))
    monkeypatch.setattr(game_layout_module, "consume_panel_shortcuts", Mock())

    layout.render(selected_region_id=None, fps=60.0, nav_service=object())

    net.get_state.assert_called_once_with()
    layout._render_system_errors_banner.assert_called_once_with(errors)
    layout.panel_manager.render_all.assert_called_once()
    layout.game_over_dialog.render.assert_called_once()
