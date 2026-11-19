from __future__ import annotations

import json
from unittest.mock import patch

import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.world.history_system import (
    HistoryStartSeedSystem,
    HistorySystem,
)
from src.client.services.history_query_service import HistoryQueryService
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.config import GameConfig
from src.shared.events import (
    EventBattleEnded,
    EventOccupationChanged,
    EventTreatyLifecycleChanged,
    EventWarEnded,
    EventWarStarted,
)
from src.shared.state import GameState
from src.shared.system_interfaces import SystemPhase


def _state() -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame({
                "id": ["USA", "CAN"], "gdp": [1000.0, 400.0], "human_dev": [0.9, 0.8],
                "money_reserves": [100.0, 80.0], "economic_health": [0.8, 0.9],
                "gvt_corruption": [0.3, 0.4],
                "total_annual_revenue": [1000.0, 500.0],
                "total_annual_expense": [650.0, 510.0],
                "expense_military_upkeep": [230.0, 90.0],
            }),
            "regions": pl.DataFrame({
                "id": [1, 2, 3], "owner": ["USA", "USA", "CAN"],
                "pop_14": [10, 10, 5], "pop_15_64": [60, 40, 35], "pop_65": [10, 10, 10],
            }),
            "countries_relations": pl.DataFrame({
                "source": ["USA"], "target": ["CAN"], "value": [25.0],
            }),
            "countries_treaties": pl.DataFrame({
                "id": ["treaty-1"], "members": [["USA", "CAN"]], "status": ["active"],
            }),
            "countries_wars": pl.DataFrame({
                "id": ["war-1"], "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["active"],
            }),
            "units": pl.DataFrame({
                "id": ["u1", "u2"], "country_id": ["USA", "USA"],
                "unit_type": ["infantry", "strategic_missile"], "strength": [12.0, 8.0],
            }),
            "strategic_weapons": pl.DataFrame({
                "id": ["w1"], "country_id": ["USA"], "quantity": [3],
            }),
            "research_tracks": pl.DataFrame({
                "id": ["usa-research"], "country_id": ["USA"], "research_level": [3], "progress": [0.5],
            }),
            "country_governments": pl.DataFrame({
                "country_id": ["USA"], "ruling_party_id": ["party-a"], "election_risk": [0.2],
                "ideology_balance": [0.6],
            }),
            "political_parties": pl.DataFrame({
                "country_id": ["USA"], "party_id": ["party-a"], "support_share": [0.6], "is_ruling": [True],
            }),
            "resource_ledger": pl.DataFrame({
                "country_id": ["USA", "USA", "CAN"], "consumption_usd": [100.0, 0.0, 100.0],
                "game_resource_id": ["food", "fuel", "food"],
                "balance_usd": [80.0, -20.0, 100.0],
            }),
            "economic_cause_records": pl.DataFrame({
                "id": ["cause-1"], "country_id": ["USA"], "indicator": ["gdp"],
                "source_type": ["policy"], "source_id": ["tax-reform"], "previous_value": [900.0],
                "new_value": [1000.0], "delta": [100.0], "unit": ["USD"], "game_minute": [0],
                "reason": ["reform"], "confidence": [1.0], "completeness": ["complete"],
            }),
        }
    )
    registry = build_base_schema_registry()
    registry.capture_state(state)
    registry.ensure_state(state)
    state.globals["tick"] = 1
    return state


def _rows(state: GameState, table: str) -> list[dict]:
    return state.tables[table].to_dicts()


def test_history_records_authoritative_and_derived_metrics_without_changing_sources() -> None:
    state = _state()
    original_gdp = state.tables["countries"]["gdp"].to_list()
    HistorySystem().update(state, 0.0)

    snapshots = _rows(state, "history_snapshots")
    values = {(row["indicator_id"], row["subject_id"]): row["value"] for row in snapshots}
    assert values[("country.gdp", "USA")] == 1000.0
    assert values[("country.gdp_per_capita", "USA")] == 1000.0 / 140.0
    assert values[("region.population", "1")] == 80.0
    assert values[("military.unit_count", "USA")] == 2.0
    assert values[("military.total_strength", "USA")] == 20.0
    assert values[("military.conventional_strength", "USA")] == 12.0
    assert values[("strategic.weapon_quantity", "USA")] == 3.0
    assert values[("relationship.relation_value", "CAN|USA")] == 25.0
    assert values[("country.population", "USA")] == 140.0
    assert values[("politics.gvt_corruption", "USA")] == 0.3
    assert values[("country.budget_balance", "USA")] == 350.0
    assert values[("country.expense_military_upkeep", "USA")] == 230.0
    assert values[("country.resource_balance", "USA")] == 60.0
    assert values[("country.resource_coverage", "USA")] == 0.8
    assert values[("diplomacy.active_treaties", "USA")] == 1.0
    assert values[("military.active_wars", "USA")] == 1.0
    assert values[("research.total_level", "USA")] == 3.0
    assert values[("politics.ruling_party_support", "USA")] == 0.6
    assert state.tables["countries"]["gdp"].to_list() == original_gdp
    assert {row["id"] for row in _rows(state, "history_indicator_definitions")} >= {
        "country.gdp", "country.gdp_per_capita", "region.population", "military.unit_count",
        "politics.gvt_corruption", "country.budget_balance", "country.expense_military_upkeep",
        "country.resource_balance",
    }


