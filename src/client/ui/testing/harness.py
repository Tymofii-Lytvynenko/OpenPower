from __future__ import annotations

import importlib.metadata
import json
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from imgui_bundle import hello_imgui, imgui, implot

from src.client.ui.core.testability import UIRunTelemetry
from src.client.ui.testing.layout_checks import analyze_layout


@dataclass(frozen=True, slots=True)
class UITestScenario:
    category: str
    name: str
    window_title: str
    viewport_size: tuple[int, int]
    telemetry: UIRunTelemetry
    render: Callable[[], None]
    test: Callable[[imgui.test_engine.TestContext], None]
    collect_checks: Callable[[bool], list[dict[str, object]]]
    collect_details: Callable[[], dict[str, object]]
    baseline: Path | None = None
    visual_tolerance: float = 0.03
    visual_masks: tuple[dict, ...] = ()
    initialize: Callable[[], None] | None = None
    cleanup: Callable[[], None] | None = None


def run_imgui_test(scenario: UITestScenario, output_dir: Path) -> int:
    """Run one registered ImGui scenario and write machine-readable artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = output_dir / "actual.png"
    report_path = output_dir / "report.json"
    runtime: dict[str, Any] = {
        "backend": "hello_imgui",
        "imgui_bundle_version": importlib.metadata.version("imgui-bundle"),
        "viewport": {
            "width": scenario.viewport_size[0],
            "height": scenario.viewport_size[1],
        },
    }
    test_handle: dict[str, Any] = {"test": None, "engine": None}
    runner_state: dict[str, Any] = {
        "finished": False,
        "error": None,
        "test_status": "not_completed",
        "test_passed": False,
        "test_log": "",
    }
    started_at = time.monotonic()

    runner_params = hello_imgui.RunnerParams()
    runner_params.app_window_params.window_title = scenario.window_title
    runner_params.app_window_params.window_geometry.size = scenario.viewport_size
    runner_params.app_window_params.window_geometry.window_size_measure_mode = (
        hello_imgui.WindowSizeMeasureMode.screen_coords
    )
    runner_params.use_imgui_test_engine = True
    runner_params.ini_folder_type = hello_imgui.IniFolderType.absolute_path
    runner_params.ini_filename_use_app_window_title = False
    runner_params.imgui_window_params.default_imgui_window_type = hello_imgui.DefaultImGuiWindowType.no_default_window

    def register_tests() -> None:
        engine = hello_imgui.get_imgui_test_engine()
        test = imgui.test_engine.register_test(
            engine,
            scenario.category,
            scenario.name,
        )
        test.test_func = scenario.test
        engine_io = imgui.test_engine.get_io(engine)
        engine_io.config_run_speed = imgui.test_engine.TestRunSpeed.fast
        engine_io.config_saved_settings = False
        test_handle["engine"] = engine
        test_handle["test"] = test
        imgui.test_engine.queue_test(engine, test)

    def render_frame() -> None:
        try:
            with scenario.telemetry.frame():
                scenario.render()
        except Exception:
            runner_state["error"] = traceback.format_exc()
            hello_imgui.get_runner_params().app_shall_exit = True
            return

        if runner_state["finished"]:
            return

        engine = test_handle["engine"]
        test = test_handle["test"]
        if engine is None or test is None:
            if time.monotonic() - started_at > 60.0:
                runner_state["error"] = "ImGui Test Engine did not register the scenario within 60 seconds."
                runner_state["finished"] = True
                hello_imgui.get_runner_params().app_shall_exit = True
            return

        test_io = imgui.test_engine.get_io(engine)
        timed_out = time.monotonic() - started_at > 60.0
        test_complete = (
            not test_io.is_running_tests
            and imgui.test_engine.is_test_queue_empty(engine)
            and test.output.status
            in (imgui.test_engine.TestStatus.success, imgui.test_engine.TestStatus.error)
        )
        if timed_out:
            runner_state["error"] = "UI test did not finish within 60 seconds."
        if test_complete or timed_out:
            runner_state["test_status"] = imgui.test_engine.get_status_name(
                test.output.status
            )
            runner_state["test_passed"] = (
                test_complete
                and test.output.status == imgui.test_engine.TestStatus.success
            )
            runner_state["test_log"] = test.output.log.get_text()
            runner_state["finished"] = True
            hello_imgui.get_runner_params().app_shall_exit = True

    runner_params.callbacks.register_tests = register_tests
    runner_params.callbacks.show_gui = render_frame
    plot_context = {"value": None}

    def initialize() -> None:
        plot_context["value"] = implot.create_context()
        # Isolate runs from saved positions, including earlier viewport sizes.
        imgui.get_io().set_ini_filename("")
        imgui.get_io().config_flags |= imgui.ConfigFlags_.nav_enable_keyboard
        if scenario.initialize is not None:
            scenario.initialize()

    def cleanup() -> None:
        if scenario.cleanup is not None:
            scenario.cleanup()
        if plot_context["value"] is not None:
            implot.destroy_context(plot_context["value"])
            plot_context["value"] = None

    runner_params.callbacks.post_init = initialize
    runner_params.callbacks.before_exit = cleanup

    try:
        runner_params.ini_filename = str((output_dir / "imgui.ini").resolve())
        hello_imgui.run(runner_params)
    except Exception:
        if runner_state["error"] is None:
            runner_state["error"] = traceback.format_exc()

    screenshot_error = _save_final_screenshot(screenshot_path)
    test_status = runner_state["test_status"]
    test_passed = (
        bool(runner_state["test_passed"])
        and runner_state["error"] is None
    )
    checks = scenario.collect_checks(test_passed)
    snapshot = scenario.telemetry.to_dict()
    findings = analyze_layout(snapshot)
    checks.append({"id": "layout.geometry", "passed": not any(f["severity"] == "error" for f in findings),
                   "message": f"{len(findings)} layout findings; see layout_findings for IDs and source locations."})
    checks.append({"id": "runtime.render_errors", "passed": not snapshot["errors"],
                   "message": "No render errors were reported by UI components."})
    checks_passed = all(bool(check.get("passed")) for check in checks)
    result = "passed" if test_passed and checks_passed and screenshot_error is None else "failed"

    report: dict[str, object] = {
        "schema_version": 1,
        "test": f"{scenario.category}/{scenario.name}",
        "result": result,
        "runtime": runtime,
        "checks": checks,
        "test_engine": {
            "status": test_status,
            "log": runner_state["test_log"],
        },
        "telemetry": snapshot,
        "layout_findings": findings,
        "details": scenario.collect_details(),
        "artifacts": {
            "screenshot": str(screenshot_path.resolve()) if screenshot_error is None else None,
            "report": str(report_path.resolve()),
        },
    }
    if runner_state["error"] is not None:
        report["error"] = runner_state["error"]
    if screenshot_error is not None:
        report["screenshot_error"] = screenshot_error
    else:
        from src.client.ui.testing.overlay import save_overlay
        try:
            report["overlay"] = save_overlay(screenshot_path, output_dir / "overlay.png", snapshot)
        except Exception as exc:
            report["overlay_error"] = str(exc)
    if scenario.baseline is not None and screenshot_error is None:
        from src.client.ui.testing.visual_diff import compare_screenshots
        try:
            report["visual"] = compare_screenshots(screenshot_path, scenario.baseline, output_dir,
                                                   scenario.visual_tolerance, list(scenario.visual_masks))
        except Exception as exc:
            report["visual"] = {"passed": False, "error": str(exc)}
        if not report["visual"]["passed"]:
            report["result"] = "failed"

    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _print_report_summary(report, report_path, screenshot_path)
    return 0 if report["result"] == "passed" else 1


def _save_final_screenshot(path: Path) -> str | None:
    try:
        import cv2
        import numpy as np

        image = np.asarray(hello_imgui.final_app_window_screenshot())
        if image.ndim != 3 or image.shape[2] not in (3, 4):
            return f"Unexpected screenshot shape: {image.shape!r}"
        color_conversion = cv2.COLOR_RGBA2BGRA if image.shape[2] == 4 else cv2.COLOR_RGB2BGR
        if not cv2.imwrite(str(path), cv2.cvtColor(image, color_conversion)):
            return "OpenCV could not write the screenshot file."
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def _print_report_summary(
    report: dict[str, object], report_path: Path, screenshot_path: Path
) -> None:
    result = str(report["result"]).upper()
    print(f"UI test {result}: {report['test']}")
    for check in report["checks"]:
        marker = "PASS" if check["passed"] else "FAIL"
        print(f"[{marker}] {check['id']}: {check['message']}")
    print(f"Report: {report_path.resolve()}")
    if report["artifacts"]["screenshot"] is not None:
        print(f"Screenshot: {screenshot_path.resolve()}")
