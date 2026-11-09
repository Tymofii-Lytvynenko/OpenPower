import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from src.client.ui.testing import harness as harness_module
from src.client.ui.testing.harness import UITestScenario


class FakeTelemetry:
    def __init__(self, snapshot=None):
        self.viewport_size = None
        self.snapshot = snapshot or {"errors": []}
        self.frames = 0

    @contextmanager
    def frame(self):
        self.frames += 1
        yield

    def to_dict(self):
        return self.snapshot


def make_scenario(
    *,
    render=None,
    baseline=None,
    initialize=None,
    cleanup=None,
    font_path=None,
    snapshot=None,
    viewport=(1024, 768),
):
    telemetry = FakeTelemetry(snapshot)
    scenario = UITestScenario(
        category="coverage",
        name="runner-flow",
        window_title="Coverage Runner",
        viewport_size=viewport,
        telemetry=telemetry,
        render=render or (lambda: None),
        test=lambda _ctx: None,
        collect_checks=lambda passed: [
            {"id": "engine.assertions", "passed": passed, "message": "Engine result"}
        ],
        collect_details=lambda: {"fixture": "unit"},
        baseline=baseline,
        visual_tolerance=0.05,
        visual_masks=({"x": 1},),
        initialize=initialize,
        cleanup=cleanup,
        font_path=font_path,
    )
    return scenario


def install_runner(
    monkeypatch,
    *,
    register=True,
    status="success",
    test_running=False,
    queue_empty=True,
    display_size=(1024, 768),
    monotonic_values=(0.0, 1.0),
    plot_context="plot-context",
    run_error=None,
    call_show_twice=False,
    call_fonts=True,
):
    engine = object()
    test = SimpleNamespace(
        output=SimpleNamespace(
            status=status,
            log=SimpleNamespace(get_text=lambda: "engine log"),
        )
    )
    engine_io = SimpleNamespace()
    test_io = SimpleNamespace(is_running_tests=test_running)
    test_engine_calls = {"get_io": 0}

    def get_test_engine_io(_engine):
        test_engine_calls["get_io"] += 1
        return engine_io if test_engine_calls["get_io"] == 1 else test_io

    test_engine = SimpleNamespace(
        TestRunSpeed=SimpleNamespace(fast="fast"),
        TestStatus=SimpleNamespace(success="success", error="error"),
        register_test=Mock(return_value=test),
        get_io=Mock(side_effect=get_test_engine_io),
        queue_test=Mock(),
        is_test_queue_empty=Mock(return_value=queue_empty),
        get_status_name=Mock(side_effect=lambda value: f"status:{value}"),
    )
    imgui_io = SimpleNamespace(
        display_size=SimpleNamespace(x=display_size[0], y=display_size[1]),
        config_flags=0,
        set_ini_filename=Mock(),
    )
    imgui_stub = SimpleNamespace(
        test_engine=test_engine,
        ConfigFlags_=SimpleNamespace(nav_enable_keyboard=1),
        get_io=Mock(return_value=imgui_io),
    )
    runner_params = SimpleNamespace(
        app_window_params=SimpleNamespace(
            window_geometry=SimpleNamespace(),
        ),
        imgui_window_params=SimpleNamespace(),
        callbacks=SimpleNamespace(),
    )

    def fake_run(params):
        if register:
            params.callbacks.register_tests()
        if call_fonts and hasattr(params.callbacks, "load_additional_fonts"):
            params.callbacks.load_additional_fonts()
        params.callbacks.post_init()
        params.callbacks.show_gui()
        if call_show_twice:
            params.callbacks.show_gui()
        params.callbacks.before_exit()
        if run_error is not None:
            raise run_error

    hello_imgui_stub = SimpleNamespace(
        RunnerParams=lambda: runner_params,
        WindowPositionMode=SimpleNamespace(from_coords="from-coords"),
        WindowSizeMeasureMode=SimpleNamespace(screen_coords="screen-coords"),
        IniFolderType=SimpleNamespace(absolute_path="absolute"),
        DefaultImGuiWindowType=SimpleNamespace(no_default_window="none"),
        get_imgui_test_engine=Mock(return_value=engine),
        get_runner_params=lambda: runner_params,
        change_window_size=Mock(),
        run=fake_run,
    )
    implot_stub = SimpleNamespace(
        create_context=Mock(return_value=plot_context),
        destroy_context=Mock(),
    )

    times = iter(monotonic_values)
    last_time = monotonic_values[-1]

    def monotonic():
        return next(times, last_time)

    monkeypatch.setattr(harness_module, "hello_imgui", hello_imgui_stub)
    monkeypatch.setattr(harness_module, "imgui", imgui_stub)
    monkeypatch.setattr(harness_module, "implot", implot_stub)
    monkeypatch.setattr(harness_module.time, "monotonic", monotonic)
    monkeypatch.setattr(harness_module.importlib.metadata, "version", lambda _name: "test-version")
    return SimpleNamespace(
        hello=hello_imgui_stub,
        imgui=imgui_stub,
        implot=implot_stub,
        runner_params=runner_params,
        engine=engine,
        test=test,
        engine_io=engine_io,
        test_io=test_io,
        test_engine=test_engine,
        imgui_io=imgui_io,
    )