def test_new_game_population_baseline_is_one_provenanced_minute_zero_point() -> None:
    state = _state()
    state.update_table(
        "regions",
        state.tables["regions"].with_columns(
            pl.Series("hex", ["#REGION-1", "#REGION-2", "#REGION-3"])
        ),
    )
    state.globals["history_start_seed_pending"] = True
    seed_system = HistoryStartSeedSystem()

    assert seed_system.access.phase == SystemPhase.STARTUP
    assert seed_system.access.phase < SystemPhase.CLOCK
    seed_system.update(state, 0.0)

    allowed_indicators = {
        "region.pop_14",
        "region.pop_15_64",
        "region.pop_65",
        "region.population",
        "country.population",
    }
    snapshots = [
        row for row in _rows(state, "history_snapshots")
        if row["indicator_id"] in allowed_indicators
    ]
    assert len(snapshots) == 14
    assert all(row["game_minute"] == 0 and row["source_boundary"] == "initial" for row in snapshots)
    assert all(row["source_reference"] for row in snapshots)
    assert all(
        "regional_population_provenance.tsv" in row["source_reference"]
        for row in snapshots
    )
    region_source = next(row["source_reference"] for row in snapshots if row["indicator_id"] == "region.pop_14")
    assert "#hex=#REGION-1" in region_source
    country_source = next(row["source_reference"] for row in snapshots if row["indicator_id"] == "country.population")
    assert "by owner" in country_source
    assert not any(row["indicator_id"] in {"country.gdp", "country.human_dev"} for row in snapshots)

    counts = {}
    for row in snapshots:
        key = (row["subject_type"], row["subject_id"], row["indicator_id"])
        counts[key] = counts.get(key, 0) + 1
    assert set(counts.values()) == {1}

    service = HistoryQueryService()
    series = service.series(state, "region", "1", "region.pop_15_64")
    assert len(series) == 1
    assert series[0]["value"] == 60.0
    assert "#hex=#REGION-1" in series[0]["source_reference"]
    assert "source_reference" in service.export_csv(series).splitlines()[0]

    initial_count = state.tables["history_snapshots"].height
    seed_system.update(state, 0.0)
    HistorySystem().update(state, 0.0)
    repeated_series = service.series(state, "region", "1", "region.pop_15_64")
    repeated_population_snapshots = [
        row for row in _rows(state, "history_snapshots")
        if row["indicator_id"] in allowed_indicators
    ]
    assert len(repeated_series) == 1
    assert state.tables["history_snapshots"].height >= initial_count
    assert len(repeated_population_snapshots) == 14
    assert state.globals["history_start_seed_pending"] is False


def test_new_game_seeds_source_backed_country_baselines_without_turning_missing_into_zero() -> None:
    state = _state()
    countries = state.tables["countries"].with_columns(
        pl.Series("birth_rate", [0.0, 12.5]),
        pl.Series("birth_rate_available", [True, False]),
        pl.Series("reference_human_dev", [0.75, 0.5]),
        pl.Series("reference_human_dev_available", [True, False]),
        pl.Series("reference_human_dev_status", ["official_undp_hdr2025", "not_reported"]),
        pl.Series("historical_metric_provenance_json", [
            json.dumps({
                "birth_rate": {
                    "year": 2001, "observation_year": 2001, "source": "World Bank WDI",
                    "source_note": "Dated observation.", "url": "https://data.worldbank.org/indicator/SP.DYN.CBRT.IN",
                },
                "reference_human_dev": {
                    "year": 2001, "observation_year": 2001, "source": "UNDP HDR 2025",
                    "source_note": "Retrospective series.", "url": "https://hdr.undp.org/",
                    "reference_human_dev_status": "official_undp_hdr2025",
                },
            }),
            json.dumps({}),
        ]),
    )
    state.update_table("countries", countries)
    state.update_table(
        "regions",
        state.tables["regions"].with_columns(
            pl.Series("hex", ["#REGION-1", "#REGION-2", "#REGION-3"])
        ),
    )
    state.globals["history_start_seed_pending"] = True

    HistoryStartSeedSystem().update(state, 0.0)

    baselines = [
        row for row in _rows(state, "history_snapshots")
        if row["indicator_id"] in {
            "country.baseline_2001.birth_rate", "country.baseline_2001.human_development",
        }
    ]
    assert {(row["indicator_id"], row["subject_id"], row["value"]) for row in baselines} == {
        ("country.baseline_2001.birth_rate", "USA", 0.0),
        ("country.baseline_2001.birth_rate", "CAN", None),
        ("country.baseline_2001.human_development", "USA", 0.75),
        ("country.baseline_2001.human_development", "CAN", None),
    }
    assert all(row["game_minute"] == 0 and row["source_boundary"] == "initial" for row in baselines)
    birth_rate = next(
        row for row in baselines
        if row["indicator_id"].endswith("birth_rate") and row["subject_id"] == "USA"
    )
    assert birth_rate["value_kind"] == "historical_observation"
    assert "observation year=2001" in birth_rate["source_reference"]
    assert "https://data.worldbank.org/indicator/SP.DYN.CBRT.IN" in birth_rate["source_reference"]
    hdi = next(
        row for row in baselines
        if row["indicator_id"].endswith("human_development") and row["subject_id"] == "USA"
    )
    assert hdi["value_kind"] == "historical_observation"
    assert "UNDP HDR 2025" in hdi["source_reference"]

    query = HistoryQueryService()
    series = query.series(state, "country", "USA", "country.baseline_2001.birth_rate")
    assert len(series) == 1 and series[0]["value"] == 0.0
    assert "source_reference" in query.export_csv(series).splitlines()[0]
    unavailable = query.series(state, "country", "CAN", "country.baseline_2001.birth_rate")
    assert len(unavailable) == 1
    assert unavailable[0]["value"] is None and unavailable[0]["completeness"] == "missing"
    assert "birth_rate_available=False" in unavailable[0]["source_reference"]


