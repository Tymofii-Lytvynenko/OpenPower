from types import SimpleNamespace

import polars as pl
import pytest

from src.client.ui.panels.military.presenter import MilitaryPresenter


def _state(tables=None, globals_=None):
    return SimpleNamespace(
        tables=tables or {},
        globals=globals_ or {},
        table_revisions={},
    )


def test_strategic_orders_redact_undetected_details_and_filter_impacts():
    presenter = MilitaryPresenter()
    orders = pl.DataFrame([
        {
            "id": "own", "country_id": "USA", "target_country_id": "CAN",
            "launch_detected": False, "launch_attributed": False, "status": "pending",
            "weapon_id": "usa-1", "yield_kt": 200.0, "blast_radius_km": 4.0,
            "payload_level": 2, "launched_at_minute": 5,
        },
        {
            "id": "hidden", "country_id": "RUS", "target_country_id": "USA",
            "launch_detected": False, "launch_attributed": False, "status": "pending",
            "weapon_id": "rus-1", "yield_kt": 500.0, "blast_radius_km": 8.0,
            "payload_level": 3, "launched_at_minute": 15,
        },
        {
            "id": "detected", "country_id": "RUS", "target_country_id": "USA",
            "launch_detected": True, "launch_attributed": False, "status": "pending",
            "weapon_id": "rus-2", "yield_kt": 800.0, "blast_radius_km": 10.0,
            "payload_level": 4, "launched_at_minute": 10,
        },
        {
            "id": "impact", "country_id": "CHN", "target_country_id": "USA",
            "launch_detected": False, "launch_attributed": True, "status": "impact",
            "weapon_id": "chn-1", "yield_kt": 300.0, "blast_radius_km": 6.0,
            "payload_level": 2, "launched_at_minute": 8,
        },
    ])
    impacts = pl.DataFrame([
        {"id": "i-own", "launch_order_id": "own", "created_at_minute": 5},
        {"id": "i-hidden", "launch_order_id": "hidden", "created_at_minute": 15},
        {"id": "i-detected", "launch_order_id": "detected", "created_at_minute": 10},
        {"id": "i-impact", "launch_order_id": "impact", "created_at_minute": 8},
    ])
    game = _state({"strategic_launch_orders": orders, "strategic_impacts": impacts})

    visible = presenter.strategic_orders_for_country(game, " usa ")

    assert [row["id"] for row in visible] == ["detected", "impact", "own"]
    assert visible[0]["country_id"] == "Unknown"
    assert visible[0]["weapon_id"] == ""
    assert visible[0]["yield_kt"] == 0.0
    assert visible[0]["blast_radius_km"] == 0.0
    assert visible[0]["payload_level"] == 0
    assert visible[1]["country_id"] == "CHN"
    assert visible[1]["weapon_id"] == ""
    assert visible[1]["payload_level"] == 2
    assert [row["id"] for row in presenter.strategic_impacts_for_country(game, "USA")] == [
        "i-detected", "i-impact", "i-own",
    ]
    assert presenter.strategic_orders_for_country(_state(), "USA") == []


def test_missile_defense_and_authorization_contexts_filter_and_normalize():
    presenter = MilitaryPresenter()
    game = _state(
        {"missile_defense_layers": pl.DataFrame([
            {"id": "short", "country_id": "USA", "layer": "short_range"},
            {"id": "long", "country_id": "USA", "layer": "long_range"},
            {"id": "foreign", "country_id": "CAN", "layer": "long_range"},
        ])},
        {"strategic_authorization_contexts": [" cabinet ", "", "cabinet", "senate"]},
    )

    assert [row["id"] for row in presenter.missile_defense_for_country(game, " usa ")] == [
        "long", "short",
    ]
    assert presenter.strategic_authorization_contexts(game) == ["cabinet", "senate"]
    assert presenter.strategic_authorization_contexts(_state(globals_={
        "strategic_authorization_contexts": "cabinet",
    })) == []


