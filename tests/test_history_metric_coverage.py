import polars as pl
import pytest

from modules.base.systems.world.history_system import HistorySystem
from src.shared.state import GameState


def _state(**tables: pl.DataFrame) -> GameState:
    return GameState(tables=tables)


def test_country_budget_balance_requires_complete_numeric_country_rows() -> None:
    state = _state(
        countries=pl.DataFrame(
            {
                "id": ["USA", "", "CAN", "MEX"],
                "total_annual_revenue": ["100", "100", "invalid", None],
                "total_annual_expense": ["40", "40", "50", "10"],
            }
        )
    )
    system = HistorySystem()

    assert system._country_budget_balance(state) == (
        {"USA": 60.0},
        {"USA": "derived"},
    )
    assert system._country_budget_balance(
        _state(countries=pl.DataFrame({"id": ["USA"]}))
    ) == ({}, {})


def test_overall_relations_handles_missing_empty_and_single_country_inputs() -> None:
    system = HistorySystem()
    relation_schema = pl.DataFrame(
        schema={"source": pl.String, "target": pl.String, "value": pl.Float64}
    )

    assert system._country_overall_relations(
        _state(countries=pl.DataFrame({"id": ["USA"]}))
    ) == ({}, {})
    assert system._country_overall_relations(
        _state(
            countries=pl.DataFrame({"name": ["USA"]}),
            countries_relations=relation_schema,
        )
    ) == ({}, {})
    assert system._country_overall_relations(
        _state(
            countries=pl.DataFrame({"id": ["USA", "CAN"]}),
            countries_relations=pl.DataFrame({"source": ["USA"]}),
        )
    ) == ({}, {})
    assert system._country_overall_relations(
        _state(
            countries=pl.DataFrame({"id": [None]}),
            countries_relations=relation_schema,
        )
    ) == ({}, {})
    assert system._country_overall_relations(
        _state(
            countries=pl.DataFrame({"id": ["USA"]}),
            countries_relations=relation_schema,
        )
    ) == ({"USA": 100.0}, {"USA": "derived"})


def test_overall_relations_ignores_unknown_and_self_pairs() -> None:
    state = _state(
        countries=pl.DataFrame({"id": ["USA", "CAN"]}),
        countries_relations=pl.DataFrame(
            {
                "source": ["USA", "CAN", "MEX", "USA"],
                "target": ["CAN", "USA", "USA", "USA"],
                "value": [10.0, 20.0, 999.0, 999.0],
            }
        ),
    )

    assert HistorySystem()._country_overall_relations(state) == (
        {"CAN": 20.0, "USA": 10.0},
        {"CAN": "derived", "USA": "derived"},
    )


@pytest.mark.parametrize(
    "rows",
    [
        [
            {"source": "USA", "target": "CAN", "value": 10.0},
            {"source": "USA", "target": "CAN", "value": 11.0},
            {"source": "CAN", "target": "USA", "value": 12.0},
        ],
        [
            {"source": "USA", "target": "CAN", "value": 10.0},
            {"source": "CAN", "target": "USA", "value": None},
        ],
        [
            {"source": "USA", "target": "CAN", "value": "invalid"},
            {"source": "CAN", "target": "USA", "value": "12"},
        ],
        [
            {"source": "USA", "target": "CAN", "value": float("inf")},
            {"source": "CAN", "target": "USA", "value": 12.0},
        ],
    ],
    ids=["duplicate-pair", "missing-value", "non-numeric-value", "non-finite-value"],
)
def test_overall_relations_rejects_ambiguous_or_invalid_pairs(rows) -> None:
    state = _state(
        countries=pl.DataFrame({"id": ["USA", "CAN"]}),
        countries_relations=pl.DataFrame(rows),
    )

    assert HistorySystem()._country_overall_relations(state) == ({}, {})