def test_legacy_save_does_not_backfill_static_historical_baselines() -> None:
    state = _state()
    state.update_table("countries", state.tables["countries"].with_columns(
        pl.Series("birth_rate", [12.0, 15.0]),
        pl.Series("birth_rate_available", [True, True]),
        pl.Series("historical_metric_provenance_json", [
            json.dumps({"birth_rate": {
                "year": 2001, "observation_year": 2001, "source": "World Bank WDI",
                "url": "https://data.worldbank.org/indicator/SP.DYN.CBRT.IN",
            }}),
            json.dumps({"birth_rate": {
                "year": 2001, "observation_year": 2001, "source": "World Bank WDI",
                "url": "https://data.worldbank.org/indicator/SP.DYN.CBRT.IN",
            }}),
        ]),
    ))

    HistorySystem().update(state, 0.0)

    assert not any(
        row["indicator_id"] == "country.baseline_2001.birth_rate"
        for row in _rows(state, "history_snapshots")
    )


def test_country_historical_baselines_do_not_depend_on_regional_population_rows() -> None:
    state = _state()
    countries = state.tables["countries"].with_columns(
        pl.Series("birth_rate", [12.0, 15.0]),
        pl.Series("birth_rate_available", [True, True]),
        pl.Series("historical_metric_provenance_json", [
            json.dumps({"birth_rate": {
                "year": 2001, "observation_year": 2001, "source": "World Bank WDI",
                "url": "https://data.worldbank.org/indicator/SP.DYN.CBRT.IN",
            }}),
            json.dumps({"birth_rate": {
                "year": 2001, "observation_year": 2001, "source": "World Bank WDI",
                "url": "https://data.worldbank.org/indicator/SP.DYN.CBRT.IN",
            }}),
        ]),
    )
    state.update_table("countries", countries)
    empty_regions = state.tables["regions"].head(0).with_columns(
        pl.Series("hex", [], dtype=pl.Utf8)
    )
    state.update_table("regions", empty_regions)
    state.globals["history_start_seed_pending"] = True

    HistoryStartSeedSystem().update(state, 0.0)

    rows = [
        row for row in _rows(state, "history_snapshots")
        if row["indicator_id"] == "country.baseline_2001.birth_rate"
    ]
    assert {row["subject_id"] for row in rows} == {"USA", "CAN"}
    assert not any(row["indicator_id"] == "country.population" for row in _rows(state, "history_snapshots"))


def test_historical_baseline_quality_tags_follow_source_method_and_status() -> None:
    classify = HistoryStartSeedSystem._historical_value_kind

    assert classify("other_land_pct", {"other_land_source_flag": "I"}) == "historical_imputed"
    assert classify("reference_human_dev", {"reference_human_dev_status": "regional_estimate_proxy"}) == "historical_proxy"
    assert classify("historical_poverty_rate_pct", {"source": "CIA Factbook 2001"}) == "historical_estimate"
    assert classify("reference_water_area_km2", {"source": "WDI surface area minus land area"}) == "historical_derived"
    assert classify("national_park_land_area_km2_2001", {"national_park_status": "bounded_zero_inference"}) == "historical_inference"
    assert classify("terrestrial_protected_area_pct_2000", {
        "source_note": "The Maldives value is derived as zero from the official register.",
    }) == "historical_inference"


def test_start_seed_does_not_backfill_existing_or_advanced_games() -> None:
    old_save = _state()
    old_save.update_table(
        "regions",
        old_save.tables["regions"].with_columns(
            pl.Series("hex", ["#REGION-1", "#REGION-2", "#REGION-3"])
        ),
    )
    HistoryStartSeedSystem().update(old_save, 0.0)
    assert old_save.tables["history_snapshots"].is_empty()

    state = _state()
    state.update_table(
        "regions",
        state.tables["regions"].with_columns(
            pl.Series("hex", ["#REGION-1", "#REGION-2", "#REGION-3"])
        ),
    )
    state.time.total_minutes = 60
    state.globals["history_start_seed_pending"] = True

    HistoryStartSeedSystem().update(state, 0.0)

    assert state.tables["history_snapshots"].is_empty()
    assert state.tables["history_series_state"].is_empty()
    assert state.globals["history_start_seed_pending"] is False


