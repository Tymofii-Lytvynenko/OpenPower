from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from src.client.ui.components import main_menu_content as menu_module
from src.client.ui.components.main_menu_content import (
    MainMenuAction,
    MainMenuContent,
    build_in_game_menu_actions,
    build_main_menu_actions,
)


def bare_content(*, actions=()):
    content = MainMenuContent.__new__(MainMenuContent)
    content._composer = Mock()
    content._composer.begin_centered_panel.return_value = True
    content._actions = actions
    content._test_id_prefix = "test_menu"
    content._settings_content = SimpleNamespace(
        render=Mock(),
        begin_session=Mock(),
        apply=Mock(return_value=True),
        discard=Mock(),
    )
    content._in_game = False
    content._show_settings = False
    content._show_credits = False
    content._active_submenu = None
    content._tutorial_guide = SimpleNamespace(
        is_open=False,
        title="Tutorial",
        window_size=Mock(return_value=(420.0, 320.0)),
        render=Mock(),
        open=Mock(),
        close=Mock(),
    )
    content._credits_content = SimpleNamespace(render=Mock())
    content._host_window = SimpleNamespace(is_open=False, render=Mock(), show=Mock())
    content._join_window = SimpleNamespace(is_open=False, render=Mock(), show=Mock())
    return content


def test_action_builders_keep_callbacks_and_unavailable_actions_explicit():
    singleplayer = Mock()
    load_game = Mock()
    exit_game = Mock()
    actions = build_main_menu_actions(singleplayer, load_game, exit_game)
    by_id = {action.test_id: action for action in actions}

    assert by_id["main_menu.singleplayer"].opens_screen == "singleplayer"
    assert by_id["main_menu.scenario"].callback is singleplayer
    assert by_id["main_menu.load_game"].callback is load_game
    assert by_id["main_menu.exit"].callback is exit_game
    assert not by_id["main_menu.custom_game"].enabled
    assert by_id["main_menu.multiplayer.internet"].join_mode == "internet"
    assert by_id["main_menu.multiplayer.lan"].join_mode == "lan"
    assert by_id["main_menu.interface_tutorial"].opens_tutorial == "interface"
    assert by_id["main_menu.military_tutorial"].opens_tutorial == "military"

    resume, quit_game, stop_game = Mock(), Mock(), Mock()
    in_game = {action.test_id: action for action in build_in_game_menu_actions(resume, quit_game)}
    assert in_game["game_menu.resume"].callback is resume
    assert not in_game["game_menu.restart"].enabled
    assert not in_game["game_menu.stop"].enabled
    assert in_game["game_menu.quit"].callback is quit_game
    stoppable = {action.test_id: action for action in build_in_game_menu_actions(resume, None, stop_game)}
    assert stoppable["game_menu.stop"].enabled
    assert stoppable["game_menu.stop"].callback is stop_game


def test_constructor_composes_settings_tutorial_credits_and_multiplayer_windows(monkeypatch):
    settings = object()
    composer = object()
    options_content = object()
    tutorial = object()
    credits = object()
    host = SimpleNamespace(show=Mock())
    join = object()
    monkeypatch.setattr(menu_module, "REFERENCEOptionsWindowContent", Mock(return_value=options_content))
    monkeypatch.setattr(menu_module, "TutorialGuideContent", Mock(return_value=tutorial))
    monkeypatch.setattr(menu_module, "ProjectCreditsContent", Mock(return_value=credits))
    monkeypatch.setattr(menu_module, "HostMultiplayerGameWindow", Mock(return_value=host))
    monkeypatch.setattr(menu_module, "JoinMultiplayerWindow", Mock(return_value=join))
    load_game = Mock()
    actions = (MainMenuAction("Load", "main_menu.load_game", load_game, "btnLoad"),)

    content = MainMenuContent(composer, settings, actions, test_id_prefix="test", in_game=True)

    assert content._composer is composer
    assert content._settings_content is options_content
    assert content._tutorial_guide is tutorial
    assert content._credits_content is credits
    assert content._host_window is host
    assert content._join_window is join
    assert content._in_game
    menu_module.REFERENCEOptionsWindowContent.assert_called_once_with(settings, "test")
    menu_module.JoinMultiplayerWindow.assert_called_once()
    assert menu_module.JoinMultiplayerWindow.call_args.kwargs["on_load_game"] is load_game
    assert menu_module.JoinMultiplayerWindow.call_args.kwargs["on_host_game"] == host.show