def test_gdp_per_capita_requires_owner_population_and_finite_gdp() -> None:
    system = HistorySystem()
    assert system._gdp_per_capita(_state()) == ({}, {})
    assert system._gdp_per_capita(
        _state(
            countries=pl.DataFrame({"id": ["USA"], "gdp": [100.0]}),
            regions=pl.DataFrame({"owner": ["USA"], "name": ["North"]}),
        )
    ) == ({}, {})

    state = _state(
        countries=pl.DataFrame(
            {"id": ["USA", "CAN"], "gdp": ["invalid", "100"]}
        ),
        regions=pl.DataFrame(
            {"owner": ["", "CAN"], "pop_14": [10, 20]}
        ),
    )
    assert system._gdp_per_capita(state) == (
        {"CAN": 5.0},
        {"CAN": "derived"},
    )


def test_country_population_requires_owner_and_population_fields() -> None:
    system = HistorySystem()
    assert system._country_population(
        _state(regions=pl.DataFrame({"owner_tag": ["USA"], "pop_14": [10]}))
    ) == ({}, {})
    assert system._country_population(
        _state(regions=pl.DataFrame({"owner": ["USA"], "name": ["North"]}))
    ) == ({}, {})


def test_resource_metrics_skip_missing_contracts_and_blank_countries() -> None:
    system = HistorySystem()
    assert system._resource_coverage(
        _state(resource_ledger=pl.DataFrame({"country_id": ["USA"]}))
    ) == ({}, {})
    assert system._resource_coverage(
        _state(
            resource_ledger=pl.DataFrame(
                {
                    "country_id": ["", "USA"],
                    "consumption_usd": [100.0, 100.0],
                    "balance_usd": [-100.0, -20.0],
                }
            )
        )
    ) == ({"USA": 0.8}, {"USA": "derived"})


def test_country_resource_balance_skips_blank_and_non_finite_rows() -> None:
    system = HistorySystem()
    assert system._country_resource_balance(
        _state(resource_ledger=pl.DataFrame({"country_id": ["USA"]}))
    ) == ({}, {})
    assert system._country_resource_balance(
        _state(
            resource_ledger=pl.DataFrame(
                {"country_id": ["", "USA", "CAN"], "balance_usd": [5.0, float("inf"), 4.0]}
            )
        )
    ) == ({"CAN": 4.0}, {"CAN": "derived"})


def test_conventional_force_rollup_rejects_incomplete_rows() -> None:
    system = HistorySystem()
    definition = {"subject_id_field": "country_id"}
    assert system._country_conventional_forces(
        _state(units=pl.DataFrame({"country_id": ["USA"]})), definition
    ) == ({}, {})

    state = _state(
        units=pl.DataFrame(
            {
                "country_id": ["", "USA", "USA", "CAN"],
                "unit_type": ["infantry", "infantry", "infantry", "infantry"],
                "strength": ["1", "invalid", "nan", "5"],
            }
        )
    )
    assert system._country_conventional_forces(state, definition) == (
        {"CAN": 5.0},
        {"CAN": "derived"},
    )


def test_treaty_membership_parses_json_and_ignores_malformed_members() -> None:
    system = HistorySystem()
    assert system._treaty_membership_count(
        _state(countries_treaties=pl.DataFrame({"status": ["active"]}))
    ) == ({}, {})

    state = _state(
        countries_treaties=pl.DataFrame(
            {
                "status": ["active", "active"],
                "members": ['["USA", "CAN"]', "not-json"],
            }
        )
    )
    assert system._treaty_membership_count(state) == (
        {"USA": 1.0, "CAN": 1.0},
        {"USA": "derived", "CAN": "derived"},
    )


def test_active_war_count_parses_json_and_falls_back_for_plain_text_sides() -> None:
    system = HistorySystem()
    assert system._active_war_count(
        _state(countries_wars=pl.DataFrame({"side_a": ["USA"]}))
    ) == ({}, {})

    state = _state(
        countries_wars=pl.DataFrame(
            {
                "status": ["active", "concluded"],
                "side_a": ['["USA", "CAN"]', '["MEX"]'],
                "side_b": ["MEX", "USA"],
            }
        )
    )
    assert system._active_war_count(state) == (
        {"USA": 1.0, "CAN": 1.0, "MEX": 1.0},
        {"USA": "derived", "CAN": "derived", "MEX": "derived"},
    )


def test_ruling_party_support_requires_the_expected_party_columns() -> None:
    assert HistorySystem()._ruling_party_support(
        _state(political_parties=pl.DataFrame({"country_id": ["USA"]}))
    ) == ({}, {})