def test_payload_profile_overrides_validate_levels_and_clamp_negative_values():
    presenter = MilitaryPresenter()
    defaults = presenter.strategic_payload_profiles(_state(globals_={
        "strategic_payload_profiles": "invalid",
    }))
    profiles = presenter.strategic_payload_profiles(_state(globals_={
        "strategic_payload_profiles": {
            "1": {"yield_kt": -10, "blast_radius_km": "3.5"},
            "2": {"yield_kt": "invalid"},
            "999": {"yield_kt": 1, "blast_radius_km": 1},
            "3": [100, 2],
        },
    }))

    assert profiles[1] == (0.0, 3.5)
    assert profiles[2] == defaults[2]
    assert profiles[3] == defaults[3]
    assert 999 not in profiles


@pytest.mark.parametrize(
    ("posture", "unit", "route", "regions", "expected"),
    [
        ({"status": "retreating"}, {"arrival_at_minute": 8}, {}, {}, ("Continue withdrawal to the rear position", 8)),
        ({"status": "disengaging"}, {"arrival_at_minute": 9}, {}, {}, ("Continue withdrawal to the rear position", 9)),
        ({"status": "reorganizing", "strategy": "retreat", "expires_at_minute": 12}, {}, {}, {}, ("Finish regrouping, then return toward the capital", 12)),
        ({"status": "reorganizing", "strategy": "attack", "expires_at_minute": 13}, {}, {}, {}, ("Finish reorganization and rejoin the battle", 13)),
        ({"status": "returning"}, {"arrival_at_minute": 14}, {"destination_region_id": 2}, {2: "North"}, ("Continue return route toward North", 14)),
        ({"status": "returning"}, {}, {}, {}, ("Continue return route toward capital route destination", 0)),
        ({"status": "blocked"}, {}, {}, {}, ("Review the blocked route; the force remains out of assault", 0)),
        ({"status": "completed"}, {}, {}, {}, ("No pending transition", 0)),
        ({"status": "cancelled"}, {}, {}, {}, ("No pending transition", 0)),
        ({"status": "active", "strategy": "defend"}, {}, {}, {}, ("Hold position and counterattack when eligible", 0)),
        ({"status": "active", "strategy": "back_off"}, {}, {}, {}, ("Hold at the rear without initiating an assault", 0)),
        ({"status": "active", "strategy": "reorganize", "expires_at_minute": 15}, {}, {}, {}, ("Finish reorganization and rejoin the battle", 15)),
        ({"status": "active", "strategy": "unknown"}, {}, {}, {}, ("Hold current position", 0)),
    ],
)
def test_battle_posture_next_action_projects_each_transition(
    posture, unit, route, regions, expected,
):
    assert MilitaryPresenter()._battle_posture_next_action(
        posture, unit, route, regions,
    ) == expected


def test_strategic_authorization_preview_covers_policy_and_war_paths():
    presenter = MilitaryPresenter()
    assert presenter._strategic_authorization_preview(
        _state(globals_={"strategic_authorization_policy": "open"}), "USA", "CAN", "",
    )["authorized"] is True
    assert presenter._strategic_authorization_preview(
        _state(globals_={"strategic_authorized_countries": [" usa "]}), "USA", "CAN", "",
    )["label"] == "authorized by scenario policy"
    assert presenter._strategic_authorization_preview(
        _state(globals_={
            "strategic_authorization_policy": "explicit",
            "strategic_authorization_contexts": ["cabinet"],
        }), "USA", "CAN", "senate",
    )["reason"] == "The selected authorization context is not permitted."
    assert presenter._strategic_authorization_preview(
        _state(globals_={"strategic_authorization_contexts": ["cabinet"]}), "USA", "CAN", "",
    )["reason"] == "Select a configured launch authorization context."
    assert presenter._strategic_authorization_preview(
        _state(), "USA", "CAN", "",
    )["reason"] == "Political launch authorization is missing."
    game_at_war = _state({"countries_wars": pl.DataFrame([
        {"status": "active", "side_a": ["USA"], "side_b": ["CAN"]},
        {"status": "ended", "side_a": ["USA"], "side_b": ["MEX"]},
    ])})
    assert presenter._strategic_authorization_preview(
        game_at_war, "USA", "CAN", "",
    )["label"] == "authorized by active war"