def test_source_backed_history_measures_refresh_when_budget_or_resource_inputs_change() -> None:
    state = _state()
    system = HistorySystem()
    system.update(state, 0.0)

    state.update_table(
        "countries",
        state.tables["countries"].with_columns(
            pl.when(pl.col("id") == "USA")
            .then(310.0)
            .otherwise(pl.col("expense_military_upkeep"))
            .alias("expense_military_upkeep")
        ),
    )
    state.update_table(
        "resource_ledger",
        state.tables["resource_ledger"].with_columns(
            pl.when(pl.col("country_id") == "USA")
            .then(pl.col("balance_usd") + 10.0)
            .otherwise(pl.col("balance_usd"))
            .alias("balance_usd")
        ),
    )
    state.globals["tick"] = 2
    system.update(state, 0.0)

    latest = {
        (row["indicator_id"], row["subject_id"]): row["value"]
        for row in _rows(state, "history_snapshots")
        if row["indicator_id"] in {"country.expense_military_upkeep", "country.resource_balance"}
    }
    assert latest[("country.expense_military_upkeep", "USA")] == 310.0
    assert latest[("country.resource_balance", "USA")] == 80.0


def test_country_resource_balance_does_not_hide_incomplete_resource_rows() -> None:
    state = _state()
    state.tables["resource_ledger"] = pl.DataFrame({
        "country_id": ["USA", "USA", "CAN"],
        "balance_usd": [80.0, None, 100.0],
    })

    values, kinds = HistorySystem()._measure_definition(state, {
        "derivation": "resource_balance",
        "source_table": "resource_ledger",
    })

    assert values == {"CAN": 100.0}
    assert kinds == {"CAN": "derived"}


def test_conventional_force_rollup_excludes_strategic_units_and_rejects_unknown_types() -> None:
    state = _state()
    definition = {
        "derivation": "conventional_forces",
        "source_table": "units",
        "subject_id_field": "country_id",
    }
    values, kinds = HistorySystem()._measure_definition(state, definition)
    assert values == {"USA": 12.0}
    assert kinds == {"USA": "derived"}

    strategic_only = state.tables["units"].filter(pl.col("unit_type") == "strategic_missile")
    state.update_table("units", strategic_only)
    assert HistorySystem()._measure_definition(state, definition) == (
        {"USA": 0.0}, {"USA": "derived"},
    )

    state.update_table(
        "units",
        state.tables["units"].with_columns(pl.lit(None, dtype=pl.Utf8).alias("unit_type")),
    )
    assert HistorySystem()._measure_definition(state, definition) == ({}, {})


def test_generic_history_measurements_preserve_aggregations_filters_and_relationships() -> None:
    state = _state()
    state.tables["measurement_fixture"] = pl.DataFrame({
        "subject": ["USA", "USA", "USA", "CAN", "USA"],
        "related": ["CAN", "CAN", "CAN", "MEX", "MEX"],
        "value": [1.5, 3.5, None, 5.0, 100.0],
        "include": ["yes", "yes", "yes", "yes", "no"],
    })
    definition = {
        "source_table": "measurement_fixture",
        "source_field": "value",
        "subject_id_field": "subject",
        "related_id_field": "related",
        "filter_field": "include",
        "filter_value": "yes",
        "subject_type": "country",
    }
    expected = {
        "sum": {"USA": 5.0, "CAN": 5.0},
        "mean": {"USA": 2.5, "CAN": 5.0},
        "max": {"USA": 3.5, "CAN": 5.0},
        "last": {"USA": 3.5, "CAN": 5.0},
        "count": {"USA": 3.0, "CAN": 1.0},
    }

    system = HistorySystem()
    for aggregation, values_expected in expected.items():
        values, _ = system._measure_definition(state, {**definition, "aggregation": aggregation})
        assert values == values_expected

    relationship_values, _ = system._measure_definition(
        state,
        {**definition, "aggregation": "sum", "subject_type": "relationship"},
    )
    assert relationship_values == {"CAN|USA": 5.0, "CAN|MEX": 5.0}


def test_overall_relations_matches_source_average_and_requires_complete_directed_matrix() -> None:
    state = _state()
    state.tables["countries"] = pl.DataFrame({"id": ["USA", "CAN", "MEX"]})
    state.tables["countries_relations"] = pl.DataFrame({
        "source": ["USA", "USA", "CAN", "CAN", "MEX", "MEX"],
        "target": ["CAN", "MEX", "USA", "MEX", "USA", "CAN"],
        "value": [10.0, 30.0, -10.0, 40.0, -30.0, 20.0],
    })

    values, kinds = HistorySystem()._measure_definition(state, {
        "derivation": "overall_relations",
        "source_table": "countries_relations",
    })

    assert values == {"CAN": 15.0, "MEX": -5.0, "USA": 20.0}
    assert kinds == {country: "derived" for country in values}

    state.tables["countries_relations"] = state.tables["countries_relations"].filter(
        ~((pl.col("source") == "USA") & (pl.col("target") == "MEX"))
    )
    assert HistorySystem()._measure_definition(state, {
        "derivation": "overall_relations",
        "source_table": "countries_relations",
    }) == ({}, {})