@pytest.mark.parametrize(
    ("tutorial", "settings", "credits", "submenu", "expected"),
    [
        (True, True, True, "multiplayer", "tutorial"),
        (False, True, True, "multiplayer", "settings"),
        (False, False, True, "multiplayer", "credits"),
        (False, False, False, "multiplayer", "multiplayer"),
        (False, False, False, None, "main"),
    ],
)
def test_current_page_obeys_overlay_and_submenu_priority(
    tutorial, settings, credits, submenu, expected
):
    content = bare_content()
    content._tutorial_guide.is_open = tutorial
    content._show_settings = settings
    content._show_credits = credits
    content._active_submenu = submenu

    assert content._current_page() == expected


@pytest.mark.parametrize(
    ("page", "in_game", "expected"),
    [
        ("main", False, ("MAIN MENU", "Main_Menu", "test_menu.window", (273.0, 196.0))),
        ("main", True, ("MAIN MENU", "Main_Menu", "test_menu.window", (273.0, 223.0))),
        ("singleplayer", False, ("SINGLEPLAYER", "Submenu_Single", "test_menu.singleplayer.window", None)),
        ("multiplayer", False, ("MULTIPLAYER", "Submenu_Multi", "test_menu.multiplayer.window", (273.0, 139.0))),
        ("settings", False, ("SETTINGS", "Options_Window", "test_menu.window", None)),
        ("credits", False, ("CREDITS", "Credits_Window", "test_menu.window", None)),
        ("tutorial", False, ("Tutorial", "", "test_menu.tutorial.window", (420.0, 320.0))),
    ],
)
def test_page_layout_selects_source_window_and_size(page, in_game, expected):
    content = bare_content()
    content._in_game = in_game

    assert content._page_layout(page) == expected


@pytest.mark.parametrize("template", ["Main_Menu", "Submenu_Multi", "other"])
def test_apply_source_runtime_geometry_matches_disconnected_source_layout(monkeypatch, template):
    layout = SimpleNamespace(resize_component=Mock(), move_component=Mock())
    monkeypatch.setattr(
        "src.client.ui.layouts.gml_layout.active_gml_layout",
        lambda: layout,
    )

    MainMenuContent._apply_source_runtime_geometry(template)

    if template == "Main_Menu":
        assert layout.resize_component.call_args_list == [
            call("Main_Menu/frmInner", height=163.0),
            call("Main_Menu/picShadowGradient", height=189.0),
            call("Main_Menu/picWhiteGradient", height=189.0),
        ]
        assert layout.move_component.call_count == 4
    elif template == "Submenu_Multi":
        assert layout.resize_component.call_count == 3
        assert layout.move_component.call_args_list == [
            call("Submenu_Multi/frmInner/picSep", y=-28.0),
            call("Submenu_Multi/frmInner/btnReturn", y=-28.0),
        ]
    else:
        layout.resize_component.assert_not_called()
        layout.move_component.assert_not_called()


def test_apply_source_runtime_geometry_returns_when_no_layout_is_active(monkeypatch):
    monkeypatch.setattr("src.client.ui.layouts.gml_layout.active_gml_layout", lambda: None)
    MainMenuContent._apply_source_runtime_geometry("Main_Menu")


@pytest.mark.parametrize("kind", ["tutorial", "join", "submenu", "return", "settings", "credits", "callback"])
def test_render_actions_dispatches_the_selected_action_and_ignores_other_screens(kind):
    callback = Mock()
    action_options = {
        "tutorial": {"opens_tutorial": "military"},
        "join": {"join_mode": "lan"},
        "submenu": {"opens_screen": "singleplayer"},
        "return": {"return_to_main": True},
        "settings": {"show_settings": True},
        "credits": {"show_credits": True},
        "callback": {"callback": callback, "spacer_after": 8.0},
    }
    options = dict(action_options[kind])
    callback_argument = options.pop("callback", None)
    selected = MainMenuAction(
        "Selected", "selected", callback_argument, "btnSelected", **options
    )
    other = MainMenuAction("Other", "other", None, "btnOther", screen="multiplayer")
    content = bare_content(actions=(other, selected))
    content._composer.draw_menu_button.side_effect = [True]
    content._show_settings = True
    content._show_credits = True
    content._active_submenu = "multiplayer"

    content._render_actions("main", "Main_Menu")

    content._composer.draw_menu_button.assert_called_once_with(
        "Selected",
        test_id="selected",
        gml_id="Main_Menu/frmInner/btnSelected",
        enabled=True,
        tooltip="",
    )
    if kind == "tutorial":
        content._tutorial_guide.open.assert_called_once_with("military")
        assert not content._show_settings and not content._show_credits
    elif kind == "join":
        content._join_window.show.assert_called_once_with("lan")
    elif kind == "submenu":
        assert content._active_submenu == "singleplayer"
        assert not content._show_settings and not content._show_credits
    elif kind == "return":
        assert content._active_submenu is None
    elif kind == "settings":
        assert content._show_settings
        assert not content._show_credits
        assert content._active_submenu is None
        content._settings_content.begin_session.assert_called_once_with()
    elif kind == "credits":
        assert not content._show_settings
        assert content._show_credits
        assert content._active_submenu is None
    else:
        callback.assert_called_once_with()
        content._composer.dummy.assert_called_once_with((0, 8.0))


