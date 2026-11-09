from __future__ import annotations

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.world.diplomatic_balance_system import DiplomaticBalanceSystem
from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from modules.base.systems.world.territory_system import TerritorySystem
from src.shared.actions import ActionAnnexRegion, ActionDeclareWar
from src.shared.events import (
    EventAggressiveExpansionUpdated,
    EventBattleUpdated,
    EventCoalitionChanged,
    EventNewDay,
    EventOccupationChanged,
    EventTerritoryOwnershipChanged,
    EventWarExhaustionUpdated,
    EventWarEnded,
    EventWarStarted,
)
from src.shared.state import GameState


def _state() -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA", "BBB", "CCC"],
                    "military_count": [100, 80, 40],
                    "gvt_stability": [60.0, 55.0, 50.0],
                }
            ),
            "regions": pl.DataFrame(
                {
                    "id": [1, 2, 3, 4],
                    "owner": ["AAA", "BBB", "BBB", "CCC"],
                    "controller": ["AAA", "AAA", "AAA", "CCC"],
                }
            ),
            "region_adjacency": pl.DataFrame(
                {"region_id": [1], "neighbor_region_id": [4]}
            ),
            "units": pl.DataFrame(
                {
                    "id": ["aaa-unit"],
                    "owner": ["AAA"],
                    "strength": [100],
                    "war_exhaustion_modifier": [1.0],
                }
            ),
        }
    )
    ensure_base_tables(state)
    state.update_table(
        "countries_wars",
        pl.DataFrame(
            {
                "id": ["war-1"],
                "side_a": [["AAA"]],
                "side_b": [["BBB"]],
                "status": ["active"],
                "casus_belli": [""],
                "leader_a": ["AAA"],
                "leader_b": ["BBB"],
                "created_at": ["2001-01-01 00:00"],
            }
        ),
    )
    return state


def _annex_state(annexer: str, defender: str) -> GameState:
    state = _state()
    countries = state.get_table("countries")
    vulnerable_neighbor = countries.filter(pl.col("id") == "CCC").row(0, named=True)
    vulnerable_neighbor.update(id="DDD", military_count=30)
    state.update_table(
        "countries",
        pl.concat(
            [
                countries,
                pl.DataFrame([vulnerable_neighbor], schema=countries.schema, strict=False),
            ]
        ),
    )

    regions = state.get_table("regions")
    template = regions.row(0, named=True)
    region_rows = []
    for region_id, owner in ((1, defender), (2, "CCC"), (3, "DDD")):
        row = dict(template, id=region_id, owner=owner, controller=owner)
        region_rows.append(row)
    state.update_table(
        "regions",
        pl.DataFrame(region_rows, schema=regions.schema, strict=False),
    )
    state.update_table(
        "region_adjacency",
        pl.DataFrame({"region_id": [1, 1], "neighbor_region_id": [2, 3]}),
    )
    state.update_table(
        "countries_treaties",
        pl.DataFrame(
            {
                "id": ["alliance-1"],
                "name": ["Defensive alliance"],
                "type": ["alliance"],
                "members": [[annexer, "DDD"]],
                "status": ["active"],
            }
        ),
    )
    state.update_table(
        "countries_wars",
        state.get_table("countries_wars").with_columns(pl.lit("").alias("casus_belli")),
    )
    state.events = [EventWarStarted("war-1", annexer, defender)]
    state.current_actions = [ActionAnnexRegion("server", 1, annexer)]
    return state


def test_offensive_occupations_trigger_a_defensive_neighbor_coalition():
    state = _state()
    state.events = [
        EventWarStarted("war-1", "AAA", "BBB"),
        EventOccupationChanged(2, "BBB", "AAA", "battle_resolution", 12),
        EventOccupationChanged(3, "BBB", "AAA", "battle_resolution", 12),
    ]

    DiplomaticBalanceSystem().update(state, 0.0)

    score = state.get_table("aggressive_expansion_scores").filter(
        pl.col("country_id") == "AAA"
    ).row(0, named=True)
    pact = state.get_table("coalition_pacts").filter(
        pl.col("primary_target_country_id") == "AAA"
    ).row(0, named=True)
    assert abs(score["threat_score"] - 0.65) < 1e-9
    assert pact["status"] == "active"
    assert pact["member_country_ids"] == ["CCC"]
    assert state.get_table("countries").filter(pl.col("id") == "CCC").item(0, "coalition_membership_count") == 1
    assert any(isinstance(event, EventAggressiveExpansionUpdated) for event in state.events)
    assert any(isinstance(event, EventCoalitionChanged) for event in state.events)

    state.update_table(
        "countries_wars",
        pl.DataFrame(schema=state.get_table("countries_wars").schema),
    )
    state.update_table(
        "regions",
        state.get_table("regions").with_columns(
            pl.when(pl.col("owner") == "BBB")
            .then(pl.col("owner"))
            .otherwise(pl.col("controller"))
            .alias("controller")
        ),
    )
    state.events = [EventWarEnded("war-1", "AAA", "BBB", ("AAA", "BBB"), "peace", 24)]
    DiplomaticBalanceSystem().update(state, 0.0)
    assert state.get_table("coalition_pacts").item(0, "status") == "dissolved"