def test_overall_relations_records_initial_and_changed_matrix_values() -> None:
    state = _state()
    state.update_table("countries_relations", pl.DataFrame({
        "source": ["USA", "CAN"],
        "target": ["CAN", "USA"],
        "value": [25.0, -10.0],
    }))
    system = HistorySystem()
    system.update(state, 0.0)

    updated = state.tables["countries_relations"].with_columns(
        pl.when(pl.col("source") == "USA").then(40.0).otherwise(pl.col("value")).alias("value")
    )
    state.update_table("countries_relations", updated)
    state.globals["tick"] = 2
    system.update(state, 0.0)

    snapshots = [
        row for row in _rows(state, "history_snapshots")
        if row["indicator_id"] == "country.overall_relations"
    ]
    values_by_subject = {
        subject: [row["value"] for row in snapshots if row["subject_id"] == subject]
        for subject in ("USA", "CAN")
    }
    assert values_by_subject == {"USA": [25.0, 40.0], "CAN": [-10.0]}


def test_observation_defaults_are_built_once_and_compaction_waits_for_thresholds() -> None:
    state = _state()
    original_defaults = HistorySystem._row_defaults
    with (
        patch.object(HistorySystem, "_row_defaults", side_effect=original_defaults) as defaults,
        patch.object(HistorySystem, "_compact_group", side_effect=AssertionError("compaction is not due")),
    ):
        HistorySystem().update(state, 0.0)
        tables = [call.args[1] for call in defaults.call_args_list]
        assert tables.count("history_snapshots") == 1
        assert tables.count("history_series_state") == 1
        assert state.tables["history_snapshots"].height > 20


def test_history_aggregates_units_by_the_production_owner_field() -> None:
    state = _state()
    state.tables["units"] = pl.DataFrame({
        "id": ["u1", "u2", "u3"],
        "owner": ["USA", "USA", "CAN"],
        "strength": [12, 8, 4],
    })

    HistorySystem().update(state, 0.0)

    definitions = {row["id"]: row for row in _rows(state, "history_indicator_definitions")}
    snapshots = {
        (row["indicator_id"], row["subject_id"]): row["value"]
        for row in _rows(state, "history_snapshots")
    }
    assert definitions["military.unit_count"]["subject_id_field"] == "owner"
    assert definitions["military.total_strength"]["subject_id_field"] == "owner"
    assert snapshots[("military.unit_count", "USA")] == 2.0
    assert snapshots[("military.unit_count", "CAN")] == 1.0
    assert snapshots[("military.total_strength", "USA")] == 20.0
    assert snapshots[("military.total_strength", "CAN")] == 4.0


def test_history_records_only_changed_or_due_values_and_marks_missing_data() -> None:
    state = _state()
    system = HistorySystem()
    system.update(state, 0.0)
    initial_count = state.tables["history_snapshots"].height

    state.globals["tick"] = 2
    system.update(state, 0.0)
    assert state.tables["history_snapshots"].height == initial_count

    countries = state.tables["countries"].with_columns(
        pl.when(pl.col("id") == "USA").then(1100.0).otherwise(pl.col("gdp")).alias("gdp")
    )
    state.update_table("countries", countries)
    state.globals["tick"] = 3
    system.update(state, 0.0)
    gdp_rows = [row for row in _rows(state, "history_snapshots") if row["indicator_id"] == "country.gdp"]
    assert [(row["value"], row["source_boundary"]) for row in gdp_rows if row["subject_id"] == "USA"] == [
        (1000.0, "initial"), (1100.0, "change"),
    ]
    assert len(gdp_rows) == 3

    countries = state.tables["countries"].with_columns(
        pl.when(pl.col("id") == "USA")
        .then(1200.0)
        .otherwise(pl.col("total_annual_revenue"))
        .alias("total_annual_revenue")
    )
    state.update_table("countries", countries)
    state.globals["tick"] = 4
    system.update(state, 0.0)
    budget_rows = [
        row for row in _rows(state, "history_snapshots")
        if row["indicator_id"] == "country.budget_balance" and row["subject_id"] == "USA"
    ]
    assert [(row["value"], row["source_boundary"]) for row in budget_rows] == [
        (350.0, "initial"), (550.0, "change"),
    ]

    definition_table = state.tables["history_indicator_definitions"]
    definitions = definition_table.to_dicts()
    gdp_definition = next(row for row in definitions if row["id"] == "country.gdp")
    gdp_definition["sample_interval_minutes"] = 60
    state.update_table("history_indicator_definitions", pl.DataFrame(definitions, schema=definition_table.schema))
    state.time.total_minutes = 60
    state.tables["regions"] = state.tables["regions"].filter(pl.col("id") != 1)
    state.update_table("regions", state.tables["regions"])
    state.globals["tick"] = 5
    system.update(state, 0.0)
    population_rows = [row for row in _rows(state, "history_snapshots") if row["indicator_id"] == "region.population" and row["subject_id"] == "1"]
    assert population_rows[-1]["value"] is None
    assert population_rows[-1]["completeness"] == "missing"


def test_history_journal_and_economic_cause_events_are_persisted_once() -> None:
    state = _state()
    state.journal.append_domain_event(
        EventWarStarted("war-1", "USA", "CAN"), event_id="event-1", tick=8, source="simulation"
    )
    system = HistorySystem()
    system.update(state, 0.0)
    system.update(state, 0.0)

    events = _rows(state, "history_events")
    assert len(events) == 2
    war = next(row for row in events if row["id"] == "journal:event-1")
    assert war["subject_type"] == "country"
    assert war["subject_id"] == "USA"
    assert json.loads(war["related_country_ids_json"]) == ["CAN", "USA"]
    cause = next(row for row in events if row["id"] == "economic-cause:cause-1")
    assert cause["cause_source_type"] == "policy"
    assert cause["cause_source_id"] == "tax-reform"


