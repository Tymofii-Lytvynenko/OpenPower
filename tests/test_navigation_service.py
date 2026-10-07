from __future__ import annotations

from unittest.mock import Mock, patch

from src.client.services.navigation_service import NavigationService


def test_all_navigation_routes_construct_the_requested_view_once() -> None:
    window = Mock()
    service = NavigationService(window)
    session, config, task = object(), object(), object()
    on_success = Mock()
    on_failure = Mock()

    routes = [
        ("src.client.views.main_menu_view.MainMenuView", "show_main_menu", (session, config)),
        ("src.client.views.loading_view.LoadingView", "show_loading", (task, on_success, on_failure)),
        ("src.client.views.new_game_view.NewGameView", "show_new_game_screen", (session, config)),
        ("src.client.views.load_game_view.LoadGameView", "show_load_game_screen", (config,)),
        ("src.client.views.game_view.GameView", "show_game_view", (session, config, "USA", (1.0, 2.0))),
    ]

    for module, method_name, args in routes:
        window.reset_mock()
        with patch(module) as view_type:
            getattr(service, method_name)(*args)
        view_type.assert_called_once_with(*args)
        window.show_view.assert_called_once_with(view_type.return_value)


def test_editor_route_builds_task_and_loads_editor_view_on_success() -> None:
    window = Mock()
    service = NavigationService(window)
    session, config, context = object(), object(), object()

    with (
        patch("src.client.tasks.editor_loading_task.EditorLoadingTask") as task_type,
        patch("src.client.views.editor_view.EditorView") as editor_view_type,
        patch.object(service, "show_loading") as show_loading,
    ):
        service.show_editor_loading(session, config)

    task_type.assert_called_once_with(session, config)
    show_loading.assert_called_once()
    task = show_loading.call_args.args[0]
    on_success = show_loading.call_args.kwargs["on_success"]
    assert task is task_type.return_value
    assert on_success(context) is editor_view_type.return_value
    editor_view_type.assert_called_once_with(context, config)