def test_strategic_launch_preview_reports_independent_reasons_and_fallback_flight_time():
    presenter = MilitaryPresenter()
    game = _state(
        {
            "countries": pl.DataFrame({"id": ["USA"], "money_reserves": [0.0]}),
            "regions": pl.DataFrame({"id": [2], "owner": ["USA"]}),
        },
        {},
    )
    weapon = {
        "operational": False,
        "ready": 0,
        "quantity": 0,
        "research_permitted": False,
        "pending_order_status": "pending",
        "launch_cost": 20.0,
        "flight_minutes": 0,
    }

    invalid_target = presenter.strategic_launch_preview(game, "USA", weapon, 999)
    own_target = presenter.strategic_launch_preview(game, "USA", weapon, 2)

    assert "Select a valid target region." in invalid_target["reasons"]
    assert "Select a region owned by another country." in own_target["reasons"]
    for message in (
        "This weapon is unavailable or not ready.",
        "Required strategic program and weapon research are incomplete.",
        "This weapon already has a pending launch order.",
        "The country cannot fund this launch cost.",
        "Political launch authorization is missing.",
    ):
        assert message in own_target["reasons"]
    assert invalid_target["flight_minutes"] == 60


def test_strategic_weapon_origin_prefers_valid_capital_then_lowest_owned_region():
    presenter = MilitaryPresenter()
    regions = pl.DataFrame([
        {"id": 4, "owner": "USA"},
        {"id": 2, "owner": "USA"},
        {"id": 3, "owner": "CAN"},
    ])
    game = _state({
        "regions": regions,
        "country_governments": pl.DataFrame([
            {"country_id": "USA", "capital_region_id": 3},
            {"country_id": "USA", "capital_region_id": 4},
        ]),
    })

    assert presenter._strategic_weapon_origin(game, "USA", {"origin_region_id": 4})["id"] == 4
    assert presenter._strategic_weapon_origin(game, "USA", {"origin_region_id": 3}) is None
    assert presenter._strategic_weapon_origin(game, "USA", {"origin_region_id": 99})["id"] == 4
    fallback = _state({"regions": regions})
    assert presenter._strategic_weapon_origin(fallback, "USA", {"origin_region_id": 99})["id"] == 2
    assert presenter._strategic_weapon_origin(_state(), "USA", {}) is None


def test_strategic_defense_coverage_uses_explicit_ranges_and_radius():
    presenter = MilitaryPresenter()
    target = {"id": 2, "latitude": 0.0, "longitude": 2.0}

    assert presenter._strategic_defense_covers_region(
        _state(), {"country_id": "USA", "coverage_region_ids": [2]}, target,
    ) is True
    assert presenter._strategic_defense_covers_region(
        _state(), {
            "country_id": "USA", "coverage_region_ids": [],
            "center_latitude": 0.0, "center_longitude": 0.0, "range_km": 100.0,
        }, target,
    ) is False
    assert presenter._strategic_defense_covers_region(
        _state(), {
            "country_id": "USA", "coverage_region_ids": [2],
            "center_latitude": 0.0, "center_longitude": 0.0,
            "range_km": 300.0, "coverage_radius_km": 100.0,
        }, target,
    ) is True


def test_strategic_production_preview_checks_research_policy_cost_and_funds():
    presenter = MilitaryPresenter()
    game = _state(
        {"countries": pl.DataFrame({"id": ["USA"], "money_reserves": [10.0]})},
        {"strategic_production_authorized_countries": ["CAN"]},
    )
    preview = presenter.strategic_production_preview(game, "USA", {
        "research_permitted": False,
        "production_cost": 0,
        "production_minutes": 0,
    }, quantity=3)

    assert preview["can_produce"] is False
    assert preview["total_cost"] == 0.0
    assert preview["production_minutes"] == 0
    assert preview["reasons"] == [
        "Required strategic program and weapon research are incomplete.",
        "This country lacks policy authority to produce strategic weapons.",
        "This weapon design has no configured production cost and duration.",
    ]
    underfunded = presenter.strategic_production_preview(game, "USA", {
        "research_permitted": True,
        "production_cost": 5,
        "production_minutes": 10,
    }, quantity=3)
    assert "The country cannot fund this production order." in underfunded["reasons"]


