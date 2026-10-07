import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.world.recognition_policy import (
    ai_recognition_vote,
    eligible_voters,
    regional_economic_access_allowed,
)
from modules.base.systems.world.recognition_system import (
    DEFAULT_VOTING_WINDOW_DAYS,
    MINUTES_PER_DAY,
    RecognitionSystem,
)
from src.shared.actions import ActionCastRecognitionVote
from src.shared.events import (
    EventRecognitionCaseOpened,
    EventRecognitionCaseResolved,
    EventRecognitionWithdrawn,
    EventNewDay,
)
from src.shared.state import GameState


def _state() -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["CLAIM", "FORMER", "YES_A", "YES_B", "NO_C", "NON_UN"],
                    "un_member": [True, True, True, True, True, False],
                    "is_playable": [True, True, True, True, True, True],
                }
            ),
            "regions": pl.DataFrame(
                {"id": [1], "owner": ["CLAIM"], "controller": ["CLAIM"]}
            ),
            "annexation_claims": pl.DataFrame(
                {
                    "id": ["claim-1"],
                    "treaty_id": ["treaty-1"],
                    "region_id": [1],
                    "annexing_country_id": ["CLAIM"],
                    "political_owner_id": ["FORMER"],
                    "controller_at_start": ["CLAIM"],
                    "due_at_minute": [0],
                    "status": ["annexed"],
                }
            ),
            "countries_relations": pl.DataFrame(
                {
                    "source": ["YES_A", "YES_B", "NO_C"],
                    "target": ["CLAIM", "CLAIM", "CLAIM"],
                    "value": [20.0, 10.0, -80.0],
                }
            ),
        }
    )
    ensure_base_tables(state)
    state.globals["player_country_map"] = {
        "player-a": "YES_A",
        "player-b": "YES_B",
        "player-c": "NO_C",
    }
    return state


def test_case_captures_eligible_un_roster_once_and_opens_with_thirty_day_window():
    state = _state()
    system = RecognitionSystem()

    system.update(state, 0.0)
    system.update(state, 0.0)

    cases = state.tables["recognition_cases"]
    assert cases.height == 1
    case = cases.row(0, named=True)
    assert case["eligible_voters"] == ["NO_C", "YES_A", "YES_B"]
    assert case["deadline_at_minute"] == DEFAULT_VOTING_WINDOW_DAYS * MINUTES_PER_DAY
    assert any(isinstance(event, EventRecognitionCaseOpened) for event in state.events)
    assert len(state.tables["news_items"]) == 1


def test_scenario_can_override_voting_window_without_changing_the_default():
    state = _state()
    state.globals["recognition_voting_window_days"] = 12

    RecognitionSystem().update(state, 0.0)

    assert state.tables["recognition_cases"]["deadline_at_minute"][0] == 12 * MINUTES_PER_DAY
    assert state.globals["recognition_voting_window_days"] == 12


def test_replaced_votes_resolve_by_strict_roster_majority_and_create_country_statuses():
    state = _state()
    system = RecognitionSystem()
    system.update(state, 0.0)
    case_id = state.tables["recognition_cases"]["id"][0]

    state.current_actions = [
        ActionCastRecognitionVote("player-a", case_id, "YES_A", "no"),
        ActionCastRecognitionVote("player-a", case_id, "YES_A", "yes"),
        ActionCastRecognitionVote("player-b", case_id, "YES_B", "yes"),
        ActionCastRecognitionVote("player-c", case_id, "NO_C", "no"),
    ]
    system.update(state, 0.0)
    state.current_actions = []
    state.time.total_minutes = DEFAULT_VOTING_WINDOW_DAYS * MINUTES_PER_DAY
    system.update(state, 0.0)

    case = state.tables["recognition_cases"].row(0, named=True)
    assert case["status"] == "passed"
    assert (case["yes_votes"], case["no_votes"]) == (2, 1)
    status_by_country = {
        row["country_id"]: row["status"]
        for row in state.tables["regional_recognition_status"].to_dicts()
    }
    assert status_by_country == {
        "NO_C": "not_recognized",
        "YES_A": "recognized",
        "YES_B": "recognized",
    }
    assert any(isinstance(event, EventRecognitionCaseResolved) for event in state.events)
    assert state.tables["recognition_votes"].height == 3


def test_unauthorized_and_late_votes_do_not_change_vote_rows():
    state = _state()
    system = RecognitionSystem()
    system.update(state, 0.0)
    case_id = state.tables["recognition_cases"]["id"][0]

    state.current_actions = [ActionCastRecognitionVote("stranger", case_id, "YES_A", "yes")]
    system.update(state, 0.0)
    assert state.tables["recognition_votes"].is_empty()
    assert state.journal.command_results[-1]["status"] == "rejected"

    state.current_actions = [ActionCastRecognitionVote("player-a", case_id, "YES_A", "yes")]
    state.time.total_minutes = DEFAULT_VOTING_WINDOW_DAYS * MINUTES_PER_DAY
    system.update(state, 0.0)
    assert state.tables["recognition_votes"].is_empty()
    assert state.tables["recognition_cases"]["status"][0] == "rejected"


