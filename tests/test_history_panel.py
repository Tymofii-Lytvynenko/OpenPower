from __future__ import annotations

from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.service import history_panel as history_panel_module
from src.client.ui.panels.service.history_panel import HistoryPanel


def test_history_trend_supports_line_and_step_segments_without_bridging_gaps() -> None:
    points = [(0.0, 1.0), (2.0, 3.0), None, (6.0, 7.0), (8.0, 9.0)]

    line_segments = HistoryPanel._trend_segments(points)
    step_segments = HistoryPanel._trend_segments(points, step=True)

    assert line_segments == [((0.0, 1.0), (2.0, 3.0)), ((6.0, 7.0), (8.0, 9.0))]
    assert step_segments == [
        ((0.0, 1.0), (2.0, 1.0)),
        ((2.0, 1.0), (2.0, 3.0)),
        ((6.0, 7.0), (8.0, 7.0)),
        ((8.0, 7.0), (8.0, 9.0)),
    ]


def test_history_panel_comparison_includes_multiple_selected_subjects(monkeypatch) -> None:
    class QueryRecorder:
        subject_ids: list[str] = []

        def compare(self, state, subject_type, subject_ids, indicator_id, **kwargs):
            self.subject_ids = subject_ids
            return {
                "common_values": {
                    subject: {"value": index + 1, "unit": "index"}
                    for index, subject in enumerate(subject_ids)
                },
                "unit_compatible": True,
                "evaluation_minute": 120,
            }

        def export_csv(self, records):
            return ""

    class FakeImGui:
        def begin_combo(self, _label, _preview):
            return True

        def checkbox(self, label, selected):
            return (label == "MEX" and not selected, True if label == "MEX" else selected)

        def end_combo(self):
            pass

        def text(self, _value):
            pass

        def text_disabled(self, _value):
            pass

        def text_colored(self, *_args):
            pass

        def button(self, _label):
            return False

    panel = HistoryPanel()
    panel._queries = QueryRecorder()
    panel._subject_type = "country"
    panel._subject_id = "USA"
    panel._indicator_id = "country.gdp"
    monkeypatch.setattr(history_panel_module, "imgui", FakeImGui())

    panel._render_comparison(state=None, subjects=["USA", "CAN", "MEX"], start=0, end=120)

    assert panel._queries.subject_ids == ["USA", "CAN", "MEX"]


def test_history_panel_uses_indexed_values_and_shows_basis_for_mixed_units(monkeypatch) -> None:
    class QueryResult:
        def compare(self, *_args, **_kwargs):
            return {
                "common_values": {
                    "USA": {"value": 150.0, "unit": "USD/year"},
                    "CAN": {"value": 75.0, "unit": "EUR/year"},
                },
                "normalized_common_values": {
                    "USA": {
                        "value": 150.0, "unit": "index", "baseline_value": 100.0,
                        "baseline_unit": "USD/year", "baseline_minute": 0,
                    },
                    "CAN": {
                        "value": 150.0, "unit": "index", "baseline_value": 50.0,
                        "baseline_unit": "EUR/year", "baseline_minute": 0,
                    },
                },
                "normalization_basis": "Each series' first positive sample is indexed to 100.",
                "normalization_unavailable_subjects": [],
                "unit_compatible": False,
                "evaluation_minute": 60,
            }

        def export_csv(self, _records):
            return ""

    class FakeImGui:
        messages: list[str] = []

        def begin_combo(self, _label, _preview):
            return False

        def checkbox(self, _label, selected):
            return False, selected

        def text(self, message):
            self.messages.append(message)

        def text_disabled(self, message):
            self.messages.append(message)

        def button(self, _label):
            return False

    panel = HistoryPanel()
    panel._queries = QueryResult()
    panel._subject_type = "country"
    panel._subject_id = "USA"
    panel._indicator_id = "country.gdp"
    fake_imgui = FakeImGui()
    monkeypatch.setattr(history_panel_module, "imgui", fake_imgui)

    panel._render_comparison(state=None, subjects=["USA", "CAN"], start=0, end=60)

    assert panel._normalize_comparison_by_indicator["country.gdp"] is True
    assert any(message.startswith("  USA: 150.000 index") for message in fake_imgui.messages)
    assert any(message.startswith("  CAN: 150.000 index") for message in fake_imgui.messages)
    assert "  CAN: 150.000 index (base 50.000 EUR/year at minute 0)" in fake_imgui.messages
    assert "Each series' first positive sample is indexed to 100." in fake_imgui.messages
    assert "All values evaluated at minute 60." in fake_imgui.messages