def test_strategic_production_orders_filter_and_sort_newest_first():
    presenter = MilitaryPresenter()
    game = _state({"strategic_production_orders": pl.DataFrame([
        {"id": "old", "country_id": "USA", "ordered_at_minute": 5},
        {"id": "new", "country_id": "USA", "ordered_at_minute": 10},
        {"id": "foreign", "country_id": "CAN", "ordered_at_minute": 20},
    ])})

    assert [row["id"] for row in presenter.strategic_production_orders_for_country(game, " usa ")] == [
        "new", "old",
    ]
    assert presenter.strategic_production_orders_for_country(_state(), "USA") == []


def test_covert_missions_redact_details_for_discovered_targets_and_framed_viewers():
    presenter = MilitaryPresenter()
    missions = pl.DataFrame([
        {
            "id": "owned", "owner_country_id": "USA", "target_country_id": "CAN",
            "discovered_by_target": False, "attributed_country_id": "",
            "attributed_to_owner": False, "created_at_minute": 1,
            "cell_id": "own-cell", "output_json": '{"secret": true}', "confidence": 0.8,
            "target_sector": "industry", "complexity": "high", "target_resource_id": "oil",
            "target_unit_category": "armor",
        },
        {
            "id": "target", "owner_country_id": "CAN", "target_country_id": "USA",
            "discovered_by_target": True, "attributed_country_id": "",
            "attributed_to_owner": True, "created_at_minute": 3,
            "cell_id": "target-cell", "output_json": '{"secret": true}', "confidence": 0.9,
            "target_sector": "industry", "complexity": "high", "target_resource_id": "oil",
            "target_unit_category": "armor",
        },
        {
            "id": "framed", "owner_country_id": "MEX", "target_country_id": "CAN",
            "discovered_by_target": True, "attributed_country_id": "USA",
            "attributed_to_owner": False, "created_at_minute": 2,
            "cell_id": "framed-cell", "output_json": '{"secret": true}', "confidence": 0.7,
            "target_sector": "government", "complexity": "medium", "target_resource_id": "gold",
            "target_unit_category": "fleet",
        },
        {
            "id": "hidden", "owner_country_id": "RUS", "target_country_id": "CAN",
            "discovered_by_target": False, "attributed_country_id": "USA",
            "attributed_to_owner": False, "created_at_minute": 4,
            "cell_id": "hidden-cell", "output_json": "{}", "confidence": 1.0,
            "target_sector": "military", "complexity": "low", "target_resource_id": "",
            "target_unit_category": "infantry",
        },
    ])

    rows = presenter.covert_missions_for_country(_state({"covert_missions": missions}), " usa ")

    assert [row["id"] for row in rows] == ["target", "framed", "owned"]
    target, framed, owned = rows
    assert target["owner_country_id"] == "CAN"
    assert target["_viewer_role"] == "target"
    assert target["cell_id"] == "" and target["output_json"] == "{}" and target["confidence"] == 0
    assert framed["owner_country_id"] == "Unknown"
    assert framed["_viewer_role"] == "framed"
    assert (framed["target_sector"], framed["complexity"], framed["target_resource_id"], framed["target_unit_category"]) == ("", "", "", "")
    assert owned["cell_id"] == "own-cell" and "_viewer_role" not in owned
    assert presenter.covert_missions_for_country(_state(), "USA") == []


def test_foreign_force_estimates_ignore_invalid_findings_and_normalize_observations():
    presenter = MilitaryPresenter()
    presenter.covert_findings_for_country = lambda _state, _country: [
        {"category": "politics", "target_country_id": "CAN"},
        {"category": "military", "target_country_id": " "},
        {
            "id": "broken", "category": "military", "target_country_id": "CAN",
            "value_json": "not json", "information_status": "estimated",
            "confidence": 0.7, "freshness": 0.8,
        },
        {
            "id": "array", "category": "military", "target_country_id": "MEX",
            "value_json": "[]", "information_status": "estimated",
            "confidence": 0.7, "freshness": 0.8,
        },
        {
            "id": "outdated", "category": "military", "target_country_id": "ARG",
            "value_json": '{"unit_count_estimate": 22}', "information_status": "outdated",
            "confidence": 0.9, "freshness": 0.0,
        },
    ]

    estimates = presenter.foreign_force_estimates_for_country(_state(), "USA")
    by_target = {row["target_country_id"]: row for row in estimates}

    assert set(by_target) == {"ARG", "CAN", "MEX"}
    assert by_target["CAN"]["status"] == "unknown"
    assert by_target["CAN"]["total_count_range"] is None
    assert by_target["MEX"]["status"] == "unknown"
    assert by_target["ARG"]["status"] == "outdated"
    assert by_target["ARG"]["total_count_range"] is None
    assert presenter.foreign_force_estimates_for_country(_state(), "  ") == []


