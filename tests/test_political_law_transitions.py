from __future__ import annotations

import json

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from src.shared.actions import ActionChangePoliticalLaw
from src.shared.events import EventPoliticalLawTransitionResolved, EventPoliticalLawTransitionScheduled
from src.shared.state import GameState


def test_law_change_stays_pending_until_due_then_applies_declared_effects() -> None:
    state = _state()
    state.current_actions = [ActionChangePoliticalLaw("player-1", "AAA", "labor", "New")]
    system = PoliticalLifecycleSystem()

    system.update(state, 0.0)

    law = state.get_table("country_laws").row(0, named=True)
    transition = state.get_table("law_transitions").row(0, named=True)
    assert law["value"] == "Old"
    assert transition["status"] == "scheduled"
    assert transition["effective_at_minute"] == 110
    assert state.get_table("countries")["money_reserves"][0] == 75.0
    assert any(isinstance(event, EventPoliticalLawTransitionScheduled) for event in state.events)
    assert state.journal.command_results[-1]["status"] == "applied"

    state.time.total_minutes = 110
    state.current_actions = []
    state.events = []
    system.update(state, 0.0)

    law = state.get_table("country_laws").row(0, named=True)
    transition = state.get_table("law_transitions").row(0, named=True)
    effect = state.get_table("political_effects").row(0, named=True)
    assert law["value"] == "New"
    assert law["cooldown_until_minute"] == 210
    assert transition["status"] == "effective"
    assert effect["source_id"] == transition["id"]
    assert effect["domain"] == "rights"
    assert effect["effect"] == "public_rights"
    assert effect["value"] == 0.1
    assert any(isinstance(event, EventPoliticalLawTransitionResolved) for event in state.events)
    assert state.get_table("political_history").height == 2
    assert state.get_table("messages").height >= 2

    effect_count = state.get_table("political_effects").height
    history_count = state.get_table("political_history").height
    system.update(state, 0.0)
    assert state.get_table("political_effects").height == effect_count
    assert state.get_table("political_history").height == history_count


def test_unauthorized_or_invalid_law_actions_are_rejected_without_mutation() -> None:
    for actor, target, permissions, crisis in (
        ("player-2", "New", '["*"]', "none"),
        ("player-1", "Unknown", '["*"]', "none"),
        ("player-1", "New", '["other_law"]', "none"),
        ("player-1", "New", '["*"]', "government_crisis"),
    ):
        state = _state(permissions_json=permissions, crisis_status=crisis)
        state.current_actions = [ActionChangePoliticalLaw(actor, "AAA", "labor", target)]

        PoliticalLifecycleSystem().update(state, 0.0)

        assert state.get_table("country_laws")["value"][0] == "Old"
        assert state.get_table("law_transitions").is_empty()
        assert state.get_table("countries")["money_reserves"][0] == 100.0
        assert state.journal.command_results[-1]["status"] == "rejected"
        assert state.journal.command_results[-1]["reason"]


def test_law_change_rejects_pending_duplicate_and_insufficient_funds() -> None:
    state = _state(money=10.0)
    state.current_actions = [ActionChangePoliticalLaw("player-1", "AAA", "labor", "New")]

    PoliticalLifecycleSystem().update(state, 0.0)

    assert state.get_table("law_transitions").is_empty()
    assert state.get_table("countries")["money_reserves"][0] == 10.0
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "cost" in state.journal.command_results[-1]["reason"].lower()

    state = _state()
    state.current_actions = [
        ActionChangePoliticalLaw("player-1", "AAA", "labor", "New"),
        ActionChangePoliticalLaw("player-1", "AAA", "labor", "New"),
    ]
    PoliticalLifecycleSystem().update(state, 0.0)
    assert state.get_table("law_transitions").height == 1
    assert [row["status"] for row in state.journal.command_results[-2:]] == ["applied", "rejected"]


def test_resolved_change_enforces_cooldown_and_effect_bounds() -> None:
    state = _state()
    state.update_table(
        "country_laws",
        state.get_table("country_laws").with_columns(
            pl.lit(
                json.dumps(
                    {
                        "New": [
                            {"domain": "rights", "effect": "public_rights", "value": 7.5}
                        ]
                    }
                )
            ).alias("effects_by_value_json")
        ),
    )
    system = PoliticalLifecycleSystem()
    state.current_actions = [ActionChangePoliticalLaw("player-1", "AAA", "labor", "New")]
    system.update(state, 0.0)

    state.time.total_minutes = 110
    state.current_actions = []
    system.update(state, 0.0)
    assert state.get_table("political_effects")["value"][0] == 1.0

    state.time.total_minutes = 111
    state.current_actions = [ActionChangePoliticalLaw("player-1", "AAA", "labor", "Old")]
    system.update(state, 0.0)
    assert state.get_table("country_laws")["value"][0] == "New"
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "cooldown" in state.journal.command_results[-1]["reason"].lower()