def install_artifact_stubs(monkeypatch, *, overlay=None, visual=None):
    overlay_module = ModuleType("src.client.ui.testing.overlay")
    overlay_module.save_overlay = overlay or Mock(return_value={"saved": True})
    visual_module = ModuleType("src.client.ui.testing.visual_diff")
    visual_module.compare_screenshots = visual or Mock(return_value={"passed": True})
    monkeypatch.setitem(sys.modules, overlay_module.__name__, overlay_module)
    monkeypatch.setitem(sys.modules, visual_module.__name__, visual_module)
    return SimpleNamespace(overlay=overlay_module, visual=visual_module)


def run_with_artifacts(monkeypatch, scenario, output_dir, *, screenshot_error=None, findings=()):
    monkeypatch.setattr(harness_module, "_save_final_screenshot", lambda _path: screenshot_error)
    monkeypatch.setattr(harness_module, "analyze_layout", lambda _snapshot: list(findings))
    install_artifact_stubs(monkeypatch)
    monkeypatch.setattr(harness_module, "_print_report_summary", Mock())
    return harness_module.run_imgui_test(scenario, output_dir)


def load_report(output_dir):
    return json.loads((output_dir / "report.json").read_text(encoding="utf-8"))


def test_run_imgui_test_writes_success_report_and_initializes_optional_dependencies(
    monkeypatch, tmp_path
):
    scenario = make_scenario(
        initialize=Mock(),
        cleanup=Mock(),
        font_path=tmp_path / "ui.ttf",
    )
    runner = install_runner(monkeypatch, call_show_twice=True)
    from src.client.ui.core.font_loader import FontLoader

    configure_font = Mock()
    monkeypatch.setattr(FontLoader, "configure_ui", configure_font)
    artifacts = install_artifact_stubs(monkeypatch)
    monkeypatch.setattr(harness_module, "_save_final_screenshot", lambda _path: None)
    monkeypatch.setattr(harness_module, "analyze_layout", lambda _snapshot: [])
    summary = Mock()
    monkeypatch.setattr(harness_module, "_print_report_summary", summary)

    assert harness_module.run_imgui_test(scenario, tmp_path) == 0

    report = load_report(tmp_path)
    assert report["result"] == "passed"
    assert report["runtime"]["imgui_bundle_version"] == "test-version"
    assert report["runtime"]["viewport"] == {"width": 1024, "height": 768}
    assert report["runtime"]["font"] == {"path": str(tmp_path / "ui.ttf"), "logical_size": 14.0}
    assert report["test_engine"] == {"status": "status:success", "log": "engine log"}
    assert report["overlay"] == {"saved": True}
    assert report["details"] == {"fixture": "unit"}
    assert runner.test.test_func is scenario.test
    assert runner.engine_io.config_run_speed == "fast"
    assert runner.engine_io.config_no_throttle
    assert not runner.engine_io.config_saved_settings
    assert runner.imgui_io.config_flags == 1
    assert runner.imgui_io.set_ini_filename.called
    runner.hello.change_window_size.assert_called_once_with((1024, 768))
    scenario.initialize.assert_called_once_with()
    scenario.cleanup.assert_called_once_with()
    runner.implot.destroy_context.assert_called_once_with("plot-context")
    assert runner.test_engine.get_io.call_count == 2
    assert artifacts.overlay.save_overlay.called
    configure_font.assert_called_once_with(runner.imgui_io, scenario.font_path)
    assert scenario.telemetry.frames == 2
    assert scenario.telemetry.viewport_size == (1024, 768)
    summary.assert_called_once()