def test_offensive_occupation_by_second_war_side_contributes_expansion_pressure():
    state = _state()
    state.events = [
        EventOccupationChanged(1, "AAA", "BBB", "battle_resolution", 12),
    ]

    DiplomaticBalanceSystem().update(state, 0.0)

    score = state.get_table("aggressive_expansion_scores").filter(
        pl.col("country_id") == "BBB"
    ).row(0, named=True)
    event = state.get_table("aggressive_expansion_events").filter(
        (pl.col("source_country_id") == "BBB")
        & (pl.col("target_country_id") == "AAA")
        & (pl.col("region_id") == 1)
    )
    assert score["threat_score"] == 0.15
    assert event.height == 1


@pytest.mark.parametrize(("annexer", "defender"), [("AAA", "BBB"), ("BBB", "AAA")])
def test_annexation_actions_from_either_war_side_form_coalitions_for_non_allied_neighbors(
    annexer: str,
    defender: str,
):
    state = _annex_state(annexer, defender)

    TerritorySystem().update(state, 0.0)
    DiplomaticBalanceSystem().update(state, 0.0)

    score = state.get_table("aggressive_expansion_scores").filter(
        pl.col("country_id") == annexer
    ).item(0, "threat_score")
    pact = state.get_table("coalition_pacts").filter(
        pl.col("primary_target_country_id") == annexer
    ).row(0, named=True)
    assert score == pytest.approx(0.6)
    assert pact["status"] == "active"
    assert pact["member_country_ids"] == ["CCC"]
    assert "DDD" not in pact["member_country_ids"]


def test_casualties_occupation_blockade_and_duration_raise_exhaustion_and_degrade_force():
    state = _state()
    state.time.total_minutes = 365 * 1440
    state.update_table(
        "regions",
        state.get_table("regions").with_columns(
            pl.when(pl.col("id") == 1)
            .then(pl.lit("BBB"))
            .otherwise(pl.col("controller"))
            .alias("controller")
        ),
    )
    state.update_table(
        "battles",
        pl.DataFrame({"id": ["battle-1"], "war_id": ["war-1"]}),
    )
    state.update_table(
        "battle_casualty_records",
        pl.DataFrame({"id": ["loss-1"], "battle_id": ["battle-1"], "country_id": ["AAA"], "losses": [30]}),
    )
    state.update_table(
        "naval_blockades",
        pl.DataFrame(
            {
                "id": ["blockade-1"],
                "target_country_id": ["AAA"],
                "blockading_country_id": ["BBB"],
                "blockade_percentage": [50.0],
                "status": ["active"],
            }
        ),
    )
    state.events = [EventNewDay(1, 1, 2002), EventBattleUpdated("battle-1", 2, "active")]

    DiplomaticBalanceSystem().update(state, 0.0)

    country = state.get_table("countries").filter(pl.col("id") == "AAA").row(0, named=True)
    exhaustion = state.get_table("war_exhaustion_states").filter(
        pl.col("country_id") == "AAA"
    ).row(0, named=True)
    assert exhaustion["casualties"] == 30
    assert exhaustion["occupied_regions"] == 1
    assert exhaustion["blockade_percentage"] == 50.0
    assert exhaustion["conflict_days"] == 365
    assert 40.0 < country["war_exhaustion"] < 50.0
    assert country["war_exhaustion_stability_penalty"] > 0.0
    assert country["active_war_count"] == 1
    assert state.get_table("units").item(0, "war_exhaustion_modifier") < 1.0
    assert any(isinstance(event, EventWarExhaustionUpdated) for event in state.events)


def test_occupied_region_index_normalizes_and_counts_owner_controller_pairs():
    regions = [
        {"owner": " aaa ", "controller": "bbb"},
        {"owner": "AAA", "controller": "BBB"},
        {"owner": "AAA", "controller": "CCC"},
        {"owner": "AAA", "controller": ""},
        {"owner": "", "controller": "BBB"},
    ]

    assert DiplomaticBalanceSystem._occupied_region_counts(regions) == {
        "AAA": {"BBB": 2, "CCC": 1}
    }