def test_region_control_reversal_withdraws_case_and_active_recognition():
    state = _state()
    system = RecognitionSystem()
    system.update(state, 0.0)
    case_id = state.tables["recognition_cases"]["id"][0]
    state.current_actions = [
        ActionCastRecognitionVote("player-a", case_id, "YES_A", "yes"),
        ActionCastRecognitionVote("player-b", case_id, "YES_B", "yes"),
    ]
    system.update(state, 0.0)
    state.current_actions = []
    state.time.total_minutes = DEFAULT_VOTING_WINDOW_DAYS * MINUTES_PER_DAY
    system.update(state, 0.0)

    state.update_table(
        "regions",
        state.tables["regions"].with_columns(pl.lit("FORMER").alias("controller")),
    )
    system.update(state, 0.0)

    assert state.tables["recognition_cases"]["status"][0] == "withdrawn"
    statuses = {
        row["country_id"]: row["status"]
        for row in state.tables["regional_recognition_status"].to_dicts()
    }
    assert statuses["YES_A"] == statuses["YES_B"] == "withdrawn"
    assert statuses["NO_C"] == "not_recognized"
    assert any(isinstance(event, EventRecognitionWithdrawn) for event in state.events)


def test_policy_uses_un_membership_relations_and_current_regional_access():
    state = _state()
    assert eligible_voters(state.tables["countries"], "CLAIM", "FORMER") == (
        "NO_C",
        "YES_A",
        "YES_B",
    )
    assert ai_recognition_vote(state, "YES_A", "CLAIM") == "yes"
    assert ai_recognition_vote(state, "NO_C", "CLAIM") == "no"
    assert regional_economic_access_allowed(state, 1, "CLAIM")
    assert not regional_economic_access_allowed(state, 1, "YES_A")

    state.update_table(
        "regional_recognition_status",
        pl.DataFrame(
            [
                {
                    "id": "case:YES_A",
                    "annexation_claim_id": "claim-1",
                    "case_id": "case",
                    "region_id": 1,
                    "country_id": "YES_A",
                    "claimant_id": "CLAIM",
                    "status": "recognized",
                    "withdrawn_at_minute": 0,
                }
            ]
        ),
    )
    assert not regional_economic_access_allowed(state, 1, "YES_A")

    state.update_table(
        "recognition_cases",
        pl.DataFrame(
            [
                {
                    "id": "case",
                    "region_id": 1,
                    "claimant_id": "CLAIM",
                    "status": "passed",
                }
            ]
        ),
    )
    assert regional_economic_access_allowed(state, 1, "YES_A")

    state.update_table(
        "recognition_cases",
        state.tables["recognition_cases"].with_columns(
            pl.lit("rejected").alias("status")
        ),
    )
    assert not regional_economic_access_allowed(state, 1, "YES_A")

    state.update_table(
        "recognition_cases",
        state.tables["recognition_cases"].with_columns(
            pl.lit("passed").alias("status")
        ),
    )
    state.update_table(
        "regional_recognition_status",
        state.tables["regional_recognition_status"].with_columns(
            pl.lit(1_440).alias("withdrawn_at_minute")
        ),
    )
    assert not regional_economic_access_allowed(state, 1, "YES_A")
    assert not regional_economic_access_allowed(state, 999, "YES_A")

    state.update_table(
        "regions",
        state.tables["regions"].with_columns(pl.lit("FORMER").alias("controller")),
    )
    assert not regional_economic_access_allowed(state, 1, "YES_A")


def test_ai_policy_uses_alliance_economic_interest_and_active_war_signals():
    state = _state()
    state.tables["countries_relations"] = pl.DataFrame(
        {"source": ["YES_A"], "target": ["CLAIM"], "value": [-40.0]}
    )
    state.tables["countries_treaties"] = pl.DataFrame(
        {
            "id": ["market"],
            "status": ["active"],
            "type": ["economic_partnership"],
            "members": [["YES_A", "CLAIM"]],
            "side_a": [["YES_A"]],
            "side_b": [["CLAIM"]],
        }
    )
    assert ai_recognition_vote(state, "YES_A", "CLAIM") == "yes"

    state.tables["countries_wars"] = pl.DataFrame(
        {"status": ["active"], "attacker_id": ["YES_A"], "defender_id": ["CLAIM"]}
    )
    assert ai_recognition_vote(state, "YES_A", "CLAIM") == "no"


def test_ai_votes_on_daily_boundary_through_same_roster_rules():
    state = _state()
    state.globals["player_country_map"] = {"human": "YES_A"}
    system = RecognitionSystem()
    system.update(state, 0.0)
    assert state.tables["recognition_votes"].height == 2

    state.events = [EventNewDay(day=2, month=1, year=2001)]
    system.update(state, 0.0)
    assert state.tables["recognition_votes"].height == 2