def test_run_imgui_test_handles_zero_display_size_and_optional_callbacks(monkeypatch, tmp_path):
    scenario = make_scenario()
    runner = install_runner(monkeypatch, display_size=(0, 0), plot_context=None, call_fonts=False)

    assert run_with_artifacts(monkeypatch, scenario, tmp_path) == 0

    assert load_report(tmp_path)["runtime"]["viewport"] == {"width": 1024, "height": 768}
    assert scenario.telemetry.viewport_size is None
    runner.implot.destroy_context.assert_not_called()


def test_run_imgui_test_reports_registration_timeout(monkeypatch, tmp_path):
    scenario = make_scenario()
    runner = install_runner(
        monkeypatch,
        register=False,
        monotonic_values=(0.0, 61.0),
        plot_context=None,
        call_fonts=False,
    )

    assert run_with_artifacts(monkeypatch, scenario, tmp_path) == 1

    report = load_report(tmp_path)
    assert report["error"] == "ImGui Test Engine did not register the scenario within 60 seconds."
    assert report["test_engine"]["status"] == "not_completed"
    assert report["result"] == "failed"
    assert runner.runner_params.app_shall_exit


@pytest.mark.parametrize(
    ("status", "test_running", "queue_empty", "timed_out", "expected_status", "passed"),
    [
        ("success", False, True, False, "status:success", True),
        ("error", False, True, False, "status:error", False),
        ("idle", True, True, False, "not_completed", False),
        ("idle", False, False, False, "not_completed", False),
        ("idle", False, True, False, "not_completed", False),
        ("idle", True, False, True, "status:idle", False),
    ],
)
def test_run_imgui_test_resolves_engine_completion_and_timeout_states(
    monkeypatch,
    tmp_path,
    status,
    test_running,
    queue_empty,
    timed_out,
    expected_status,
    passed,
):
    scenario = make_scenario()
    times = (0.0, 61.0) if timed_out else (0.0, 1.0)
    runner = install_runner(
        monkeypatch,
        status=status,
        test_running=test_running,
        queue_empty=queue_empty,
        monotonic_values=times,
    )

    assert run_with_artifacts(monkeypatch, scenario, tmp_path) == int(not passed)

    report = load_report(tmp_path)
    assert report["test_engine"]["status"] == expected_status
    assert report["result"] == ("passed" if passed else "failed")
    if timed_out:
        assert report["error"] == "UI test did not finish within 60 seconds."
        assert runner.runner_params.app_shall_exit
    if expected_status == "not_completed":
        runner.test_engine.get_status_name.assert_not_called()


def test_run_imgui_test_records_render_error_and_keeps_first_error(monkeypatch, tmp_path):
    def fail_render():
        raise ValueError("panel render failed")

    scenario = make_scenario(render=fail_render)
    runner = install_runner(monkeypatch, run_error=RuntimeError("runner failed"))

    assert run_with_artifacts(monkeypatch, scenario, tmp_path) == 1

    report = load_report(tmp_path)
    assert "ValueError: panel render failed" in report["error"]
    assert runner.runner_params.app_shall_exit


def test_run_imgui_test_captures_runner_exception_when_no_render_error_exists(monkeypatch, tmp_path):
    scenario = make_scenario()
    runner = install_runner(monkeypatch, register=False, run_error=RuntimeError("startup failed"))
    runner.runner_params.callbacks.show_gui = None

    def fail_before_gui(_params):
        raise RuntimeError("startup failed")

    runner.hello.run = fail_before_gui

    assert run_with_artifacts(monkeypatch, scenario, tmp_path) == 1

    report = load_report(tmp_path)
    assert "RuntimeError: startup failed" in report["error"]
    assert report["test_engine"]["status"] == "not_completed"