def test_expired_blockade_contributes_nothing_while_unexpired_blockade_remains():
    state = _state()
    state.time.total_minutes = 10
    state.update_table(
        "naval_blockades",
        pl.DataFrame(
            [
                {
                    "id": "expired",
                    "target_country_id": "AAA",
                    "blockading_country_id": "BBB",
                    "blockade_percentage": 70.0,
                    "status": "active",
                    "expires_at_minute": 10,
                },
                {
                    "id": "active",
                    "target_country_id": "AAA",
                    "blockading_country_id": "BBB",
                    "blockade_percentage": 20.0,
                    "status": "active",
                    "expires_at_minute": 11,
                },
                {
                    "id": "inactive",
                    "target_country_id": "AAA",
                    "blockading_country_id": "CCC",
                    "blockade_percentage": 80.0,
                    "status": "ended",
                    "expires_at_minute": 20,
                },
            ],
            schema=state.get_table("naval_blockades").schema,
            strict=False,
        ),
    )
    state.events = [EventNewDay(1, 1, 2001)]

    DiplomaticBalanceSystem().update(state, 0.0)

    exhaustion = state.get_table("war_exhaustion_states").filter(
        pl.col("country_id") == "AAA"
    ).row(0, named=True)
    assert exhaustion["blockade_percentage"] == 20.0


def test_multiple_wars_are_projected_independently_and_repeated_day_updates_are_idempotent():
    state = _state()
    wars = state.get_table("countries_wars")
    second_war = dict(
        wars.row(0, named=True),
        id="war-2",
        side_a=["AAA"],
        side_b=["CCC"],
        leader_b="CCC",
    )
    state.update_table(
        "countries_wars",
        pl.concat(
            [
                wars,
                pl.DataFrame([second_war], schema=wars.schema, strict=False),
            ]
        ),
    )
    system = DiplomaticBalanceSystem()
    state.events = [EventNewDay(1, 1, 2001)]

    system.update(state, 0.0)

    exhaustion = state.get_table("war_exhaustion_states")
    assert exhaustion.height == 4
    assert set(
        exhaustion.filter(pl.col("country_id") == "AAA").get_column("war_id").to_list()
    ) == {"war-1", "war-2"}
    assert state.get_table("countries").filter(pl.col("id") == "AAA").item(
        0, "active_war_count"
    ) == 2

    state.events = [EventNewDay(1, 1, 2001)]
    system.update(state, 0.0)
    assert not any(isinstance(event, EventWarExhaustionUpdated) for event in state.events)
    assert state.get_table("war_exhaustion_states").height == 4


def test_ended_war_cleanup_removes_exhaustion_rows_and_resets_country_and_unit_projections():
    state = _state()
    system = DiplomaticBalanceSystem()
    state.events = [EventNewDay(1, 1, 2001)]
    system.update(state, 0.0)
    assert state.get_table("war_exhaustion_states").height == 2

    state.update_table(
        "countries_wars",
        state.get_table("countries_wars").with_columns(pl.lit("ended").alias("status")),
    )
    state.events = [EventWarEnded("war-1", "AAA", "BBB", ("AAA", "BBB"), "peace", 24)]
    system.update(state, 0.0)

    assert state.get_table("war_exhaustion_states").is_empty()
    assert state.get_table("countries").get_column("active_war_count").to_list() == [0, 0, 0]
    assert state.get_table("countries").get_column("war_exhaustion").to_list() == [0.0, 0.0, 0.0]
    assert state.get_table("units").item(0, "war_exhaustion_modifier") == 1.0


def test_defensive_coalition_members_join_a_war_against_its_primary_target():
    state = _state()
    state.update_table(
        "countries_wars",
        pl.DataFrame(schema=state.get_table("countries_wars").schema),
    )
    state.update_table(
        "coalition_pacts",
        pl.DataFrame(
            {
                "id": ["coalition-AAA"],
                "leader_country_id": ["BBB"],
                "member_country_ids": [["BBB", "CCC"]],
                "primary_target_country_id": ["AAA"],
                "mutual_defense": [True],
                "threat_score": [0.7],
                "status": ["active"],
                "formed_at_minute": [0],
                "updated_at_minute": [0],
                "dissolved_at_minute": [0],
                "reason": ["test pact"],
            }
        ),
    )
    state.current_actions = [ActionDeclareWar("AAA", "AAA", "BBB", "unprovoked")]

    DiplomacySystem().update(state, 0.0)

    war = state.get_table("countries_wars").row(0, named=True)
    assert war["side_a"] == ["AAA"]
    assert war["side_b"] == ["BBB", "CCC"]