def test_mobilization_signals_validate_payloads_and_choose_strongest_public_signal():
    presenter = MilitaryPresenter()
    presenter.covert_findings_for_country = lambda _state, _country: [
        {"category": "military", "target_country_id": "CAN", "value_json": "{}"},
        {"category": "military_mobilization", "target_country_id": "CAN", "value_json": "invalid"},
        {"category": "military_mobilization", "target_country_id": "CAN", "value_json": "[]"},
        {
            "category": "military_mobilization", "target_country_id": "CAN",
            "value_json": '{"signal_type":"mobilization","domain":"space","from_readiness":"ready","to_readiness":"fortified"}',
        },
        {
            "category": "military_mobilization", "target_country_id": "CAN",
            "value_json": '{"signal_type":"mobilization","domain":"land","from_readiness":"unknown","to_readiness":"ready"}',
        },
        {
            "id": "weak", "category": "military_mobilization", "target_country_id": "CAN",
            "value_json": '{"signal_type":"mobilization","domain":"land","from_readiness":"parked","to_readiness":"ready","confidence_factors":{"observer_telecom":0.5}}',
            "source_country_id": "USA", "confidence": 0.4, "freshness": 0.5,
        },
        {
            "id": "strong", "category": "military_mobilization", "target_country_id": "CAN",
            "value_json": '{"signal_type":"mobilization","domain":"land","from_readiness":"ready","to_readiness":"fortified","confidence_factors":{"observer_telecom":0.8}}',
            "source_country_id": "MEX", "confidence": 0.9, "freshness": 0.9,
        },
    ]

    signals = presenter.mobilization_signals_for_country(_state(), "USA")

    assert len(signals) == 1
    assert signals[0]["from_readiness"] == "ready"
    assert signals[0]["to_readiness"] == "fortified"
    assert signals[0]["source_type"] == "allied"
    assert signals[0]["source_factors"] == {"observer_telecom": 0.8}
    assert "source_finding_id" not in signals[0]
    assert presenter.mobilization_signals_for_country(_state(), "  ") == []


def test_strategic_launch_preview_reports_missing_origin_and_out_of_range_target():
    presenter = MilitaryPresenter()
    weapon = {
        "operational": True,
        "ready": 1,
        "quantity": 1,
        "research_permitted": True,
        "launch_cost": 10,
        "range_km": 10,
    }
    globals_ = {"strategic_authorization_policy": "open"}
    missing_origin = _state(
        {
            "countries": pl.DataFrame({"id": ["USA"], "money_reserves": [100.0]}),
            "regions": pl.DataFrame({"id": [2], "owner": ["CAN"]}),
        },
        globals_,
    )
    out_of_range = _state(
        {
            "countries": pl.DataFrame({"id": ["USA"], "money_reserves": [100.0]}),
            "regions": pl.DataFrame({
                "id": [1, 2], "owner": ["USA", "CAN"],
                "latitude": [0.0, 0.0], "longitude": [0.0, 20.0],
            }),
        },
        globals_,
    )

    no_origin = presenter.strategic_launch_preview(missing_origin, "USA", weapon, 2)
    beyond_range = presenter.strategic_launch_preview(
        out_of_range, "USA", {**weapon, "origin_region_id": 1}, 2,
    )

    assert "This weapon has no valid controlled origin region." in no_origin["reasons"]
    assert "The target is outside this weapon's operational range." in beyond_range["reasons"]
    assert beyond_range["distance_km"] > 10