def test_render_actions_skips_dispatch_when_button_is_not_clicked_and_still_adds_spacer():
    callback = Mock()
    action = MainMenuAction("Action", "action", callback, "btnAction", spacer_after=3.0)
    content = bare_content(actions=(action,))
    content._composer.draw_menu_button.return_value = False

    content._render_actions("main", "Main_Menu")

    callback.assert_not_called()
    content._composer.dummy.assert_called_once_with((0, 3.0))


def test_render_actions_settings_branch_accepts_missing_begin_session_method():
    content = bare_content(
        actions=(MainMenuAction("Settings", "settings", None, "btn", show_settings=True),)
    )
    content._settings_content = object()
    content._composer.draw_menu_button.return_value = True

    content._render_actions("main", "Main_Menu")

    assert content._show_settings


def test_close_tutorial_delegates_to_guide():
    content = bare_content()
    content._close_tutorial()
    content._tutorial_guide.close.assert_called_once_with()


def install_settings_render_stubs(monkeypatch, *, close_clicked, clicked, available_height=100.0):
    title = SimpleNamespace(button_at=Mock(return_value=close_clicked))
    options = SimpleNamespace(
        button=Mock(side_effect=lambda component, *_args, **_kwargs: component == clicked)
    )
    monkeypatch.setattr(
        menu_module,
        "GMLWidgets",
        lambda root: title if root.endswith("frmTitle") else options,
    )
    monkeypatch.setattr(menu_module, "semantic_region", lambda *_args: nullcontext())
    monkeypatch.setattr(
        menu_module,
        "imgui",
        SimpleNamespace(
            get_content_region_avail=lambda: SimpleNamespace(y=available_height),
            get_cursor_screen_pos=Mock(return_value=(3.0, 4.0)),
            set_cursor_screen_pos=Mock(),
        ),
    )
    return title, options


@pytest.mark.parametrize(
    ("close_clicked", "clicked", "apply_result", "expected_open", "discard_calls", "apply_calls", "height"),
    [
        (True, None, None, False, 1, 0, 100.0),
        (False, "btnConfirm", False, True, 0, 1, 200.0),
        (False, "btnConfirm", None, False, 0, 1, 200.0),
        (False, "btnCancel", None, False, 1, 0, 200.0),
    ],
)
def test_render_settings_handles_close_apply_and_back_actions(
    monkeypatch,
    close_clicked,
    clicked,
    apply_result,
    expected_open,
    discard_calls,
    apply_calls,
    height,
):
    content = bare_content()
    content._show_settings = True
    content._settings_content.apply.return_value = apply_result
    previous_cursor = object()
    monkeypatch.setattr(
        menu_module,
        "imgui",
        SimpleNamespace(
            get_content_region_avail=lambda: SimpleNamespace(y=height),
            get_cursor_screen_pos=Mock(return_value=previous_cursor),
            set_cursor_screen_pos=Mock(),
        ),
    )
    title, options = install_settings_render_stubs(
        monkeypatch,
        close_clicked=close_clicked,
        clicked=clicked,
        available_height=height,
    )

    content._render_settings()

    content._settings_content.render.assert_called_once_with(max_height=max(120.0, height - 34.0))
    assert content._settings_content.discard.call_count == discard_calls
    assert content._settings_content.apply.call_count == apply_calls
    assert content._show_settings is expected_open
    assert options.button.call_count == 2
    assert title.button_at.called


def test_render_settings_apply_closes_when_settings_has_no_apply_method(monkeypatch):
    content = bare_content()
    content._show_settings = True
    content._settings_content = SimpleNamespace(render=Mock())
    install_settings_render_stubs(monkeypatch, close_clicked=False, clicked="btnConfirm")

    content._render_settings()

    assert not content._show_settings


