from __future__ import annotations

from typing import Any

from src.client.ui.core.instrumented_imgui import imgui
import polars as pl

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.shared.panel_widgets import draw_empty_state
from src.client.services.history_query_service import HistoryQueryService


class HistoryPanel:
    """Interactive read-only browser for persisted historical observations."""

    _RANGES = (("30 days", 30 * 1440), ("1 year", 365 * 1440), ("5 years", 5 * 365 * 1440), ("All", 0))

    def __init__(self) -> None:
        self._queries = HistoryQueryService()
        self._indicator_id = ""
        self._subject_type = "country"
        self._subject_id = ""
        self._subject_search = ""
        self._comparison_ids: set[str] = set()
        self._comparison_initialized = False
        self._normalize_comparison_by_indicator: dict[str, bool] = {}
        self._range_minutes = 365 * 1440
        self._granularity_minutes = 0
        self._step_trend = False
        self._ranking_descending = True
        self._export_status = ""
        self._subject_cache: dict[str, tuple[tuple[int, ...], list[str]]] = {}

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("HISTORY & ANALYTICS", x=900, y=90, w=740, h=650) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        definitions_table = state.tables.get("history_indicator_definitions")
        if definitions_table is None or definitions_table.is_empty():
            draw_empty_state("Historical data will appear after the first simulation update.")
            return
        definitions = [row for row in definitions_table.to_dicts() if row.get("enabled", True)]
        if not definitions:
            draw_empty_state("No history indicators are enabled.")
            return

        self._render_indicator_selector(definitions)
        matching = next((row for row in definitions if row.get("id") == self._indicator_id), definitions[0])
        self._indicator_id = str(matching.get("id") or "")
        self._subject_type = str(matching.get("subject_type") or "country")
        subjects = self._subjects(state, self._subject_type)
        if not subjects:
            draw_empty_state("No subjects currently provide this indicator.")
            return
        default_subject = str(context.target_tag or "").upper()
        if self._subject_type == "region" and context.selected_region_id is not None:
            default_subject = str(context.selected_region_id)
        if self._subject_id not in subjects:
            self._subject_id = default_subject if default_subject in subjects else subjects[0]
        self._render_subject_selector(subjects)
        self._render_range_selector()
        _, self._step_trend = imgui.checkbox("Step trend", self._step_trend)

        now = int(state.time.total_minutes)
        start = now - self._range_minutes if self._range_minutes > 0 else None
        selected_series = self._queries.series(
            state, self._subject_type, self._subject_id, self._indicator_id,
            start_minute=start, end_minute=now, granularity_minutes=self._granularity_minutes,
        )
        current = self._queries.current_value(state, self._subject_type, self._subject_id, self._indicator_id)
        unit = str(matching.get("unit") or "")
        imgui.separator()
        if current.get("available"):
            latest = selected_series[-1] if selected_series else None
            current_text = self._format_value(current.get("value"), unit)
            sampled_text = "unavailable" if latest is None else self._format_value(latest.get("value"), unit)
            imgui.text(f"Current: {current_text}    Latest sample: {sampled_text}")
            imgui.text_disabled(f"Source: {current.get('value_kind', 'unknown')} · samples: {len(selected_series)}")
        else:
            imgui.text_disabled(f"Current value unavailable · unit: {unit or 'unspecified'}")
        self._draw_trend(selected_series, unit, step=self._step_trend)
        comparison = self._render_comparison(state, subjects, start, now)
        self._render_ranking(state, start, now)
        timeline = self._render_timelines(state, now)
        self._render_export(selected_series, comparison, timeline)

    def _render_indicator_selector(self, definitions: list[dict[str, Any]]) -> None:
        by_type: dict[str, list[dict[str, Any]]] = {}
        for row in definitions:
            by_type.setdefault(str(row.get("subject_type") or "country"), []).append(row)
        types = sorted(by_type)
        if self._subject_type not in types:
            self._subject_type = types[0]
        preview = self._label(self._indicator_id) if self._indicator_id else "Choose indicator"
        if imgui.begin_combo("Indicator", preview):
            for subject_type in types:
                for row in sorted(by_type[subject_type], key=lambda item: str(item.get("id") or "")):
                    indicator_id = str(row.get("id") or "")
                    label = f"{self._label(indicator_id)} ({subject_type})"
                    selected = indicator_id == self._indicator_id
                    if imgui.selectable(label, selected)[0]:
                        self._indicator_id = indicator_id
                        self._subject_type = subject_type
                    if selected:
                        imgui.set_item_default_focus()
            imgui.end_combo()

    def _render_subject_selector(self, subjects: list[str]) -> None:
        _, self._subject_search = imgui.input_text("Find subject", self._subject_search, 64)
        normalized_search = self._subject_search.strip().lower()
        visible_subjects = [
            item for item in subjects
            if not normalized_search or normalized_search in item.lower()
        ][:200]
        if imgui.begin_combo("Subject", self._subject_id):
            for subject_id in visible_subjects:
                if imgui.selectable(subject_id, subject_id == self._subject_id)[0]:
                    self._subject_id = subject_id
            if not visible_subjects:
                imgui.text_disabled("No matching subjects.")
            imgui.end_combo()

    def _render_range_selector(self) -> None:
        preview = next((name for name, minutes in self._RANGES if minutes == self._range_minutes), "Custom")
        if imgui.begin_combo("Time range", preview):
            for name, minutes in self._RANGES:
                if imgui.selectable(name, minutes == self._range_minutes)[0]:
                    self._range_minutes = minutes
            imgui.end_combo()
        imgui.same_line()
        if imgui.begin_combo("Granularity", str(self._granularity_minutes or "Raw") + (" min" if self._granularity_minutes else "")):
            for label, minutes in (("Raw", 0), ("1 day", 1440), ("1 week", 10080), ("1 month", 43200)):
                if imgui.selectable(label, minutes == self._granularity_minutes)[0]:
                    self._granularity_minutes = minutes
            imgui.end_combo()

    def _render_comparison(self, state, subjects: list[str], start: int | None, end: int) -> dict[str, Any] | None:
        if self._subject_type not in {"country", "region"} or len(subjects) < 2:
            return None
        alternatives = [subject for subject in subjects if subject != self._subject_id]
        self._comparison_ids.intersection_update(alternatives)
        if not self._comparison_initialized and alternatives:
            self._comparison_ids.add(alternatives[0])
            self._comparison_initialized = True
        if imgui.begin_combo("Compare with", f"{len(self._comparison_ids)} selected"):
            for subject in alternatives:
                changed, selected = imgui.checkbox(subject, subject in self._comparison_ids)
                if changed:
                    if selected:
                        self._comparison_ids.add(subject)
                    else:
                        self._comparison_ids.discard(subject)
            imgui.end_combo()
        comparison_subjects = [self._subject_id, *sorted(self._comparison_ids)]
        comparison = self._queries.compare(
            state, self._subject_type, comparison_subjects, self._indicator_id,
            start_minute=start, end_minute=end, granularity_minutes=self._granularity_minutes,
        )
        normalize = self._normalize_comparison_by_indicator.get(
            self._indicator_id, not comparison["unit_compatible"]
        )
        _, normalize = imgui.checkbox("Index each series to first positive sample = 100", normalize)
        self._normalize_comparison_by_indicator[self._indicator_id] = normalize
        displayed_values = (
            comparison.get("normalized_common_values", {})
            if normalize else comparison.get("common_values", {})
        )
        imgui.text("Comparison:")
        for subject in comparison_subjects:
            latest = displayed_values.get(subject)
            value = (
                self._format_value(latest.get("value"), latest.get("unit", ""))
                if latest else "unavailable"
            )
            if normalize and latest:
                baseline = self._format_value(
                    latest.get("baseline_value"), latest.get("baseline_unit", "")
                )
                value += f" (base {baseline} at minute {latest.get('baseline_minute')})"
            imgui.text(f"  {subject}: {value}")
        if normalize:
            imgui.text_disabled(str(comparison.get("normalization_basis") or "Indexed series comparison."))
            unavailable = comparison.get("normalization_unavailable_subjects", [])
            if unavailable:
                imgui.text_disabled("No compatible positive baseline for: " + ", ".join(unavailable[:8]))
        elif not comparison["unit_compatible"]:
            imgui.text_colored(
                (1.0, 0.45, 0.2, 1.0),
                "Units differ; enable indexed comparison before comparing magnitudes.",
            )
        if comparison.get("evaluation_minute") is not None:
            imgui.text_disabled(f"All values evaluated at minute {comparison['evaluation_minute']}.")
        if displayed_values and imgui.button("Copy comparison CSV"):
            imgui.set_clipboard_text(self._queries.export_csv(displayed_values.values()))
        return comparison

    def _render_ranking(self, state, start: int | None, end: int) -> None:
        if self._subject_type != "country":
            return
        _, self._ranking_descending = imgui.checkbox("Highest first", self._ranking_descending)
        ranking = self._queries.rank(
            state, self._indicator_id, subject_type="country", start_minute=start, end_minute=end,
            descending=self._ranking_descending,
        )
        direction = "highest first" if self._ranking_descending else "lowest first"
        period = "all recorded history" if start is None else f"minutes {start}–{end}"
        boundary = ranking.get("evaluation_minute")
        boundary_text = str(boundary) if boundary is not None else "unavailable"
        imgui.text(
            f"Ranking: {self._label(self._indicator_id)} · {period} · {direction} · "
            f"common boundary {boundary_text}"
        )
        imgui.text_disabled("Tie rule: subject ID ascending.")
        freshness_by_subject = ranking.get("freshness_by_subject", {})
        for index, row in enumerate(ranking.get("rows", [])[:8], start=1):
            subject_id = str(row.get("subject_id") or "")
            freshness = freshness_by_subject.get(subject_id)
            freshness_text = "unknown age" if freshness is None else f"{freshness} min old"
            imgui.text(
                f"{index:>2}. {subject_id}: "
                f"{self._format_value(row.get('value'), row.get('unit', ''))} · {freshness_text}"
            )
        incompatible_units = ranking.get("incompatible_unit_subjects", [])
        if incompatible_units:
            imgui.text_colored(
                (1.0, 0.45, 0.2, 1.0),
                "Excluded for incompatible units: " + ", ".join(incompatible_units[:8]),
            )
        excluded = sorted(set(ranking.get("excluded", [])) - set(incompatible_units))
        if excluded:
            imgui.text_disabled("Unavailable at boundary: " + ", ".join(excluded[:8]))
        for tie in ranking.get("ties", [])[:3]:
            imgui.text_disabled(f"Tie at {self._format_value(tie.get('value'), tie.get('unit', ''))}: {', '.join(tie.get('subjects', []))}")

    def _render_timelines(self, state, now: int) -> None:
        imgui.separator()
        if self._subject_type == "relationship" and "|" in self._subject_id:
            country_a, country_b = self._subject_id.split("|", 1)
            events = self._queries.relationship_timeline(state, country_a, country_b)
            imgui.text("Relationship timeline")
        else:
            events = self._queries.event_timeline(
                state,
                subject_type=self._subject_type if self._subject_type != "country" else None,
                subject_id=self._subject_id if self._subject_type != "country" else None,
                country_ids=[self._subject_id] if self._subject_type == "country" else (),
                start_minute=max(0, now - 365 * 1440), end_minute=now,
            )
            imgui.text("Recorded events and causes")
        if not events:
            imgui.text_disabled("No attributable events are recorded in this period.")
        else:
            for event in events[-6:]:
                title = str(event.get("title") or event.get("event_type") or "Recorded event")
                cause = f" · cause {event.get('cause_source_type')}:{event.get('cause_source_id')}" if event.get("cause_source_type") else " · cause unknown"
                imgui.text(f"{event.get('game_minute', 0):>8}  {title}{cause}")
            if imgui.button("Copy event timeline CSV"):
                imgui.set_clipboard_text(self._queries.export_csv(events))
        return events

    def _render_export(self, records: list[dict[str, Any]], comparison, timeline: list[dict[str, Any]]) -> None:
        imgui.separator()
        if imgui.button("Copy selected series as CSV"):
            if records:
                imgui.set_clipboard_text(self._queries.export_csv(records))
                self._export_status = f"Copied {len(records)} row(s)."
            else:
                self._export_status = "There are no samples to export."
        if self._export_status:
            imgui.same_line()
            imgui.text_disabled(self._export_status)

    def _subjects(self, state, subject_type: str) -> list[str]:
        source_tables = ("countries", "regions", "countries_relations", "history_series_state")
        revisions = getattr(state, "table_revisions", {})
        revision_key = tuple(int(revisions.get(name, 0)) for name in source_tables)
        cached = self._subject_cache.get(subject_type)
        if cached is not None and cached[0] == revision_key:
            return list(cached[1])

        subjects: set[str] = set()
        if subject_type == "country":
            table = state.tables.get("countries")
            if table is not None and "id" in table.columns:
                subjects.update(str(value).upper() for value in table.get_column("id").to_list())
        elif subject_type == "region":
            table = state.tables.get("regions")
            if table is not None and "id" in table.columns:
                subjects.update(str(value) for value in table.get_column("id").to_list())
        elif subject_type == "relationship":
            table = state.tables.get("countries_relations")
            if table is not None and {"source", "target"}.issubset(table.columns):
                subjects.update(
                    "|".join(sorted((str(row["source"]).upper(), str(row["target"]).upper())))
                    for row in table.to_dicts()
                )

        series = state.tables.get("history_series_state")
        if series is not None and {"subject_type", "subject_id"}.issubset(series.columns):
            # Historical series outlive removed source rows and remain directly inspectable by ID.
            subjects.update(
                str(row.get("subject_id") or "").upper()
                if subject_type == "country" else str(row.get("subject_id") or "")
                for row in series.filter(pl.col("subject_type") == subject_type).select("subject_id").to_dicts()
                if row.get("subject_id")
            )

        result = sorted(subjects)
        self._subject_cache[subject_type] = (revision_key, result)
        return list(result)

    @staticmethod
    def _draw_trend(records: list[dict[str, Any]], unit: str, *, step: bool = False) -> None:
        values = [row.get("value") for row in records]
        numeric = [float(value) for value in values if value is not None]
        if not numeric:
            draw_empty_state("No historical samples in this range; no zero line is implied.")
            return
        low, high = min(numeric), max(numeric)
        plotted = values[-240:]
        width = max(1.0, float(imgui.get_content_region_avail().x))
        height = 100.0
        start = imgui.get_cursor_screen_pos()
        draw = imgui.get_window_draw_list()
        draw.add_rect_filled(start, (start.x + width, start.y + height), imgui.get_color_u32((0.05, 0.07, 0.09, 1.0)))
        draw.add_line((start.x, start.y + height - 1), (start.x + width, start.y + height - 1), imgui.get_color_u32((0.35, 0.39, 0.43, 1.0)), 1.0)
        span = high - low
        points: list[tuple[float, float] | None] = []
        for index, value in enumerate(plotted):
            x = start.x + (width * index / max(1, len(plotted) - 1))
            if value is None:
                points.append(None)
                draw.add_rect_filled((x - 2, start.y + 3), (x + 2, start.y + height - 3), imgui.get_color_u32((0.75, 0.35, 0.2, 0.55)))
                continue
            normalized = 0.5 if span == 0 else (float(value) - low) / span
            y = start.y + height - 6 - max(0.0, min(1.0, normalized)) * (height - 12)
            points.append((x, y))
        color = imgui.get_color_u32((0.35, 0.78, 0.98, 1.0))
        for left, right in HistoryPanel._trend_segments(points, step=step):
            draw.add_line(left, right, color, 2.0)
        imgui.dummy((width, height + 4))
        trend_kind = "step" if step else "line"
        imgui.text_disabled(f"Min {low:,.3f} · max {high:,.3f} · {unit or 'unit unspecified'} · {trend_kind} trend · gaps marked · no interpolation")

    @staticmethod
    def _trend_segments(
        points: list[tuple[float, float] | None], *, step: bool = False,
    ) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for left, right in zip(points, points[1:]):
            if left is None or right is None:
                continue
            if step:
                corner = (right[0], left[1])
                segments.extend(((left, corner), (corner, right)))
            else:
                segments.append((left, right))
        return segments

    @staticmethod
    def _label(value: str) -> str:
        return str(value).replace("_", " ").replace(".", " / ").title()

    @staticmethod
    def _format_value(value: Any, unit: Any) -> str:
        if value is None:
            return "unavailable"
        return f"{float(value):,.3f} {str(unit or '').strip()}".strip()