def test_history_relationship_timeline_includes_war_treaty_occupation_and_losses() -> None:
    state = _state()
    records = (
        EventWarEnded("war-1", "USA", "CAN", ("USA", "CAN"), "peace", 1440),
        EventTreatyLifecycleChanged("treaty-1", "trade_embargo", "activated", ("USA", "CAN"), 1500),
        EventOccupationChanged(1, "CAN", "USA", "battle_resolution", 1550),
        EventBattleEnded("battle-1", "USA", "SIDE_A", 1, 1600, 12, 7, ("USA", "CAN")),
    )
    for index, event in enumerate(records):
        state.journal.append_domain_event(
            event, event_id=f"timeline-{index}", tick=index + 1, source="simulation",
            game_minute=1440 + index * 60,
        )
    HistorySystem().update(state, 0.0)

    timeline = HistoryQueryService().relationship_timeline(state, "USA", "CAN")
    relation_samples = [row for row in timeline if row.get("timeline_kind") == "relation_value"]
    assert len(relation_samples) == 1
    assert relation_samples[0]["value"] == 25.0
    types = {row.get("event_type") for row in timeline if row.get("timeline_kind") == "event"}
    assert {"EventWarEnded", "EventTreatyLifecycleChanged", "EventOccupationChanged", "EventBattleEnded"} <= types
    battle = next(row for row in timeline if row.get("event_type") == "EventBattleEnded")
    details = json.loads(battle["details_json"])
    assert details["side_a_losses"] == 12 and details["side_b_losses"] == 7


def test_history_queries_are_deterministic_and_expose_missing_units_and_ties() -> None:
    state = _state()
    system = HistorySystem()
    system.update(state, 0.0)
    snapshots = state.tables["history_snapshots"]
    row = snapshots.row(0, named=True)
    additions = [
        {**row, "id": "extra-can-gdp", "subject_id": "CAN", "indicator_id": "country.gdp", "value": 1000.0},
        {**row, "id": "extra-usa-gdp", "subject_id": "USA", "indicator_id": "country.gdp", "value": 1000.0},
        {**row, "id": "extra-unsupported", "subject_id": "MEX", "indicator_id": "country.gdp", "value": None,
         "completeness": "missing", "game_minute": 10},
    ]
    for extra in additions:
        extra.update({"subject_type": "country", "unit": "USD/year", "game_minute": 5, "tick": 99})
    additions[-1]["game_minute"] = 10
    state.update_table("history_snapshots", pl.concat([snapshots, pl.DataFrame(additions, schema=snapshots.schema)]))

    queries = HistoryQueryService()
    ranking = queries.rank(state, "country.gdp", end_minute=10)
    assert [row["subject_id"] for row in ranking["rows"]] == ["CAN", "USA"]
    assert ranking["ties"][0]["subjects"] == ["CAN", "USA"]
    assert ranking["excluded"] == ["MEX"]
    comparison = queries.compare(state, "country", ["USA", "CAN", "MEX"], "country.gdp", end_minute=10)
    assert comparison["unit_compatible"] is True
    assert comparison["unavailable_subjects"] == ["MEX"]
    assert comparison["evaluation_minute"] == 5
    assert comparison["common_values"]["CAN"]["value"] == 1000.0
    assert comparison["common_unavailable_subjects"] == ["MEX"]
    csv_text = queries.export_csv(ranking["rows"])
    assert "subject_id" in csv_text and "USA" in csv_text


def test_history_comparison_indexes_different_units_from_each_first_positive_sample() -> None:
    state = _state()
    HistorySystem().update(state, 0.0)
    table = state.tables["history_snapshots"]
    template = table.filter(pl.col("indicator_id") == "country.gdp").row(0, named=True)
    samples = []
    for identifier, subject, minute, value, unit in (
        ("usa-base", "USA", 0, 100.0, "USD/year"),
        ("usa-latest", "USA", 60, 150.0, "USD/year"),
        ("can-base", "CAN", 0, 50.0, "EUR/year"),
        ("can-latest", "CAN", 60, 75.0, "EUR/year"),
    ):
        row = dict(template)
        row.update({
            "id": identifier,
            "subject_id": subject,
            "value": value,
            "unit": unit,
            "game_minute": minute,
            "tick": 0,
            "completeness": "complete",
        })
        samples.append(row)
    state.update_table("history_snapshots", pl.DataFrame(samples, schema=table.schema))

    comparison = HistoryQueryService().compare(
        state, "country", ["USA", "CAN"], "country.gdp", start_minute=0, end_minute=60,
    )

    assert comparison["unit_compatible"] is False
    assert comparison["common_values"]["USA"]["value"] == 150.0
    assert comparison["common_values"]["CAN"]["value"] == 75.0
    assert comparison["normalized_common_values"]["USA"]["value"] == 150.0
    assert comparison["normalized_common_values"]["CAN"]["value"] == 150.0
    assert comparison["normalized_common_values"]["CAN"]["baseline_unit"] == "EUR/year"
    assert comparison["normalized_common_values"]["CAN"]["baseline_minute"] == 0
    assert comparison["normalization_unavailable_subjects"] == []