@pytest.mark.parametrize(
    ("snapshot", "findings", "screenshot_error", "expected_screenshot", "result"),
    [
        ({"errors": []}, (), None, True, "passed"),
        ({"errors": ["render"]}, (), None, True, "failed"),
        ({"errors": []}, ({"severity": "error", "id": "overlap"},), None, True, "failed"),
        ({"errors": []}, (), "capture failed", False, "failed"),
    ],
)
def test_run_imgui_test_combines_telemetry_layout_and_screenshot_checks(
    monkeypatch,
    tmp_path,
    snapshot,
    findings,
    screenshot_error,
    expected_screenshot,
    result,
):
    scenario = make_scenario(snapshot=snapshot)
    install_runner(monkeypatch)
    monkeypatch.setattr(harness_module, "_save_final_screenshot", lambda _path: screenshot_error)
    monkeypatch.setattr(harness_module, "analyze_layout", lambda _snapshot: list(findings))
    artifacts = install_artifact_stubs(monkeypatch)
    monkeypatch.setattr(harness_module, "_print_report_summary", Mock())

    assert harness_module.run_imgui_test(scenario, tmp_path) == int(result == "failed")

    report = load_report(tmp_path)
    assert report["result"] == result
    assert bool(report["artifacts"]["screenshot"]) is expected_screenshot
    if screenshot_error:
        assert report["screenshot_error"] == screenshot_error
        artifacts.overlay.save_overlay.assert_not_called()
    else:
        assert artifacts.overlay.save_overlay.called


def test_run_imgui_test_reports_overlay_failure_without_hiding_other_results(monkeypatch, tmp_path):
    scenario = make_scenario()
    install_runner(monkeypatch)
    overlay_error = Mock(side_effect=RuntimeError("overlay unavailable"))
    artifacts = install_artifact_stubs(monkeypatch, overlay=overlay_error)
    monkeypatch.setattr(harness_module, "_save_final_screenshot", lambda _path: None)
    monkeypatch.setattr(harness_module, "analyze_layout", lambda _snapshot: [])
    monkeypatch.setattr(harness_module, "_print_report_summary", Mock())

    assert harness_module.run_imgui_test(scenario, tmp_path) == 0

    report = load_report(tmp_path)
    assert report["result"] == "passed"
    assert report["overlay_error"] == "overlay unavailable"
    artifacts.overlay.save_overlay.assert_called_once()


@pytest.mark.parametrize("visual_result", [{"passed": True}, {"passed": False}])
def test_run_imgui_test_compares_baseline_and_applies_visual_result(
    monkeypatch, tmp_path, visual_result
):
    baseline = tmp_path / "baseline.png"
    scenario = make_scenario(baseline=baseline)
    install_runner(monkeypatch)
    visual = Mock(return_value=visual_result)
    artifacts = install_artifact_stubs(monkeypatch, visual=visual)
    monkeypatch.setattr(harness_module, "_save_final_screenshot", lambda _path: None)
    monkeypatch.setattr(harness_module, "analyze_layout", lambda _snapshot: [])
    monkeypatch.setattr(harness_module, "_print_report_summary", Mock())

    assert harness_module.run_imgui_test(scenario, tmp_path) == int(not visual_result["passed"])

    report = load_report(tmp_path)
    assert report["visual"] == visual_result
    assert report["result"] == ("passed" if visual_result["passed"] else "failed")
    artifacts.visual.compare_screenshots.assert_called_once_with(
        tmp_path / "actual.png", baseline, tmp_path, 0.05, [{"x": 1}]
    )


def test_run_imgui_test_records_visual_comparison_exception(monkeypatch, tmp_path):
    scenario = make_scenario(baseline=tmp_path / "baseline.png")
    install_runner(monkeypatch)
    visual_error = Mock(side_effect=OSError("baseline missing"))
    artifacts = install_artifact_stubs(monkeypatch, visual=visual_error)
    monkeypatch.setattr(harness_module, "_save_final_screenshot", lambda _path: None)
    monkeypatch.setattr(harness_module, "analyze_layout", lambda _snapshot: [])
    monkeypatch.setattr(harness_module, "_print_report_summary", Mock())

    assert harness_module.run_imgui_test(scenario, tmp_path) == 1

    assert load_report(tmp_path)["visual"] == {"passed": False, "error": "baseline missing"}
    artifacts.visual.compare_screenshots.assert_called_once()


