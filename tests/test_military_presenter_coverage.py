from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.military import presenter as presenter_module
from src.client.ui.panels.military.presenter import MilitaryPresenter


def state(tables=None, *, globals_=None):
    return SimpleNamespace(tables=tables or {}, globals=globals_ or {})


def test_build_summary_aggregates_all_force_branches_and_supporting_counts():
    presenter = MilitaryPresenter()
    presenter._country_units = lambda _state, _tag: [
        {"unit_type": "fighter aircraft", "strength": 10, "is_moving": True},
        {"unit_type": "air wing", "strength": 4},
        {"unit_type": "carrier fleet", "strength": 20},
        {"unit_type": "strategic missile", "strength": 3},
        {"unit_type": "army", "strength": 12},
    ]
    presenter.strategic_inventory_for_country = lambda _state, _tag: [
        {"ready": 2, "quantity": 5, "defense_rating": 0.6},
        {"ready": "bad", "quantity": 3, "defense_rating": 0.8},
    ]
    presenter.wars_for_country = lambda _state, _tag: [{}, {}]
    presenter.covert_cells_for_country = lambda _state, _tag: [{}]

    result = presenter.build_summary(object(), "USA")

    assert [(item.label, item.strength, item.unit_count) for item in result.branches] == [
        ("LAND", 12, 1), ("AIR", 14, 2), ("NAVAL", 20, 1), ("STRATEGIC", 3, 1),
    ]
    assert result.moving_units == 1
    assert result.active_wars == 2
    assert result.covert_cells == 1
    assert result.strategic_ready == 2
    assert result.strategic_total == 8
    assert result.missile_defense_pct == 70.0


def test_branch_and_battle_labels_cover_known_and_unknown_values():
    presenter = MilitaryPresenter()

    assert [presenter._classify_branch(value) for value in (
        "fighter", "jet bomber", "naval ship", "submarine", "strategic rocket", "army",
    )] == ["AIR", "AIR", "NAVAL", "NAVAL", "STRATEGIC", "LAND"]
    assert presenter._humanize_unit_type("air_defense") == "Air Defense"
    assert presenter_module.battle_mode_label(" assault ") == "Active"
    assert presenter_module.battle_mode_label(None) == "Unknown"
    assert presenter_module.battle_status_label("inactive") == "Inactive"
    assert presenter_module.battle_status_label("unknown") == "Unknown"
    assert presenter_module.battle_balance_estimate_label(0.375) == "Balance estimate 38%"
    assert presenter_module.battle_balance_estimate_label("bad") == "Balance estimate 0%"


def test_unit_rows_cover_lifecycle_readiness_design_and_market_states(monkeypatch):
    monkeypatch.setattr(presenter_module, "unit_upkeep_by_id", lambda _state: {"U1": 12.5})
    game = state({
        "countries": pl.DataFrame({"id": ["USA", "CAN"], "name": ["United States", "Canada"]}),
        "regions": pl.DataFrame({"id": [1], "name": ["Capital"]}),
        "units": pl.DataFrame({
            "id": [f"U{i}" for i in range(1, 8)],
            "owner": ["USA"] * 7,
            "unit_type": ["army", "army", "navy", "army", "army", "army", "army"],
            "strength": [10, 20, 30, 40, 50, 60, 70],
            "equipment_quantity": [None, 18, 28, 38, 48, 58, 68],
            "design_id": ["own", "foreign", "own", "own", "own", "own", "infantry"],
            "current_region_id": [1] * 7,
            "unit_lifecycle": ["deployment_queued", "deployment_transit", "deployment_blocked", "training", "available", "available", "available"],
            "readiness_status": ["ready", "ready", "ready", "ready", "fortified", "ready", "ready"],
            "readiness_transition_id": ["", "", "", "", "transition", "", ""],
            "readiness_progress": [0.0, 0.0, 0.0, 0.0, 1.5, 0.0, 0.0],
            "movement_progress": [0.0, 1.5, 0.0, 0.0, 0.0, -0.2, 0.0],
            "training_progress": [0.0, 0.0, 0.0, -0.2, 0.0, 0.0, 0.0],
            "is_moving": [False, False, False, False, False, True, False],
            "training_level": ["Recruit", "Veteran", "Regular", "Regular", "Elite", "Recruit", "Regular"],
        }),
        "unit_designs": pl.DataFrame({
            "id": ["own", "foreign", "infantry"],
            "country_id": ["USA", "CAN", "USA"],
            "class_name": ["tank", "tank", "infantry"],
            "display_name": ["Armor", "Foreign armor", "Infantry design"],
            "name": ["Armor", "Foreign armor", "Infantry"],
            "cost": [1200.0, 2400.0, 500.0],
        }),
        "unit_market_listings": pl.DataFrame({
            "unit_id": ["U7"], "status": ["listed"], "quantity": [1],
        }),
        "unit_movement_routes": pl.DataFrame({
            "unit_id": ["U6"], "status": ["blocked"], "rejection_reason": ["route closed"],
            "route_region_ids": [[1]], "destination_region_id": [1], "is_naval_invasion": [False],
        }),
    })

    rows = MilitaryPresenter().unit_rows(game, "USA")
    by_id = {row.unit_id: row for row in rows}

    assert by_id["U1"].status == "Deployment queued"
    assert by_id["U1"].location == "Deployment queue"
    assert by_id["U1"].design_id == "own"
    assert by_id["U1"].design_name == "Armor"
    assert by_id["U1"].upkeep == 12.5
    assert by_id["U2"].status == "Deployment transit"
    assert by_id["U2"].progress_pct == 100.0
    assert by_id["U2"].design_id == ""
    assert by_id["U2"].design_name == "Unknown design"
    assert by_id["U3"].status == "Deployment blocked"
    assert by_id["U4"].status == "Training"
    assert by_id["U4"].progress_pct == 0.0
    assert by_id["U5"].status == "Fortified"
    assert by_id["U5"].progress_pct == 100.0
    assert by_id["U6"].status == "Moving"
    assert by_id["U6"].progress_pct == 0.0
    assert by_id["U6"].route_summary == "Blocked: route closed"
    assert by_id["U7"].design_id == ""
    assert by_id["U7"].design_name == "Infantry design"
    assert by_id["U7"].for_sale is True