def test_history_ranking_excludes_incompatible_units_instead_of_mixing_magnitudes() -> None:
    state = _state()
    HistorySystem().update(state, 0.0)
    snapshots = state.tables["history_snapshots"].with_columns(
        pl.when((pl.col("indicator_id") == "country.gdp") & (pl.col("subject_id") == "CAN"))
        .then(pl.lit("EUR/year"))
        .otherwise(pl.col("unit"))
        .alias("unit")
    )
    state.update_table("history_snapshots", snapshots)

    ranking = HistoryQueryService().rank(state, "country.gdp")

    assert ranking["unit_compatible"] is False
    assert ranking["unit"] == "USD/year"
    assert [row["subject_id"] for row in ranking["rows"]] == ["USA"]
    assert ranking["incompatible_unit_subjects"] == ["CAN"]
    assert ranking["excluded"] == ["CAN"]


def test_history_comparison_does_not_normalize_across_an_unconverted_unit_transition() -> None:
    state = _state()
    HistorySystem().update(state, 0.0)
    table = state.tables["history_snapshots"]
    template = table.filter(pl.col("indicator_id") == "country.gdp").row(0, named=True)
    samples = []
    for identifier, subject, minute, value, unit in (
        ("usa-base", "USA", 0, 100.0, "USD/year"),
        ("usa-latest", "USA", 60, 150.0, "USD/year"),
        ("can-base", "CAN", 0, 50.0, "EUR/year"),
        ("can-latest", "CAN", 60, 75.0, "USD/year"),
    ):
        row = dict(template)
        row.update({
            "id": identifier,
            "subject_id": subject,
            "value": value,
            "unit": unit,
            "game_minute": minute,
            "tick": 0,
            "completeness": "complete",
        })
        samples.append(row)
    state.update_table("history_snapshots", pl.DataFrame(samples, schema=table.schema))

    comparison = HistoryQueryService().compare(
        state, "country", ["USA", "CAN"], "country.gdp", start_minute=0, end_minute=60,
    )

    assert comparison["normalized_common_values"]["USA"]["value"] == 150.0
    assert comparison["normalization_unavailable_subjects"] == ["CAN"]


def test_history_ranking_keeps_missing_boundary_rows_and_excludes_unaligned_series() -> None:
    state = _state()
    HistorySystem().update(state, 0.0)
    table = state.tables["history_snapshots"]
    template = table.filter(pl.col("indicator_id") == "country.gdp").row(0, named=True)
    samples = []
    for identifier, subject, minute, value, completeness in (
        ("usa-early", "USA", 3, 1000.0, "complete"),
        ("usa-gap", "USA", 5, None, "missing"),
        ("usa-late", "USA", 10, 1200.0, "complete"),
        ("can-common", "CAN", 5, 800.0, "complete"),
        ("mex-late", "MEX", 8, 700.0, "complete"),
    ):
        row = dict(template)
        row.update({
            "id": identifier,
            "subject_id": subject,
            "game_minute": minute,
            "tick": 0,
            "value": value,
            "completeness": completeness,
        })
        samples.append(row)
    state.update_table(
        "history_snapshots",
        pl.DataFrame(samples, schema=table.schema, strict=False),
    )

    ranking = HistoryQueryService().rank(state, "country.gdp")

    assert ranking["evaluation_minute"] == 5
    assert [row["subject_id"] for row in ranking["rows"]] == ["CAN"]
    assert ranking["excluded"] == ["MEX", "USA"]


def test_history_ranking_uses_revision_matched_series_index() -> None:
    state = _state()
    HistorySystem().update(state, 0.0)
    query = HistoryQueryService()

    with patch.object(
        query,
        "_latest_snapshot_rows_at_common_boundary",
        side_effect=AssertionError("the complete series index should avoid a history scan"),
    ):
        ranking = query.rank(state, "country.gdp")

    assert ranking["evaluation_minute"] == 0
    assert {row["subject_id"] for row in ranking["rows"]} == {"USA", "CAN"}
    assert all(row["id"].startswith("history:country.gdp:country:") for row in ranking["rows"])


def test_history_current_value_uses_live_authoritative_inputs() -> None:
    state = _state()
    HistorySystem().update(state, 0.0)
    queries = HistoryQueryService()

    gdp = queries.current_value(state, "country", "USA", "country.gdp")
    per_capita = queries.current_value(state, "country", "USA", "country.gdp_per_capita")
    regional_population = queries.current_value(state, "region", "1", "region.population")
    assert gdp == {"available": True, "value": 1000.0, "unit": "USD/year", "value_kind": "authoritative"}
    assert per_capita["value"] == 1000.0 / 140.0 and per_capita["value_kind"] == "derived"
    assert regional_population["value"] == 80.0 and regional_population["value_kind"] == "derived"
    assert queries.current_value(state, "country", "USA", "country.resource_coverage")["value"] == 0.8
    assert queries.current_value(state, "country", "USA", "diplomacy.active_treaties")["value"] == 1.0


