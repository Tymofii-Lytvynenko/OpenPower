from __future__ import annotations

from typing import Any

from src.client.ui.core.instrumented_imgui import imgui
import polars as pl

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import (
    active_gml_layout,
    get_gml_layout,
    resume_gml_layout,
    suspend_gml_layout,
)
from src.client.ui.panels.shared.panel_widgets import draw_empty_state
from src.client.ui.panels.service.history_event_marker_layer import HistoryEventMarkerLayer
from src.client.services.history_indicator_catalog import (
    history_indicator_sort_key,
    history_indicator_source_label,
)
from src.client.services.history_query_service import HistoryQueryService


class HistoryPanel:
    """Interactive read-only browser for persisted historical observations."""

    _DEFAULT_INDICATOR_IDS = {"country": "country.population"}
    _RANGES = (("1 month", 30 * 1440), ("6 months", 182 * 1440), ("1 year", 365 * 1440), ("2 years", 730 * 1440))

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
        self._history_event_markers = HistoryEventMarkerLayer()

    def render(self, state, context: PanelRenderContext) -> bool:
        viewport = imgui.get_main_viewport()
        layout = get_gml_layout("History_Window")
        x = min(900.0, max(0.0, float(viewport.size.x) - layout.width))
        y = min(90.0, max(0.0, float(viewport.size.y) - layout.height))
        with WindowManager.window(
            "HISTORY###HistoryPanel", x=x, y=y,
            w=layout.width, h=layout.height,
            test_id="history.panel", gml_template="History_Window",
        ) as is_open:
            if not is_open:
                self._history_event_markers.hide()
                return False
            self._render_content(state, context)
        self._history_event_markers.render_tooltip()
        return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        ui = GMLWidgets("History_Window/frmInner/frmHistory")
        title_ui = GMLWidgets("History_Window/frmTitle")
        if title_ui.button("btnApply", "…", "history.analytics", tooltip="Open additional analytics"):
            imgui.open_popup("HistoryAnalytics")

        definitions_table = state.tables.get("history_indicator_definitions")
        definitions = (
            [row for row in definitions_table.to_dicts() if row.get("enabled", True)]
            if definitions_table is not None and not definitions_table.is_empty()
            else []
        )
        matching = self._render_indicator_selector(definitions, ui)
        now = int(state.time.total_minutes)
        start = max(0, now - self._range_minutes)
        if matching is None:
            self._history_event_markers.hide()
            self._render_chart_message("Historical data will appear after the first simulation update.")
            self._render_analysis_popup(state, [], start, now, [])
            return

        self._indicator_id = str(matching.get("id") or "")
        self._subject_type = str(matching.get("subject_type") or "country")
        subjects = self._subjects(state, self._subject_type)
        if not subjects:
            self._history_event_markers.hide()
            self._render_chart_message("No subjects currently provide this indicator.")
            return
        default_subject = str(context.target_tag or "").upper()
        if self._subject_type == "region" and context.selected_region_id is not None:
            default_subject = str(context.selected_region_id)
        if self._subject_id not in subjects:
            self._subject_id = default_subject if default_subject in subjects else subjects[0]
        selected_series = self._queries.series(
            state, self._subject_type, self._subject_id, self._indicator_id,
            start_minute=start, end_minute=now, granularity_minutes=self._granularity_minutes,
        )
        unit = str(matching.get("unit") or "")
        events = self._history_events(state, start, now)
        values = [float(row["value"]) for row in selected_series if row.get("value") is not None]
        low, high = (min(values), max(values)) if values else (None, None)
        graph_ui = GMLWidgets("History_Window/frmInner/frmHistory/frmGraph")
        graph_ui.text(
            "txtV0", self._axis_value(low),
            tooltip=self._format_value(low, unit) if low is not None else "No recorded minimum",
            test_id="history.axis.min",
        )
        graph_ui.text(
            "txtV1", self._axis_value(high),
            tooltip=self._format_value(high, unit) if high is not None else "No recorded maximum",
            test_id="history.axis.max",
        )
        self._render_time_ticks(graph_ui, now)
        self._draw_trend(
            selected_series,
            unit,
            events=events,
            start_minute=start,
            end_minute=now,
            step=self._step_trend,
        )
        self._render_analysis_popup(state, subjects, start, now, selected_series)

    def _render_indicator_selector(self, definitions: list[dict[str, Any]], ui: GMLWidgets) -> dict[str, Any] | None:
        by_type: dict[str, list[dict[str, Any]]] = {}
        for row in definitions:
            by_type.setdefault(str(row.get("subject_type") or "country"), []).append(row)
        types = sorted(by_type)
        if not definitions:
            imgui.push_style_var(imgui.StyleVar_.frame_padding, (3.0, 2.0))
            imgui.begin_disabled()
            try:
                imgui.combo(
                    "##history_indicator", 0, ["No indicators available"],
                    test_id="history.indicator", gml_id=ui.path("cboDisplay"),
                )
            finally:
                imgui.end_disabled()
                imgui.pop_style_var()
            return None
        if self._subject_type not in types:
            self._subject_type = types[0]
        options = []
        for row in sorted(definitions, key=history_indicator_sort_key):
            indicator_id = str(row.get("id") or "")
            subject_type = str(row.get("subject_type") or "country")
            label = history_indicator_source_label(indicator_id) or self._label(indicator_id)
            options.append((indicator_id, f"{label} ({subject_type})"))
        selected_index = next(
            (index for index, (indicator_id, _) in enumerate(options) if indicator_id == self._indicator_id),
            next(
                (
                    index for index, (indicator_id, _) in enumerate(options)
                    if indicator_id == self._DEFAULT_INDICATOR_IDS.get(self._subject_type)
                ),
                0,
            ),
        )
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (3.0, 2.0))
        try:
            changed, selected_index = imgui.combo(
                "##history_indicator", selected_index, [label for _, label in options],
                test_id="history.indicator", gml_id=ui.path("cboDisplay"),
            )
        finally:
            imgui.pop_style_var()
        if changed:
            self._indicator_id = options[selected_index][0]
        selected_id = options[selected_index][0]
        return next(row for rows in by_type.values() for row in rows if str(row.get("id") or "") == selected_id)

    def _render_subject_selector(self, subjects: list[str]) -> None:
        imgui.text_disabled("Find subject")
        _, self._subject_search = imgui.input_text("##history_subject_filter", self._subject_search, 64)
        normalized_search = self._subject_search.strip().lower()
        visible_subjects = [
            item for item in subjects
            if not normalized_search or normalized_search in item.lower()
        ][:200]
        imgui.text_disabled("Subject")
        if imgui.begin_combo("##history_subject", self._subject_id):
            for subject_id in visible_subjects:
                if imgui.selectable(subject_id, subject_id == self._subject_id)[0]:
                    self._subject_id = subject_id
            if not visible_subjects:
                imgui.text_disabled("No matching subjects.")
            imgui.end_combo()

    def _render_time_range_selector(self) -> None:
        imgui.text_disabled("Time range")
        selected_index = next(
            (index for index, (_, minutes) in enumerate(self._RANGES) if minutes == self._range_minutes),
            2,
        )
        changed, selected_index = imgui.combo(
            "##history_time_range",
            selected_index,
            [label for label, _ in self._RANGES],
            test_id="history.range",
        )
        if changed:
            self._range_minutes = self._RANGES[selected_index][1]

    def _render_time_ticks(self, ui: GMLWidgets, now: int) -> None:
        range_days = max(1, self._range_minutes // 1440)
        for index in range(6):
            days_ago = round(range_days * (5 - index) / 5)
            label = "now" if days_ago == 0 else f"-{days_ago}d" if days_ago < 60 else f"-{round(days_ago / 30)}mo"
            ui.text(
                f"txtH{index}", label,
                tooltip=f"{days_ago} days before minute {now}" if days_ago else f"Current game minute {now}",
                test_id=f"history.axis.time.{index}",
            )

    def _render_chart_message(self, message: str) -> None:
        graph_ui = GMLWidgets("History_Window/frmInner/frmHistory/frmGraph")
        rect = graph_ui.rect("Container")
        session = active_gml_layout()
        if rect is None or session is None:
            draw_empty_state(message)
            return
        imgui.set_cursor_screen_pos((
            session.window_position[0] + rect.x,
            session.window_position[1] + rect.y,
        ))
        x, y = session.window_position[0] + rect.x, session.window_position[1] + rect.y
        draw = imgui.get_window_draw_list()
        draw.add_rect_filled((x, y), (x + rect.width, y + rect.height), imgui.get_color_u32((0.035, 0.045, 0.055, 0.94)))
        draw.add_rect((x, y), (x + rect.width, y + rect.height), imgui.get_color_u32((0.45, 0.50, 0.56, 0.55)), 1.0)
        # The empty-state sentence can exceed the graph width at the game's font size.
        token = suspend_gml_layout()
        try:
            imgui.set_cursor_screen_pos((x + 8.0, y + 8.0))
            imgui.push_text_wrap_pos(imgui.get_cursor_pos_x() + max(1.0, rect.width - 16.0))
            try:
                imgui.text_colored(
                    GAMETHEME.colors.text_dim, message,
                    test_id="history.chart.empty_message",
                )
            finally:
                imgui.pop_text_wrap_pos()
            imgui.set_cursor_screen_pos((x, y))
            imgui.invisible_button("##history_chart_empty", (rect.width, rect.height), test_id="history.chart")
        finally:
            resume_gml_layout(token)

    def _render_analysis_popup(
        self,
        state,
        subjects: list[str],
        start: int,
        now: int,
        selected_series: list[dict[str, Any]],
    ) -> None:
        if not imgui.begin_popup("HistoryAnalytics", test_id="history.analytics.popup"):
            return
        try:
            imgui.text("Additional analysis")
            if not subjects:
                imgui.text_disabled("Additional analysis is available after history indicators are recorded.")
                return
            self._render_subject_selector(subjects)
            self._render_time_range_selector()
            self._render_granularity_selector()
            _, self._step_trend = imgui.checkbox("Step trend", self._step_trend)
            imgui.separator()
            comparison = self._render_comparison(state, subjects, start, now) if subjects else None
            self._render_ranking(state, start, now)
            timeline = self._render_timelines(state, now)
            self._render_export(selected_series, comparison, timeline)
        finally:
            imgui.end_popup()

    def _render_granularity_selector(self) -> None:
        imgui.text_disabled("Granularity")
        if imgui.begin_combo("##history_granularity", str(self._granularity_minutes or "Raw") + (" min" if self._granularity_minutes else "")):
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
        imgui.text_disabled("Compare with")
        if imgui.begin_combo("##history_compare", f"{len(self._comparison_ids)} selected"):
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

    def _history_events(self, state, start: int, end: int) -> list[dict[str, Any]]:
        if self._subject_type == "relationship" and "|" in self._subject_id:
            country_a, country_b = self._subject_id.split("|", 1)
            return [
                row for row in self._queries.relationship_timeline(state, country_a, country_b)
                if row.get("timeline_kind") == "event"
                and start <= int(row.get("game_minute") or 0) <= end
            ]
        return self._queries.event_timeline(
            state,
            subject_type=self._subject_type if self._subject_type != "country" else None,
            subject_id=self._subject_id if self._subject_type != "country" else None,
            country_ids=[self._subject_id] if self._subject_type == "country" else (),
            start_minute=start,
            end_minute=end,
        )

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

    def _draw_trend(
        self,
        records: list[dict[str, Any]],
        unit: str,
        *,
        events: list[dict[str, Any]],
        start_minute: int,
        end_minute: int,
        step: bool = False,
    ) -> None:
        session = active_gml_layout()
        component_path = "History_Window/frmInner/frmHistory/frmGraph/Container"
        component = session.layout.component(component_path) if session is not None else None
        if session is not None and component is not None:
            rect = session.rect_for(component)
            x = session.window_position[0] + rect.x
            y = session.window_position[1] + rect.y
            width, height = rect.width, rect.height
            draw = imgui.get_window_draw_list()
            draw.add_rect_filled(
                (x, y), (x + width, y + height),
                imgui.get_color_u32((0.035, 0.045, 0.055, 0.94)),
            )
            for fraction in (0.25, 0.5, 0.75):
                grid_y = y + height * fraction
                draw.add_line(
                    (x, grid_y), (x + width, grid_y),
                    imgui.get_color_u32((0.35, 0.39, 0.43, 0.24)), 1.0,
                )
            for index in range(1, 5):
                grid_x = x + width * index / 5.0
                draw.add_line(
                    (grid_x, y), (grid_x, y + height),
                    imgui.get_color_u32((0.35, 0.39, 0.43, 0.18)), 1.0,
                )
            draw.add_rect(
                (x, y), (x + width, y + height),
                imgui.get_color_u32((0.45, 0.50, 0.56, 0.55)), 1.0,
            )

            plotted_records = records[-240:]
            values = [row.get("value") for row in plotted_records]
            numeric = [float(value) for value in values if value is not None]
            plot_left, plot_top = x + 5.0, y + 5.0
            plot_width, plot_height = max(1.0, width - 10.0), max(1.0, height - 10.0)
            if numeric:
                low, high = min(numeric), max(numeric)
                span = high - low
                points: list[tuple[float, float] | None] = []
                minute_span = max(1.0, float(end_minute - start_minute))
                for index, (row, value) in enumerate(zip(plotted_records, values)):
                    try:
                        minute_fraction = (
                            float(row.get("game_minute") or 0) - float(start_minute)
                        ) / minute_span
                    except (TypeError, ValueError):
                        minute_fraction = index / max(1, len(values) - 1)
                    point_x = plot_left + plot_width * max(0.0, min(1.0, minute_fraction))
                    if value is None:
                        points.append(None)
                        draw.add_rect_filled(
                            (point_x - 2.0, plot_top + 2.0),
                            (point_x + 2.0, plot_top + plot_height - 2.0),
                            imgui.get_color_u32((0.75, 0.35, 0.2, 0.48)),
                        )
                        continue
                    normalized = 0.5 if span == 0 else (float(value) - low) / span
                    point_y = plot_top + plot_height - 4.0 - max(0.0, min(1.0, normalized)) * (plot_height - 8.0)
                    points.append((point_x, point_y))
                color = imgui.get_color_u32(GAMETHEME.colors.accent)
                for left, right in HistoryPanel._trend_segments(points, step=step):
                    draw.add_line(left, right, color, 2.0)
            else:
                draw.add_text(
                    (x + 8.0, y + 8.0), imgui.get_color_u32(GAMETHEME.colors.text_dim),
                    "No historical samples in this range.",
                )

            imgui.set_cursor_screen_pos((x, y))
            imgui.invisible_button("##history_chart", (width, height), test_id="history.chart")

            self._history_event_markers.draw(
                events,
                chart_rect=(x, y, width, height),
                start_minute=start_minute,
                end_minute=end_minute,
                parent_origin=session.window_position,
                parent_size=(float(session.layout.width), float(session.layout.height)),
            )
            return

        self._history_event_markers.hide()
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
    def _axis_value(value: float | None) -> str:
        if value is None:
            return "—"
        magnitude = abs(value)
        if magnitude >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2g}b"
        if magnitude >= 1_000_000:
            return f"{value / 1_000_000:.2g}m"
        if magnitude >= 10_000:
            return f"{value / 1_000:.2g}k"
        return f"{value:.3g}"

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