def test_route_summary_covers_blocked_invasion_retreat_return_and_fallback():
    presenter = MilitaryPresenter()
    game = state({"regions": pl.DataFrame({"id": [1, 2], "name": ["Origin", "Target"]})})

    assert presenter._route_summary(game, None) == ""
    assert presenter._route_summary(game, {"status": "blocked"}) == "Blocked: route needs review"
    route = {
        "status": "active", "route_region_ids": [1], "destination_region_id": 2,
        "is_naval_invasion": True,
    }
    assert presenter._route_summary(game, route) == "Landing: Origin → Target"
    assert presenter._route_summary(game, route, "battle_retreating") == "Retreat to battle rear · Target"
    assert presenter._route_summary(game, route, "battle_returning") == "Return to capital: Origin → Target"
    assert presenter._route_summary(game, {"status": "active"}) == "Move: Unknown → Unknown"


def test_reserve_projection_filters_lifecycles_and_attaches_training_and_design_data():
    game = state({
        "units": pl.DataFrame({
            "id": ["U1", "U2", "U3", "U4"],
            "unit_type": ["army", "navy", "armor", "air"],
            "strength": [10, 20, 30, 40],
            "design_id": ["D1", "missing", "D1", "D1"],
            "unit_lifecycle": ["deployment_queued", "deployment_blocked", "training", "available"],
            "unit_domain": ["", "naval", "", "land"],
            "training_level": ["Veteran", "Recruit", "Elite", "Regular"],
            "training_state": ["", "", "training", ""],
            "training_progress": [0.0, 0.0, 1.5, 0.0],
        }),
        "unit_designs": pl.DataFrame({
            "id": ["D1"], "display_name": ["Armored Division"], "name": ["Armor"], "branch": ["land"],
        }),
        "unit_training_orders": pl.DataFrame({
            "unit_id": ["U1", "U3", "U4"], "status": ["completed", "active", "cancelled"],
            "id": ["T1", "T3", "T4"],
        }),
        "unit_deployment_orders": pl.DataFrame({
            "id": ["O1", "O2", "O3", "O4", "O5"],
            "country_id": ["USA"] * 5,
            "unit_id": ["U1", "U2", "U3", "U4", "ORPHAN"],
            "source_region_id": [1] * 5,
            "destination_region_id": [2] * 5,
            "status": ["queued", "blocked", "training", "ready", "queued"],
        }),
    })

    rows = MilitaryPresenter().reserve_units_for_country(game, "USA")

    assert [row["unit_id"] for row in rows] == ["U2", "U1", "U3"]
    by_id = {row["unit_id"]: row for row in rows}
    assert by_id["U1"]["design_name"] == "Armored Division"
    assert by_id["U1"]["unit_domain"] == "land"
    assert by_id["U1"]["training_level"] == "Veteran"
    assert by_id["U1"]["training_order"] == {}
    assert by_id["U2"]["design_name"] == "navy"
    assert by_id["U3"]["lifecycle"] == "training"
    assert by_id["U3"]["training_progress"] == 1.0
    assert by_id["U3"]["training_order"]["id"] == "T3"