def test_history_compaction_is_deterministic_and_series_bounded() -> None:
    state = _state()
    system = HistorySystem()
    system.update(state, 0.0)
    definition_table = state.tables["history_indicator_definitions"]
    definitions = definition_table.to_dicts()
    gdp = next(row for row in definitions if row["id"] == "country.gdp")
    gdp["sample_interval_minutes"] = 1
    gdp["retention_window_minutes"] = 1000
    gdp["max_samples_per_series"] = 2
    state.update_table("history_indicator_definitions", pl.DataFrame(definitions, schema=definition_table.schema))

    for minute in range(1, 9):
        state.time.total_minutes = minute
        state.globals["tick"] = minute + 1
        state.update_table("countries", state.tables["countries"].with_columns(
            (pl.col("gdp") + 1.0).alias("gdp")
        ))
        system.update(state, 0.0)

    kept = [row for row in _rows(state, "history_snapshots") if row["indicator_id"] == "country.gdp" and row["subject_id"] == "USA"]
    assert len(kept) <= 4
    assert max(row["value"] for row in kept) == 1008.0
    assert sorted(row["game_minute"] for row in kept) == sorted(set(row["game_minute"] for row in kept))


def test_history_compaction_matches_retention_and_downsample_boundaries() -> None:
    state = _state()
    template = HistorySystem._row_defaults(state, "history_snapshots")
    rows = []
    for minute, tick in ((12, 1), (0, 1), (8, 2), (5, 1), (11, 1), (7, 1), (10, 2), (6, 1), (9, 1)):
        row = dict(template)
        row.update({
            "id": f"snapshot:{minute}:{tick}", "subject_type": "country", "subject_id": "USA",
            "indicator_id": "country.gdp", "value": None if minute == 8 else float(minute),
            "game_minute": minute, "tick": tick,
        })
        rows.append(row)
    group = pl.DataFrame(rows, schema=state.tables["history_snapshots"].schema)
    recent_rows = [row for row in group.to_dicts() if row["game_minute"] >= 5]

    for cap in (1, 2, 3, 6):
        compacted = HistorySystem._compact_group(group, now=15, retention=10, cap=cap)
        expected = HistorySystem._downsample(recent_rows, cap)
        assert compacted.get_column("id").to_list() == [row["id"] for row in expected]
        assert compacted.height <= cap

    cap_six = HistorySystem._compact_group(group, now=15, retention=10, cap=6)
    assert cap_six.filter(pl.col("id") == "snapshot:8:2").get_column("value").to_list() == [None]


def test_history_survives_state_snapshot_roundtrip_without_replaying_events() -> None:
    state = _state()
    state.journal.append_domain_event(
        EventWarStarted("war-1", "USA", "CAN"), event_id="persisted-event", tick=1,
        source="simulation", game_minute=90,
    )
    HistorySystem().update(state, 0.0)
    before_series = HistoryQueryService().series(state, "country", "USA", "country.gdp")
    before_events = state.tables["history_events"].height

    restored = GameState.from_ipc(state.to_ipc())
    after_series = HistoryQueryService().series(restored, "country", "USA", "country.gdp")
    HistorySystem().update(restored, 0.0)

    assert after_series == before_series
    assert restored.tables["history_events"].height == before_events
    assert restored.globals["history_journal_cursor"] == 1


def test_history_survives_save_load_and_deterministic_replay_continuation(tmp_path) -> None:
    state = _state()
    state.update_table(
        "regions",
        state.tables["regions"].with_columns(
            pl.Series("hex", ["#REGION-1", "#REGION-2", "#REGION-3"])
        ),
    )
    state.globals["history_start_seed_pending"] = True
    HistoryStartSeedSystem().update(state, 0.0)
    state.journal.append_domain_event(
        EventWarStarted("war-1", "USA", "CAN"), event_id="saved-war", tick=1,
        source="simulation", game_minute=0,
    )
    HistorySystem().update(state, 0.0)
    registry = build_base_schema_registry()
    ipc_copy = GameState.from_ipc(state.to_ipc())
    registry.ensure_state(ipc_copy)

    config = GameConfig(tmp_path)
    assert SaveWriter(config).save_game(state, "history-roundtrip")
    loaded = DataLoader(config, schema_registry=registry).load_save("history-roundtrip")

    table_names = (
        "history_indicator_definitions", "history_series_state", "history_snapshots", "history_events",
    )
    for candidate in (ipc_copy, loaded):
        assert all(
            candidate.get_table(name).to_dicts() == state.get_table(name).to_dicts()
            for name in table_names
        )
        assert any(
            row["source_reference"]
            for row in candidate.get_table("history_snapshots").to_dicts()
            if row["indicator_id"] == "region.population"
        )

    continuations = (state, ipc_copy, loaded)
    for candidate in continuations:
        candidate.time.total_minutes = 1440
        candidate.globals["tick"] = 2
        candidate.update_table(
            "countries",
            candidate.get_table("countries").with_columns(
                pl.when(pl.col("id") == "USA")
                .then(pl.lit(1100.0))
                .otherwise(pl.col("gdp"))
                .alias("gdp")
            ),
        )
        HistorySystem().update(candidate, 0.0)

    for candidate in continuations[1:]:
        for name in table_names:
            candidate_rows = candidate.get_table(name).to_dicts()
            expected_rows = state.get_table(name).to_dicts()
            if name == "history_series_state":
                # Source revisions are process-local table counters and are rebuilt on load.
                for row in (*candidate_rows, *expected_rows):
                    row.pop("source_revision", None)
            assert candidate_rows == expected_rows, name