def test_sparse_presenter_tables_return_safe_empty_defaults():
    presenter = MilitaryPresenter()
    game = _state()

    assert presenter.production_orders_for_country(game, "USA") == []
    assert presenter.deployment_orders_for_country(game, "USA") == []
    assert presenter.foreign_designs_for_country(game, "USA") == []
    assert presenter.foreign_orders_for_country(game, "USA") == []
    assert presenter.market_listings_for_country(game, "USA") == []
    assert presenter.marketable_units_for_country(game, "USA") == []
    assert presenter.wars_for_country(game, "USA") == []
    assert presenter.strategic_inventory_for_country(game, "USA") == []
    assert presenter.missile_defense_for_country(game, "USA") == []
    assert presenter.battles_for_country(game, " ") == []
    assert presenter.battle_status(game, "battle-1", "USA") is None
    assert presenter._battle_visible_to_country(game, "battle-1", " ") is False
    assert presenter.battle_force_summary(game, "battle-1", "USA") == []
    assert presenter.battle_postures_for_country(game, "battle-1", "USA") == []
    assert presenter.battle_command_history(game, "battle-1", "USA") == []
    assert presenter.battle_loss_summary(game, "battle-1", "USA") == []
    assert presenter._country_units(game, "USA") == []
    assert presenter._allied_countries(game, "USA") == set()
    assert presenter._strategic_countries_at_war(game, "USA", "CAN") is False


def test_sparse_table_fallbacks_cover_deployment_market_and_foreign_design_filters():
    presenter = MilitaryPresenter()
    deployments = _state({
        "unit_deployment_orders": pl.DataFrame({"id": ["legacy-order"]}),
    })
    assert presenter.deployment_orders_for_country(deployments, "USA") == [{"id": "legacy-order"}]

    designs = _state({
        "unit_designs": pl.DataFrame([
            {"id": "own", "country_id": "USA"},
            {"id": "blank", "country_id": ""},
            {"id": "foreign", "country_id": "CAN"},
        ]),
    })
    assert presenter.foreign_designs_for_country(designs, "USA") == []

    listings = _state({
        "unit_market_listings": pl.DataFrame([
            {"id": "cancelled", "seller_country_id": "USA", "status": "cancelled", "quantity": 1},
            {"id": "empty", "seller_country_id": "USA", "status": "listed", "quantity": 0},
        ]),
    })
    assert presenter.market_listings_for_country(listings, "USA") == []
    assert presenter.marketable_units_for_country(_state({
        "units": pl.DataFrame({"unit_type": ["army"]}),
    }), "USA") == []


def test_war_and_intelligence_sharing_filters_accept_fallback_formats():
    presenter = MilitaryPresenter()
    wars = _state({"countries_wars": pl.DataFrame([
        {"status": "ended", "side_a": "USA", "side_b": "CAN"},
        {"status": "active", "side_a": "USA, CAN", "side_b": "MEX, USA"},
    ])})
    assert presenter._active_war_opponents(wars, "USA") == {"CAN", "MEX"}
    assert presenter._strategic_countries_at_war(wars, "USA", "CAN") is False

    treaty_effects = _state({"treaty_effects": pl.DataFrame([
        {"effect": "economic_sharing", "country_id": "CAN", "detail": '["USA"]'},
        {"effect": "military_intelligence_sharing", "country_id": "CAN", "detail": "broken"},
        {"effect": "military_intelligence_sharing", "country_id": "MEX", "detail": "{}"},
        {"effect": "military_intelligence_sharing", "country_id": "USA", "detail": '["USA"]'},
        {"effect": "military_intelligence_sharing", "country_id": "CAN", "detail": '["USA"]'},
    ])})
    assert presenter._military_intelligence_sources(treaty_effects, "USA") == {"CAN"}

    alliances = _state({"countries_treaties": pl.DataFrame([
        {"type": "trade", "members": "", "side_a": "USA", "side_b": "CAN"},
        {"type": "alliance", "members": "", "side_a": "MEX", "side_b": "BRA"},
        {"type": "defensive_pact", "members": "", "side_a": "USA", "side_b": "CAN"},
    ])})
    assert presenter._allied_countries(alliances, "USA") == {"CAN"}