def test_table_projections_handle_missing_empty_filtered_and_unfiltered_tables():
    presenter = MilitaryPresenter()
    assert presenter.production_orders_for_country(state(), "USA") == []
    assert presenter.designs_for_country(state(), "USA") == []
    assert presenter.research_tracks_for_country(state(), "USA") == []
    assert presenter.covert_cells_for_country(state(), "USA") == []

    game = state({
        "production_orders": pl.DataFrame({"id": ["P1", "P2"], "country_id": ["USA", "CAN"], "priority": [1, 3]}),
        "unit_designs": pl.DataFrame({
            "id": ["D2", "D1", "D3"], "country_id": ["USA", "USA", "CAN"],
            "branch": ["naval", "land", "air"], "display_name": ["Zeta", "Alpha", "Other"],
        }),
        "research_tracks": pl.DataFrame({"id": ["R2", "R1", "R3"], "country_id": ["USA", "USA", "CAN"], "priority": [2, 1, 0]}),
        "covert_cells": pl.DataFrame({"id": ["C1", "C2"], "country_id": ["USA", "CAN"]}),
    })

    assert [row["id"] for row in presenter.production_orders_for_country(game, "USA")] == ["P1"]
    assert [row["id"] for row in presenter.designs_for_country(game, "USA")] == ["D1", "D2"]
    assert [row["id"] for row in presenter.research_tracks_for_country(game, "USA")] == ["R1", "R2"]
    assert [row["id"] for row in presenter.covert_cells_for_country(game, "USA")] == ["C1"]

    unfiltered = state({
        "production_orders": pl.DataFrame({"id": ["P"], "priority": [1]}),
        "unit_designs": pl.DataFrame({"id": ["D"], "display_name": ["Design"]}),
        "research_tracks": pl.DataFrame({"id": ["R"], "priority": [1]}),
        "covert_cells": pl.DataFrame({"id": ["C"]}),
    })
    assert presenter.production_orders_for_country(unfiltered, "USA")[0]["id"] == "P"
    assert presenter.designs_for_country(unfiltered, "USA")[0]["id"] == "D"
    assert presenter.research_tracks_for_country(unfiltered, "USA")[0]["id"] == "R"
    assert presenter.covert_cells_for_country(unfiltered, "USA")[0]["id"] == "C"


def test_war_projections_normalize_members_and_keep_defaults():
    game = state({
        "countries": pl.DataFrame({"id": ["USA", "CAN", "MEX"], "name": ["United States", "Canada", "Mexico"]}),
        "countries_wars": pl.DataFrame({
            "id": [None, "war-2"],
            "side_a": [["usa", "CAN"], []],
            "side_b": [["MEX"], ["CAN"]],
            "status": [None, "concluded"],
            "leader_a": [None, None],
            "leader_b": [None, "CAN"],
        }),
    })
    presenter = MilitaryPresenter()

    all_wars = presenter.all_wars(game)
    assert all_wars[0]["id"] == "war-001"
    assert all_wars[0]["status"] == "Active"
    assert all_wars[0]["front"] == "United States, Canada vs Mexico"
    assert all_wars[0]["leader_a"] == "usa"
    assert all_wars[1]["leader_a"] == "UNK"
    assert all_wars[1]["intent_a"] == "war"
    assert [war["id"] for war in presenter.wars_for_country(game, "CAN")] == ["war-001", "war-2"]
    assert presenter.wars_for_country(game, "BRA") == []
    assert presenter.all_wars(state()) == []


def test_preferred_targets_without_relation_rows_excludes_allies_and_war_opponents():
    game = state({
        "countries": pl.DataFrame({"id": ["USA", "CAN", "MEX", "BRA"]}),
        "countries_relations": pl.DataFrame(),
        "countries_wars": pl.DataFrame({
            "id": ["W1"], "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["active"],
        }),
        "countries_treaties": pl.DataFrame({
            "type": ["military_alliance", "economic"],
            "members": [["USA", "MEX"], []],
            "side_a": [[], ["USA"]],
            "side_b": [[], ["BRA"]],
        }),
    })
    presenter = MilitaryPresenter()

    assert [row["country_tag"] for row in presenter.preferred_war_targets(game, "USA")] == ["BRA"]
    assert presenter.preferred_war_targets(state(), "USA") == []