def test_expansion_pressure_ignores_non_offensive_occupations_and_non_annex_transfers():
    state = _state()
    state.events = [
        EventOccupationChanged(1, "BBB", "AAA", "battle_resolution", 12),
        EventOccupationChanged(2, "AAA", "AAA", "battle_resolution", 12),
        EventTerritoryOwnershipChanged(2, "BBB", "AAA", "province_transfer", 12),
    ]

    DiplomaticBalanceSystem()._update_expansion_pressure(state)

    assert state.get_table("aggressive_expansion_events").is_empty()


def test_expansion_event_recording_rejects_self_threats_and_deduplicates_ids():
    system = DiplomaticBalanceSystem()
    events = []
    known_ids = set()

    system._record_expansion_event(events, known_ids, "", "BBB", 1, "test", 0.2, 10)
    system._record_expansion_event(events, known_ids, "AAA", "AAA", 1, "test", 0.2, 10)
    system._record_expansion_event(events, known_ids, "AAA", "BBB", 1, "test", 0.2, 10)
    system._record_expansion_event(events, known_ids, "AAA", "BBB", 1, "test", 0.2, 10)

    assert len(events) == 1
    assert events[0]["source_country_id"] == "AAA"
    assert known_ids == {events[0]["id"]}


def test_active_coalition_updates_its_threat_score_while_war_pressure_continues():
    state = _state()
    pact_frame = state.get_table("coalition_pacts")
    state.update_table(
        "coalition_pacts",
        pl.DataFrame([{
            "id": "coalition-AAA",
            "leader_country_id": "CCC",
            "member_country_ids": ["CCC"],
            "primary_target_country_id": "AAA",
            "mutual_defense": True,
            "threat_score": 0.1,
            "status": "active",
            "formed_at_minute": 0,
            "updated_at_minute": 0,
            "dissolved_at_minute": 0,
            "reason": "previous pressure",
        }], schema=pact_frame.schema, strict=False),
    )

    DiplomaticBalanceSystem()._update_coalitions(state, {"AAA": 0.4}, 12)

    pact = state.get_table("coalition_pacts").row(0, named=True)
    assert pact["threat_score"] == pytest.approx(0.4)
    assert pact["updated_at_minute"] == 12
    assert any(isinstance(event, EventCoalitionChanged) for event in state.events)


def test_set_pact_leaves_identical_pacts_untouched_and_reactivates_changed_pacts():
    system = DiplomaticBalanceSystem()
    state = _state()
    unchanged = {
        "id": "coalition-AAA",
        "leader_country_id": "BBB",
        "member_country_ids": ["BBB", "CCC"],
        "primary_target_country_id": "AAA",
        "threat_score": 0.6,
        "status": "active",
    }
    pacts = [unchanged]

    system._set_pact(state, pacts, unchanged, "AAA", ["BBB", "CCC"], 0.6, 10, "same")

    assert state.events == []
    changed = dict(unchanged, status="dissolved", dissolved_at_minute=9, reason="ended")
    pacts[0] = changed

    system._set_pact(state, pacts, changed, "AAA", ["BBB", "CCC"], 0.6, 11, "renewed")

    assert changed["status"] == "active"
    assert changed["dissolved_at_minute"] == 0
    assert changed["updated_at_minute"] == 11
    assert changed["reason"] == "renewed"
    assert len(state.events) == 1 and isinstance(state.events[0], EventCoalitionChanged)


def test_missing_war_participant_is_skipped_during_exhaustion_projection():
    state = _state()
    wars = state.get_table("countries_wars")
    war = wars.row(0, named=True)
    war["side_a"] = ["AAA", "UNKNOWN"]
    state.update_table(
        "countries_wars",
        pl.DataFrame([war], schema=wars.schema, strict=False),
    )

    DiplomaticBalanceSystem()._update_war_exhaustion(state)

    projected_countries = set(state.get_table("war_exhaustion_states").get_column("country_id"))
    assert projected_countries == {"AAA", "BBB"}


def test_war_duration_normalizes_aware_timestamps_and_tag_parser_handles_other_inputs():
    system = DiplomaticBalanceSystem()

    aware_days = system._war_days({"created_at": "2001-01-01T00:00:00+03:00"}, 0)
    naive_days = system._war_days({"created_at": "2001-01-01T00:00:00"}, 0)

    assert aware_days == naive_days
    assert system._tags("AAA, BBB") == {"AAA", "BBB"}
    assert system._tags(None) == set()
