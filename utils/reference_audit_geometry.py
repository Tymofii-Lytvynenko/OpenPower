"""Compare reference route geometry with recorded UI telemetry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _route_evidence_snapshot(report: dict, region_id: str) -> tuple[dict, str]:
    # Journeys often close the destination after checking it. Its final-frame
    # telemetry cannot replace the native capture made while it was visible.
    for step in report.get("details", {}).get("steps", []):
        if step.get("region") != region_id or not step.get("passed") or not step.get("screenshot"):
            continue
        screenshot = Path(step["screenshot"])
        try:
            snapshot = json.loads(screenshot.with_suffix(".json").read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if screenshot.is_file() and any(item.get("id") == region_id and item.get("visible")
                                        and item.get("present") for item in snapshot.get("regions", [])):
            return snapshot, str(screenshot)
    return report.get("telemetry", {}), report.get("artifacts", {}).get("screenshot", "")


def _layout_geometry_crosswalk(
    edges: list[dict[str, Any]],
    journey_rows: list[dict[str, Any]],
    component_rows: list[dict[str, Any]],
    window_rows: list[dict[str, Any]],
    journey_suite: dict[str, Any],
    *,
    viewport: tuple[int, int] = (1280, 720),
    repo_root: Path,
    latest_reports: dict[str, Path],
    edge_bindings: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """Pair source route geometry with telemetry captured by its Python journey."""
    components = {
        (row["window_id"], row["component_path"]): row
        for row in component_rows
    }
    windows = {row["window_id"]: row for row in window_rows}
    routes = {
        (row["source_file"], int(row["source_line"]), row["target_window"]): row
        for row in journey_rows
    }
    suite_results = {
        Path(result.get("journey", "")).name: result
        for result in journey_suite.get("results", [])
    }
    rows: list[dict[str, Any]] = []
    for edge in edges:
        source_window = edge["source_window"]
        source_widget = edge["source_widget_path"]
        target_window = edge["target_window"]
        journey = routes.get((edge["source_file"], int(edge["source_line"]), target_window), {})
        source_gml_widget = journey.get("source_gml_component_path") or source_widget
        gml_component = components.get((source_window, source_gml_widget), {})
        effective_target = journey.get("effective_target_window", target_window)
        gml_target = windows.get(effective_target, {})
        suite_result = suite_results.get(Path(journey.get("journey_file", "")).name, {})
        report_path = Path(suite_result.get("report", ""))
        latest_report = latest_reports.get(Path(journey.get("journey_file", "")).name)
        if latest_report is not None and (repo_root / latest_report).is_file():
            report_path = repo_root / latest_report
            try:
                latest_report_data = json.loads(report_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                latest_report_data = {}
            suite_result = {"passed": latest_report_data.get("result") == "passed"}
        report = {}
        if suite_result.get("passed") and report_path.is_file():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                report = {}

        telemetry, screenshot = _route_evidence_snapshot(
            report, journey.get("expected_openpower_region", ""),
        )
        widgets = {item.get("id"): item for item in telemetry.get("widgets", [])}
        regions = {item.get("id"): item for item in telemetry.get("regions", [])}
        control = widgets.get(journey.get("journey_control_id", ""), {})
        region = regions.get(journey.get("expected_openpower_region", ""), {})
        control_rect = control.get("rect", {})
        region_rect = region.get("rect", {})
        source_gml_geometry = {
            key: gml_component.get(key, "")
            for key in ("left", "top", "width", "height")
        }
        if gml_component and region_rect and gml_target.get("width"):
            geometry_status = "source_widget_and_python_destination_measured"
        elif region_rect and gml_target.get("width"):
            geometry_status = "python_destination_measured_source_widget_unresolved"
        elif gml_target.get("width"):
            geometry_status = "gml_window_geometry_only"
        else:
            geometry_status = "source_geometry_unavailable"

        rows.append({
            "source_window": source_window,
            "source_file": edge["source_file"],
            "source_line": edge["source_line"],
            "source_widget_path": source_widget,
            "source_gml_widget_path": source_gml_widget,
            "source_widget_path_status": edge.get("control_path_status", ""),
            "event": edge["event"],
            "target_window": target_window,
            "effective_target_window": effective_target,
            "mode": edge["mode"],
            "source_gml_widget_geometry": json.dumps(source_gml_geometry, ensure_ascii=False),
            "target_gml_window_geometry": (
                f"{gml_target.get('width', '')}x{gml_target.get('height', '')}"
                if gml_target.get("width") else ""
            ),
            "openpower_mapping_status": gml_target.get("mapping_status", ""),
            "journey_file": journey.get("journey_file", ""),
            "openpower_control_id": journey.get("journey_control_id", ""),
            "openpower_control_rect": json.dumps(control_rect, ensure_ascii=False) if control_rect else "",
            "openpower_destination_region": journey.get("expected_openpower_region", ""),
            "openpower_destination_rect": json.dumps(region_rect, ensure_ascii=False) if region_rect else "",
            "reference_viewport": f"{viewport[0]}x{viewport[1]}",
            "journey_status": journey.get("coverage_status", ""),
            "geometry_status": geometry_status,
            "journey_report": str(report_path) if report else "",
            "screenshot": screenshot,
            "action_required": (
                edge_bindings.get(source_widget, {}).get("geometry_action_required") or (
                    "Review component-level content and placement; the OpenPower theme and pixel styling are intentionally independent."
                    if geometry_status == "source_widget_and_python_destination_measured"
                    else "Resolve a testable OpenPower route and map its rendered control/destination geometry."
                )
            ),
        })
    return rows