def test_history_subject_selector_keeps_removed_entities_available_by_stable_id() -> None:
    state = SimpleNamespace(
        tables={
            "countries": pl.DataFrame({"id": ["USA"]}),
            "regions": pl.DataFrame({"id": [2]}),
            "countries_relations": pl.DataFrame({"source": ["USA"], "target": ["CAN"]}),
            "history_series_state": pl.DataFrame({
                "subject_type": ["country", "region", "relationship"],
                "subject_id": ["OLD", "1", "CAN|MEX"],
            }),
        },
        table_revisions={
            "countries": 1,
            "regions": 1,
            "countries_relations": 1,
            "history_series_state": 1,
        },
    )
    panel = HistoryPanel()

    assert panel._subjects(state, "country") == ["OLD", "USA"]
    assert panel._subjects(state, "region") == ["1", "2"]
    assert panel._subjects(state, "relationship") == ["CAN|MEX", "CAN|USA"]

    state.tables["history_series_state"] = pl.concat([
        state.tables["history_series_state"],
        pl.DataFrame({"subject_type": ["country"], "subject_id": ["ARCHIVED"]}),
    ])
    state.table_revisions["history_series_state"] += 1
    assert panel._subjects(state, "country") == ["ARCHIVED", "OLD", "USA"]


def test_history_ranking_exposes_direction_tie_rule_period_and_freshness(monkeypatch) -> None:
    class QueryRecorder:
        descending: bool | None = None
        time_range: tuple[int | None, int | None] | None = None

        def rank(self, _state, _indicator_id, **kwargs):
            self.descending = kwargs["descending"]
            self.time_range = (kwargs["start_minute"], kwargs["end_minute"])
            return {
                "evaluation_minute": 100,
                "rows": [{"subject_id": "USA", "value": 10, "unit": "index"}],
                "freshness_by_subject": {"USA": 20},
                "excluded": ["CAN"],
                "ties": [{"value": 10, "unit": "index", "subjects": ["USA", "MEX"]}],
            }

    class FakeImGui:
        messages: list[str] = []

        def checkbox(self, _label, _selected):
            return True, False

        def text(self, message):
            self.messages.append(message)

        def text_disabled(self, message):
            self.messages.append(message)

    panel = HistoryPanel()
    panel._queries = QueryRecorder()
    panel._subject_type = "country"
    panel._indicator_id = "country.gdp"
    fake_imgui = FakeImGui()
    monkeypatch.setattr(history_panel_module, "imgui", fake_imgui)

    panel._render_ranking(state=None, start=20, end=100)

    assert panel._queries.descending is False
    assert panel._queries.time_range == (20, 100)
    assert any("minutes 20–100 · lowest first · common boundary 100" in message for message in fake_imgui.messages)
    assert "Tie rule: subject ID ascending." in fake_imgui.messages
    assert any("20 min old" in message for message in fake_imgui.messages)


def test_history_panel_exports_selected_series_as_csv(monkeypatch) -> None:
    class FakeImGui:
        clipboard = ""

        def separator(self):
            pass

        def button(self, label):
            return label == "Copy selected series as CSV"

        def set_clipboard_text(self, value):
            self.clipboard = value

        def same_line(self):
            pass

        def text_disabled(self, _message):
            pass

    panel = HistoryPanel()
    fake_imgui = FakeImGui()
    monkeypatch.setattr(history_panel_module, "imgui", fake_imgui)
    records = [{"subject_id": "USA", "game_minute": 60, "value": 1000.0, "unit": "USD/year"}]

    panel._render_export(records, comparison=None, timeline=[])

    assert fake_imgui.clipboard.startswith("game_minute,subject_id,unit,value")
    assert "USA" in fake_imgui.clipboard
    assert panel._export_status == "Copied 1 row(s)."
