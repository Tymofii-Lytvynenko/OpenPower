from types import SimpleNamespace

import polars as pl

from src.shared.events import EventSystemError
from src.shared.state import GameState
from src.simulation.diagnostics import SimulationDiagnostics


def test_schema_contract_handles_missing_registry_and_reports_schema_issues():
    diagnostics = SimulationDiagnostics()
    assert list(diagnostics._schema_contract(GameState())) == []

    state = GameState()
    state.bind_schema_registry(
        SimpleNamespace(
            validate_state=lambda _state: [
                SimpleNamespace(
                    code="missing_column",
                    message="Required column is absent.",
                    table="countries",
                )
            ]
        )
    )

    issues = list(diagnostics._schema_contract(state))

    assert [(issue.code, issue.message, issue.table) for issue in issues] == [
        ("schema_missing_column", "Required column is absent.", "countries")
    ]


def test_system_errors_are_reported_with_their_traceback_details():
    diagnostics = SimulationDiagnostics()
    state = GameState(
        events=[
            EventSystemError(
                system_id="combat",
                error_message="Invalid damage value",
                traceback_text="Traceback details",
            )
        ]
    )

    issues = list(diagnostics._system_errors(state))

    assert len(issues) == 1
    assert issues[0].code == "system_error"
    assert issues[0].message == "System combat failed: Invalid damage value"
    assert issues[0].details == {
        "system_id": "combat",
        "traceback": "Traceback details",
    }


def test_required_tables_distinguish_missing_and_empty_tables():
    diagnostics = SimulationDiagnostics()
    state = GameState(tables={"countries": pl.DataFrame()})

    issues = list(diagnostics._required_tables(state))

    assert {(issue.code, issue.table) for issue in issues} == {
        ("empty_table", "countries"),
        ("missing_table", "regions"),
    }


def test_player_country_reports_mismatch_and_missing_saved_country():
    diagnostics = SimulationDiagnostics()
    state = GameState(
        tables={"countries": pl.DataFrame({"id": ["USA"]})},
        globals={"player_tag": "USA"},
    )

    expected_issues = list(diagnostics._player_country(state, "CAN"))
    saved_state = GameState(
        tables={"countries": pl.DataFrame({"id": ["USA"]})},
        globals={"player_tag": "MEX"},
    )
    saved_issues = list(diagnostics._player_country(saved_state, None))
    missing_table_issues = list(
        diagnostics._player_country(GameState(globals={"player_tag": "USA"}), None)
    )

    assert [issue.code for issue in expected_issues] == [
        "player_tag_mismatch",
        "expected_player_missing",
    ]
    assert [issue.code for issue in saved_issues] == ["saved_player_missing"]
    assert missing_table_issues == []


def test_country_id_diagnostics_report_missing_and_duplicate_ids():
    diagnostics = SimulationDiagnostics()
    assert list(diagnostics._country_ids(GameState())) == []

    missing_id_state = GameState(tables={"countries": pl.DataFrame({"name": ["USA"]})})
    missing_id_issues = list(diagnostics._country_ids(missing_id_state))
    duplicate_id_state = GameState(
        tables={"countries": pl.DataFrame({"id": ["USA", "USA", "CAN"]})}
    )
    duplicate_issues = list(diagnostics._country_ids(duplicate_id_state))

    assert [issue.code for issue in missing_id_issues] == ["country_id_missing"]
    assert duplicate_issues[0].details == {"duplicates": ["USA"], "count": 1}


def test_region_references_return_cleanly_without_required_tables():
    assert list(SimulationDiagnostics()._region_references(GameState())) == []


def test_unit_references_report_unknown_owners_and_regions():
    diagnostics = SimulationDiagnostics()
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["USA"]}),
            "regions": pl.DataFrame({"id": [1]}),
            "units": pl.DataFrame({"owner": ["CAN"], "current_region_id": [9]}),
        }
    )

    issues = list(diagnostics._unit_references(state))

    assert [issue.code for issue in issues] == [
        "unknown_unit_owner",
        "unknown_unit_region_ref",
    ]
    assert issues[1].details == {"unknown": [9], "count": 1}


def test_country_number_diagnostics_report_non_finite_values():
    diagnostics = SimulationDiagnostics()
    empty_state = GameState(tables={"countries": pl.DataFrame()})
    assert list(diagnostics._finite_country_numbers(empty_state)) == []

    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {"id": ["USA"], "treasury": [float("nan")], "reserves": [float("inf")]}
            )
        }
    )

    issues = list(diagnostics._finite_country_numbers(state))

    assert {(issue.column, issue.details["count"]) for issue in issues} == {
        ("treasury", 1),
        ("reserves", 1),
    }


def test_finite_float_guard_accepts_values_that_cannot_be_compared():
    class UncomparableValue:
        def __eq__(self, other):
            raise TypeError("value does not support equality")

    assert SimulationDiagnostics()._is_finite_float(UncomparableValue()) is True