def test_battle_projection_handles_missing_records_and_unmatched_units():
    presenter = MilitaryPresenter()
    game = _state({"battles": pl.DataFrame({
        "id": ["battle-1"], "attacker_side": ["USA"], "defender_side": ["CAN"],
    })})
    assert presenter.battle_force_summary(game, "battle-1", "USA") == []
    assert presenter.battle_postures_for_country(game, "battle-1", "USA") == []
    assert presenter.battle_command_history(game, "battle-1", "USA") == []
    assert presenter.battle_loss_summary(game, "battle-1", "USA") == []

    missing_unit = _state({
        "battles": game.tables["battles"],
        "battle_units": pl.DataFrame({
            "battle_id": ["battle-1"], "unit_id": ["gone"], "country_id": ["USA"], "side": ["SIDE_A"],
        }),
        "units": pl.DataFrame({"id": ["present"], "unit_type": ["army"], "strength": [5]}),
    })
    assert presenter.battle_force_summary(missing_unit, "battle-1", "USA") == []

    no_battle_id = _state({"battles": pl.DataFrame({"status": ["active"]})})
    assert presenter.battle_status(no_battle_id, "battle-1", "USA") is None


def test_relation_ranked_targets_stop_at_limit_and_posture_text_has_defaults():
    presenter = MilitaryPresenter()
    game = _state({
        "countries": pl.DataFrame({"id": ["USA", "CAN", "MEX"]}),
        "countries_relations": pl.DataFrame({
            "source": ["USA", "USA"], "target": ["CAN", "MEX"], "value": [-5.0, 2.0],
        }),
    })
    assert [row["country_tag"] for row in presenter.preferred_war_targets(game, "USA", limit=1)] == ["CAN"]
    assert presenter.force_posture_text(_state({"countries": pl.DataFrame({
        "id": ["USA"], "military_count": [1250], "money_reserves": [4500.0],
        "budget_research_ratio": [0.125],
    })}), "USA") == "Field strength 1 250 | Reserves $4 500 | Research 12.5%"


def test_battle_status_formats_defender_victory_and_origin_skips_foreign_governments():
    presenter = MilitaryPresenter()
    battle = _state({"battles": pl.DataFrame({
        "id": ["battle-1"], "attacker_side": ["USA"], "defender_side": ["CAN"],
        "status": ["concluded"], "victor_side": ["SIDE_B"],
    })})
    status = presenter.battle_status(battle, "battle-1", "CAN")
    assert status is not None and status.outcome_label == "Victory: CAN"

    game = _state({
        "regions": pl.DataFrame({"id": [1], "owner": ["USA"]}),
        "country_governments": pl.DataFrame([
            {"country_id": "CAN", "capital_region_id": 1},
            {"country_id": "USA", "capital_region_id": 1},
        ]),
    })
    assert presenter._strategic_weapon_origin(game, "USA", {})["id"] == 1


def test_movement_and_strategic_defense_previews_handle_invalid_or_unknown_inputs():
    presenter = MilitaryPresenter()
    assert presenter._movement_progress({
        "movement_progress": 0.35, "departed_at_minute": 10, "arrival_at_minute": 10,
    }, 20) == 0.35

    assert presenter.strategic_defense_estimate_for_region(_state(), "USA", 2) == {
        "target_region_id": 2, "covered_layers": [], "interception_probability": 0.0,
    }
    assert presenter.strategic_defense_estimate_for_region(_state({
        "regions": pl.DataFrame({"id": [1]}),
    }), "USA", 2) == {
        "target_region_id": 2, "covered_layers": [], "interception_probability": 0.0,
    }

    unknown_layer = _state({
        "regions": pl.DataFrame({"id": [2], "owner": ["CAN"]}),
        "missile_defense_layers": pl.DataFrame({"id": ["unknown"], "country_id": ["USA"], "layer": ["orbital"]}),
    })
    assert presenter.strategic_defense_estimate_for_region(unknown_layer, "USA", 2) == {
        "target_region_id": 2, "covered_layers": [], "interception_probability": 0.0,
    }
