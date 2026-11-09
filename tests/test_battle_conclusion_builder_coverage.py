from unittest.mock import Mock

from modules.base.systems.military.battle_conclusion_builder import (
    BattleConclusionBuilder,
)
from modules.base.systems.military.battle_victory_finalizer import (
    BattleEndedEventRequest,
    ConcludedBattleRowRequest,
)


def test_existing_battle_row_applies_resolved_round_and_preserves_input() -> None:
    prior_row = {
        "side_a_strength": 100.0,
        "side_b_strength": 80.0,
        "side_a_losses": 2,
        "side_b_losses": 1,
        "round": 4,
    }
    builder = BattleConclusionBuilder(snapshots=Mock())

    concluded = builder.build_concluded_battle_row(
        ConcludedBattleRowRequest(
            prior_row=prior_row,
            battle_id="battle-1",
            region_id=12,
            metadata={
                "round_resolved": True,
                "side_a_strength": 90,
                "side_b_strength": 70,
                "previous_a": 100,
                "previous_b": 75,
            },
            now=250,
            victor_side="SIDE_A",
        )
    )

    assert prior_row["side_a_strength"] == 100.0
    assert concluded["side_a_strength"] == 90.0
    assert concluded["side_b_strength"] == 70.0
    assert concluded["balance"] == 0.5625
    assert concluded["side_a_losses"] == 12
    assert concluded["side_b_losses"] == 6
    assert concluded["round"] == 5
    assert concluded["status"] == "concluded"
    assert concluded["updated_at_minute"] == 250
    assert concluded["concluded_at_minute"] == 250
    assert concluded["victor_side"] == "SIDE_A"


def test_existing_battle_row_skips_round_updates_when_no_round_was_resolved() -> None:
    prior_row = {"side_a_strength": 100.0, "side_b_strength": 80.0, "round": 2}
    builder = BattleConclusionBuilder(snapshots=Mock())

    concluded = builder.build_concluded_battle_row(
        ConcludedBattleRowRequest(
            prior_row=prior_row,
            battle_id="battle-1",
            region_id=12,
            metadata={"round_resolved": False},
            now=250,
            victor_side="SIDE_B",
        )
    )

    assert concluded["side_a_strength"] == 100.0
    assert concluded["side_b_strength"] == 80.0
    assert concluded["round"] == 2
    assert concluded["status"] == "concluded"
    assert concluded["victor_side"] == "SIDE_B"


def test_new_concluded_battle_row_delegates_snapshot_projection() -> None:
    snapshots = Mock()
    snapshots.build_battle_row.return_value = {"id": "battle-2"}
    builder = BattleConclusionBuilder(snapshots=snapshots)

    concluded = builder.build_concluded_battle_row(
        ConcludedBattleRowRequest(
            prior_row={},
            battle_id="battle-2",
            region_id=8,
            metadata={
                "war_id": "war-2",
                "mode": "positional",
                "side_a_tags": ["AAA"],
                "side_b_tags": ["BBB"],
                "side_a_strength": 40,
                "side_b_strength": 20,
                "previous_a": 50,
                "previous_b": 25,
                "round_resolved": True,
            },
            now=300,
            victor_side="SIDE_A",
        )
    )

    row_request = snapshots.build_battle_row.call_args.args[0]
    assert row_request.battle_id == "battle-2"
    assert row_request.war_id == "war-2"
    assert row_request.side_a_tags == frozenset({"AAA"})
    assert row_request.side_b_tags == frozenset({"BBB"})
    assert row_request.side_a_losses == 10
    assert row_request.side_b_losses == 5
    assert row_request.round_number == 1
    assert concluded["status"] == "concluded"


def test_battle_ended_event_uses_countries_from_the_concluded_row() -> None:
    event = BattleConclusionBuilder.build_battle_ended_event(
        BattleEndedEventRequest(
            battle_id="battle-3",
            victor="AAA",
            region_id=7,
            now=400,
            concluded_row={
                "victor_side": "SIDE_A",
                "attacker_side": "AAA,CCC",
                "defender_side": "BBB",
                "side_a_losses": 3,
                "side_b_losses": 5,
            },
        )
    )

    assert event.participant_countries == ("AAA", "BBB", "CCC")
    assert event.side_a_country_ids == ("AAA", "CCC")
    assert event.side_b_country_ids == ("BBB",)
    assert event.side_a_losses == 3
    assert event.side_b_losses == 5
    assert event.concluded_at_minute == 400
