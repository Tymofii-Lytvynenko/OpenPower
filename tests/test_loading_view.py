from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.client.views.loading_view import LoadingView


def _make_view(task: object, on_success: Mock, on_failure: Mock | None = None) -> LoadingView:
    fake_window = SimpleNamespace(
        background_color=None,
        imgui=SimpleNamespace(update_time=Mock()),
        show_view=Mock(),
    )
    with patch("arcade.get_window", return_value=fake_window):
        view = LoadingView(task, on_success, on_failure)
    view._active = True
    return view


def test_loading_failure_is_reported_once_across_updates() -> None:
    task = SimpleNamespace(progress=0.5, status_text="Loading")
    on_failure = Mock()
    view = _make_view(task, Mock(), on_failure)
    view.is_finished = True
    view.error = RuntimeError("load failed")

    view.on_update(1 / 60)
    view.on_update(1 / 60)

    on_failure.assert_called_once_with(view.error)


def test_loading_failure_without_callback_keeps_client_alive() -> None:
    view = _make_view(SimpleNamespace(progress=0.5, status_text="Loading"), Mock())
    view.is_finished = True
    view.error = RuntimeError("load failed")
    view.on_update(1 / 60)
    view.on_update(1 / 60)
    assert view.error is not None
    view.window.show_view.assert_not_called()


def test_loading_success_transitions_once_after_final_progress_frame() -> None:
    task = SimpleNamespace(progress=0.7, status_text="Loading")
    next_view = object()
    on_success = Mock(return_value=next_view)
    view = _make_view(task, on_success)
    view.is_finished = True
    view.result = "ready"

    view.on_update(1 / 60)
    assert task.progress == 1.0
    assert task.status_text == "Finalizing Graphics..."
    view.on_update(1 / 60)
    view.on_update(1 / 60)

    on_success.assert_called_once_with("ready")
    view.window.show_view.assert_called_once_with(next_view)


def test_loading_worker_is_started_only_once_when_view_is_shown_again() -> None:
    task = SimpleNamespace(progress=0.0, status_text="Loading")
    view = _make_view(task, Mock())
    with patch.object(view.thread, "start") as start_thread:
        view.on_show_view()
        view.on_show_view()

    start_thread.assert_called_once_with()


def test_hiding_loading_view_cancels_task_and_suppresses_late_success() -> None:
    task = SimpleNamespace(progress=0.0, status_text="Loading", cancel=Mock())
    on_success = Mock(return_value=object())
    view = _make_view(task, on_success)

    view.on_hide_view()
    view.result = "late result"
    view.is_finished = True
    view.on_update(1 / 60)
    view.on_update(1 / 60)

    task.cancel.assert_called_once_with()
    on_success.assert_not_called()
    view.window.show_view.assert_not_called()


def test_showing_view_marks_it_active_before_starting_worker() -> None:
    task = SimpleNamespace(progress=0.0, status_text="Loading")
    view = _make_view(task, Mock())
    view._active = False

    with patch.object(view.thread, "start"):
        view.on_show_view()

    assert view._active is True


def test_hiding_finished_view_cancels_unclaimed_result_before_transition() -> None:
    task = SimpleNamespace(progress=1.0, status_text="Ready", cancel=Mock())
    on_success = Mock(return_value=object())
    view = _make_view(task, on_success)
    view.is_finished = True
    view.result = "created session"

    view.on_hide_view()
    view.on_update(1 / 60)

    task.cancel.assert_called_once_with()
    on_success.assert_not_called()


def test_worker_stores_the_task_result_and_marks_completion() -> None:
    task = SimpleNamespace(run=Mock(return_value="ready"), progress=0.0, status_text="Loading")
    view = _make_view(task, Mock())

    view._worker()

    assert view.result == "ready"
    assert view.error is None
    assert view.is_finished is True


def test_worker_captures_task_errors_and_marks_completion() -> None:
    error = RuntimeError("load failed")
    task = SimpleNamespace(run=Mock(side_effect=error), progress=0.0, status_text="Loading")
    view = _make_view(task, Mock())

    view._worker()

    assert view.result is None
    assert view.error is error
    assert view.is_finished is True


def test_resize_forwards_window_dimensions_to_imgui() -> None:
    view = _make_view(SimpleNamespace(progress=0.0, status_text="Loading"), Mock())
    view.window.imgui.resize = Mock()

    view.on_resize(1280, 720)

    view.window.imgui.resize.assert_called_once_with(1280, 720)


def _make_drawable_view() -> LoadingView:
    view = _make_view(SimpleNamespace(progress=0.5, status_text="Loading"), Mock())
    view.window.get_size = Mock(return_value=(800, 600))
    view.window.use = Mock()
    view.window.setup = Mock()
    view.window.imgui.new_frame = Mock()
    view.window.imgui.render = Mock()
    view.ui.setup_frame = Mock()
    view.status_panel.render = Mock()
    view.clear = Mock()
    return view


def test_draw_renders_loading_ui_when_no_shared_renderer_is_available() -> None:
    view = _make_drawable_view()

    view.on_draw()

    view.clear.assert_called_once_with()
    view.window.use.assert_called_once_with()
    view.window.imgui.new_frame.assert_called_once_with()
    view.ui.setup_frame.assert_called_once_with()
    view.status_panel.render.assert_called_once_with(
        view.ui,
        view.task,
        view.error,
        (800, 600),
        on_return=view.window.setup,
    )
    view.window.imgui.render.assert_called_once_with()


def test_draw_resets_graphics_state_before_drawing_shared_globe() -> None:
    view = _make_drawable_view()
    renderer = SimpleNamespace(draw=Mock())
    context = SimpleNamespace(
        scissor=(1, 2, 3, 4),
        viewport=None,
        DEPTH_TEST=1,
        BLEND=2,
        enable_only=Mock(),
    )
    view.window.shared_renderer = renderer
    view.window.ctx = context

    view.on_draw()

    assert context.scissor is None
    assert context.viewport == (0, 0, 800, 600)
    context.enable_only.assert_called_once_with(context.DEPTH_TEST, context.BLEND)
    renderer.draw.assert_called_once_with()
    view.window.use.assert_called_once_with()