@pytest.mark.parametrize("child_open", [True, False])
@pytest.mark.parametrize("layout_kind", ["none", "missing-component", "component"])
def test_render_credits_draws_content_and_uses_available_close_geometry(
    monkeypatch, child_open, layout_kind
):
    content = bare_content()
    if layout_kind == "component":
        close_component = object()
        close_rect = SimpleNamespace(x=7.0, y=9.0, width=18.0, height=19.0)
        layout = SimpleNamespace(
            component=Mock(return_value=close_component),
        )
        layout_session = SimpleNamespace(layout=layout, rect_for=Mock(return_value=close_rect))
    elif layout_kind == "missing-component":
        layout = SimpleNamespace(component=Mock(return_value=None))
        layout_session = SimpleNamespace(layout=layout, rect_for=Mock())
    else:
        layout_session = None
    monkeypatch.setattr(menu_module, "active_gml_layout", lambda: layout_session)
    monkeypatch.setattr(menu_module, "semantic_region", lambda *_args: nullcontext())
    imgui = SimpleNamespace(
        begin_child=Mock(return_value=child_open),
        end_child=Mock(),
        get_window_pos=Mock(return_value=SimpleNamespace(x=100.0, y=200.0)),
        set_cursor_screen_pos=Mock(),
        button=Mock(return_value=True),
    )
    monkeypatch.setattr(menu_module, "imgui", imgui)

    content._show_credits = True
    content._render_credits()

    assert content._credits_content.render.call_count == int(child_open)
    imgui.end_child.assert_called_once_with()
    assert imgui.button.call_args.args[0] == "×"
    assert content._show_credits is False
    if layout_kind == "component":
        assert imgui.button.call_args.args[1] == (18.0, 19.0)
        imgui.set_cursor_screen_pos.assert_called_once_with((107.0, 209.0))
        layout_session.rect_for.assert_called_once_with(close_component)
    else:
        assert imgui.button.call_args.args[1] == (24.0, 24.0)
        imgui.set_cursor_screen_pos.assert_not_called()


def test_render_routes_host_and_join_windows_before_the_menu_panel():
    content = bare_content()
    content._host_window.is_open = True
    content.render(800.0, 600.0)
    content._host_window.render.assert_called_once_with(800.0, 600.0)
    content._join_window.render.assert_not_called()
    content._composer.begin_centered_panel.assert_not_called()

    content._host_window.is_open = False
    content._join_window.is_open = True
    content.render(800.0, 600.0)
    content._join_window.render.assert_called_once_with(800.0, 600.0)
    content._composer.begin_centered_panel.assert_not_called()


@pytest.mark.parametrize(
    ("page_state", "expected_method"),
    [
        ({}, "_render_actions"),
        ({"settings": True}, "_render_settings"),
        ({"credits": True}, "_render_credits"),
        ({"tutorial": True}, "tutorial"),
    ],
)
def test_render_selects_page_content_and_ends_centered_panel(
    monkeypatch, page_state, expected_method
):
    content = bare_content()
    content._show_settings = page_state.get("settings", False)
    content._show_credits = page_state.get("credits", False)
    content._tutorial_guide.is_open = page_state.get("tutorial", False)
    content._active_submenu = "singleplayer" if not page_state else None
    monkeypatch.setattr(content, "_apply_source_runtime_geometry", Mock())
    render_actions = Mock()
    render_settings = Mock()
    render_credits = Mock()
    monkeypatch.setattr(content, "_render_actions", render_actions)
    monkeypatch.setattr(content, "_render_settings", render_settings)
    monkeypatch.setattr(content, "_render_credits", render_credits)

    content.render(900.0, 700.0)

    content._apply_source_runtime_geometry.assert_called_once()
    content._composer.end_panel.assert_called_once_with()
    if expected_method == "_render_actions":
        render_actions.assert_called_once_with("singleplayer", "Submenu_Single")
    elif expected_method == "_render_settings":
        render_settings.assert_called_once_with()
    elif expected_method == "_render_credits":
        render_credits.assert_called_once_with()
    else:
        content._tutorial_guide.render.assert_called_once_with(content._close_tutorial, window_width=420.0)


def test_render_returns_when_composer_cannot_open_panel_and_skips_source_resize_in_game(monkeypatch):
    content = bare_content()
    content._composer.begin_centered_panel.return_value = False
    resize = Mock()
    monkeypatch.setattr(content, "_apply_source_runtime_geometry", resize)

    content.render(900.0, 700.0)

    resize.assert_not_called()
    content._composer.end_panel.assert_not_called()

    content._composer.begin_centered_panel.return_value = True
    content._in_game = True
    content.render(900.0, 700.0)
    resize.assert_not_called()
    content._composer.end_panel.assert_called_once_with()