class FakeImage:
    def __init__(self, shape):
        self.shape = shape
        self.ndim = len(shape)


def install_cv_modules(monkeypatch, *, image, write_result=True, convert_error=None):
    cv2 = ModuleType("cv2")
    cv2.COLOR_RGBA2BGRA = "rgba-to-bgra"
    cv2.COLOR_RGB2BGR = "rgb-to-bgr"
    cv2.cvtColor = Mock(side_effect=convert_error or (lambda value, code: (value, code)))
    cv2.imwrite = Mock(return_value=write_result)
    numpy = ModuleType("numpy")
    numpy.asarray = Mock(return_value=image)
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "numpy", numpy)
    return SimpleNamespace(cv2=cv2, numpy=numpy)


@pytest.mark.parametrize(
    ("channels", "expected_conversion"),
    [(3, "rgb-to-bgr"), (4, "rgba-to-bgra")],
)
def test_save_final_screenshot_converts_rgb_or_rgba_before_writing(
    monkeypatch, tmp_path, channels, expected_conversion
):
    image = FakeImage((4, 5, channels))
    modules = install_cv_modules(monkeypatch, image=image)
    monkeypatch.setattr(
        harness_module,
        "hello_imgui",
        SimpleNamespace(final_app_window_screenshot=Mock(return_value=image)),
    )
    path = tmp_path / "actual.png"

    assert harness_module._save_final_screenshot(path) is None

    modules.numpy.asarray.assert_called_once_with(image)
    modules.cv2.cvtColor.assert_called_once_with(image, expected_conversion)
    modules.cv2.imwrite.assert_called_once_with(str(path), (image, expected_conversion))


@pytest.mark.parametrize(
    ("image", "write_result", "convert_error", "expected"),
    [
        (FakeImage((10, 10)), True, None, "Unexpected screenshot shape: (10, 10)"),
        (FakeImage((1, 1, 3)), False, None, "OpenCV could not write the screenshot file."),
        (FakeImage((1, 1, 3)), True, ValueError("conversion failed"), "ValueError: conversion failed"),
    ],
)
def test_save_final_screenshot_returns_actionable_failure(
    monkeypatch, tmp_path, image, write_result, convert_error, expected
):
    modules = install_cv_modules(
        monkeypatch,
        image=image,
        write_result=write_result,
        convert_error=convert_error,
    )
    monkeypatch.setattr(
        harness_module,
        "hello_imgui",
        SimpleNamespace(final_app_window_screenshot=Mock(return_value=image)),
    )

    assert harness_module._save_final_screenshot(tmp_path / "actual.png") == expected
    if image.ndim == 3 and convert_error is None:
        modules.cv2.imwrite.assert_called_once()


def test_print_report_summary_marks_each_check_and_omits_missing_screenshot(capsys, tmp_path):
    report_path = tmp_path / "report.json"
    screenshot_path = tmp_path / "actual.png"
    report = {
        "result": "failed",
        "test": "coverage/runner-flow",
        "checks": [
            {"passed": True, "id": "render", "message": "Rendered"},
            {"passed": False, "id": "layout", "message": "Overflow"},
        ],
        "artifacts": {"screenshot": None},
    }

    harness_module._print_report_summary(report, report_path, screenshot_path)

    output = capsys.readouterr().out
    assert "UI test FAILED: coverage/runner-flow" in output
    assert "[PASS] render: Rendered" in output
    assert "[FAIL] layout: Overflow" in output
    assert str(report_path.resolve()) in output
    assert str(screenshot_path.resolve()) not in output


def test_print_report_summary_includes_a_saved_screenshot(capsys, tmp_path):
    report = {
        "result": "passed",
        "test": "coverage/runner-flow",
        "checks": [],
        "artifacts": {"screenshot": str((tmp_path / "actual.png").resolve())},
    }

    harness_module._print_report_summary(
        report,
        tmp_path / "report.json",
        tmp_path / "actual.png",
    )

    assert f"Screenshot: {(tmp_path / 'actual.png').resolve()}" in capsys.readouterr().out