def test_due_transition_obeys_explicit_government_change_carry_over_rule() -> None:
    for carry_over_rule, expected_status, expected_value in (
        ("cancel_on_regime_change", "cancelled", "Old"),
        ("carry_over", "effective", "New"),
    ):
        state = _state()
        state.update_table(
            "country_laws",
            state.get_table("country_laws").with_columns(
                pl.lit(carry_over_rule).alias("carry_over_rule")
            ),
        )
        system = PoliticalLifecycleSystem()
        state.current_actions = [ActionChangePoliticalLaw("player-1", "AAA", "labor", "New")]
        system.update(state, 0.0)
        state.update_table(
            "country_governments",
            state.get_table("country_governments").with_columns(
                pl.lit("military-led state").alias("government_form_id")
            ),
        )
        state.time.total_minutes = 110
        state.current_actions = []
        system.update(state, 0.0)

        assert state.get_table("law_transitions")["status"][0] == expected_status
        assert state.get_table("country_laws")["value"][0] == expected_value


def test_legacy_seeded_law_gets_actionable_metadata_without_replacing_its_value() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["AAA"], "money_reserves": [100.0]}),
            "country_laws": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "law_id": ["party_system"],
                    "value": ["Managed competition"],
                }
            ),
        }
    )
    ensure_base_tables(state)

    PoliticalLifecycleSystem().update(state, 0.0)

    law = state.get_table("country_laws").row(0, named=True)
    assert law["value"] == "Managed competition"
    assert "Competitive" in json.loads(law["allowed_values_json"])
    assert "Managed competition" in json.loads(law["allowed_values_json"])
    assert law["transition_minutes"] == 43_200
    assert json.loads(law["effects_by_value_json"])["Competitive"][0]["domain"] == "rights"


def test_explicit_empty_value_catalog_and_invalid_negative_cost_are_not_made_permissive() -> None:
    state = _state()
    state.update_table(
        "country_laws",
        state.get_table("country_laws").with_columns(
            pl.lit("[]").alias("allowed_values_json"),
        ),
    )
    state.current_actions = [ActionChangePoliticalLaw("player-1", "AAA", "labor", "New")]

    PoliticalLifecycleSystem().update(state, 0.0)

    law = state.get_table("country_laws").row(0, named=True)
    assert json.loads(law["allowed_values_json"]) == ["Old"]
    assert state.get_table("law_transitions").is_empty()
    assert state.get_table("countries")["money_reserves"][0] == 100.0
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "not allowed" in state.journal.command_results[-1]["reason"].lower()

    state = _state()
    state.update_table(
        "country_laws",
        state.get_table("country_laws").with_columns(pl.lit(-5.0).alias("change_cost")),
    )
    state.current_actions = [ActionChangePoliticalLaw("player-1", "AAA", "labor", "New")]
    PoliticalLifecycleSystem().update(state, 0.0)
    assert state.get_table("law_transitions").is_empty()
    assert state.get_table("countries")["money_reserves"][0] == 100.0
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "cost is invalid" in state.journal.command_results[-1]["reason"].lower()


def _state(
    *,
    permissions_json: str = '["*"]',
    crisis_status: str = "none",
    money: float = 100.0,
) -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["AAA"], "money_reserves": [money]}),
            "country_governments": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "government_type": ["Transitional republic"],
                    "government_form_id": ["transitional republic"],
                    "ruling_party_id": ["incumbent"],
                    "election_eligible": [False],
                    "initialized": [True],
                    "crisis_status": [crisis_status],
                }
            ),
            "government_form_rules": pl.DataFrame(
                {
                    "government_form_id": ["transitional republic"],
                    "display_name": ["Transitional republic"],
                    "election_eligible": [False],
                    "election_interval_minutes": [0],
                    "law_permissions_json": [permissions_json],
                }
            ),
            "country_laws": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "law_id": ["labor"],
                    "group_name": ["Labor"],
                    "title": ["Labor law"],
                    "status": ["Active"],
                    "value": ["Old"],
                    "notes": [""],
                    "allowed_values_json": [json.dumps(["Old", "New"])],
                    "transition_minutes": [10],
                    "legal_authority": ["government"],
                    "change_cost": [25.0],
                    "cooldown_minutes": [100],
                    "cooldown_until_minute": [0],
                    "effects_by_value_json": [json.dumps({"New": [{"domain": "rights", "effect": "public_rights", "value": 0.1}]})],
                }
            ),
        },
        globals={"player_country_map": {"player-1": "AAA"}, "tick": 1},
    )
    state.time.total_minutes = 100
    ensure_base_tables(state)
    return state
