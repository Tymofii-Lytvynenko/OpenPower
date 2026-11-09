from __future__ import annotations

import json
import math

import polars as pl
import pytest

from modules.base.systems.politics.political_lifecycle_system import (
    PoliticalLifecycleSystem,
)
from src.shared.actions import (
    ActionChangePoliticalLaw,
    ActionResolvePoliticalCrisis,
    ActionSetElectionOverride,
)
from src.shared.state import GameState
from tests.test_political_election_overrides import _state as election_state
from tests.test_political_law_transitions import _state as law_state
from tests.test_political_regime_changes import _state as regime_state


def test_update_guards_and_malformed_json_helpers() -> None:
    system = PoliticalLifecycleSystem()
    system.update(GameState(), 0.0)

    state = regime_state(support=0.9)
    state.tables["countries"] = state.get_table("countries").head(0)
    system.update(state, 0.0)

    state = regime_state(support=0.9)
    state.tables["countries"] = pl.DataFrame({"country_name": ["AAA"]})
    system.update(state, 0.0)

    law = {
        "country_id": "AAA",
        "law_id": "party_system",
        "allowed_values_json": "{malformed",
    }
    assert PoliticalLifecycleSystem._validated_law_updates(
        [law], "AAA", (("party_system", "Competitive"),)
    ) == [(law, "Competitive")]
    assert PoliticalLifecycleSystem._decode_effects_by_value("{malformed") == {}
    assert PoliticalLifecycleSystem._decode_effects("{malformed") == []
    assert PoliticalLifecycleSystem._finite("invalid", 7.0) == 7.0


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("missing_country", "unavailable"),
        ("missing_crisis", "unavailable"),
        ("wrong_crisis_country", "another country"),
        ("missing_form_rules", "no regime-change rules"),
    ],
)
def test_regime_change_rejections_cover_stale_targets_and_server_notifications(
    case: str,
    expected_reason: str,
) -> None:
    state = regime_state(support=0.9)
    actor = "AI" if case == "missing_crisis" else "AAA"
    country_tag = "ZZZ" if case == "missing_country" else "AAA"
    crisis_id = "missing" if case == "missing_crisis" else "crisis-1"

    if case == "wrong_crisis_country":
        state.tables["political_crises"] = state.get_table(
            "political_crises"
        ).with_columns(pl.lit("BBB").alias("country_id"))
    elif case == "missing_form_rules":
        state.tables["country_governments"] = state.get_table(
            "country_governments"
        ).with_columns(pl.lit("unconfigured form").alias("government_form_id"))

    action = ActionResolvePoliticalCrisis(
        actor, country_tag, crisis_id, "constitutional"
    )
    PoliticalLifecycleSystem()._process_regime_change_actions(
        state, [action], state.time.total_minutes
    )

    result = state.journal.command_results[-1]
    assert result["status"] == "rejected"
    assert expected_reason in result["reason"]
    if case == "missing_crisis":
        assert state.get_table("messages").height == 1
        assert state.get_table("news_items").height == 1


@pytest.mark.parametrize("law_already_matches", [True, False])
def test_successful_regime_change_normalizes_indicators_and_keeps_active_crisis(
    law_already_matches: bool,
) -> None:
    state = regime_state(support=0.9)
    rules = state.get_table("government_form_rules").to_dicts()
    paths = json.loads(rules[0]["regime_change_paths_json"])
    paths[0]["minimum_approval"] = 0.5
    paths[0]["minimum_stability"] = 0.5
    state.tables["government_form_rules"] = state.get_table(
        "government_form_rules"
    ).with_columns(pl.lit(json.dumps(paths)).alias("regime_change_paths_json"))
    state.tables["countries"] = state.get_table("countries").with_columns(
        pl.when(pl.col("id") == "AAA")
        .then(pl.lit(0.6))
        .otherwise(pl.col("gvt_approval"))
        .alias("gvt_approval"),
        pl.when(pl.col("id") == "AAA")
        .then(pl.lit(0.5))
        .otherwise(pl.col("gvt_stability"))
        .alias("gvt_stability"),
        pl.when(pl.col("id") == "AAA")
        .then(pl.lit(0.1))
        .otherwise(pl.col("gvt_corruption"))
        .alias("gvt_corruption"),
    )
    state.tables["country_laws"] = state.get_table("country_laws").with_columns(
        pl.lit("Competitive" if law_already_matches else "Single-party").alias("value"),
        pl.lit(
            json.dumps(
                {
                    "Competitive": [
                        {"domain": "", "effect": "ignored", "value": 1.0},
                        {"domain": "rights", "effect": "ignored", "value": 0.0},
                    ]
                }
            )
        ).alias("effects_by_value_json"),
    )
    if not law_already_matches:
        crisis = state.get_table("political_crises").row(0, named=True)
        state.tables["political_crises"] = state.get_table(
            "political_crises"
        ).vstack(
            pl.DataFrame(
                [
                    {
                        **crisis,
                        "id": "crisis-2",
                        "crisis_type": "protest",
                        "created_at_minute": 6_000,
                        "status": "active",
                    }
                ],
                schema=state.get_table("political_crises").schema,
                strict=False,
            )
        )

    action = ActionResolvePoliticalCrisis(
        "AAA", "AAA", "crisis-1", "constitutional"
    )
    PoliticalLifecycleSystem()._process_regime_change_actions(
        state, [action], state.time.total_minutes
    )

    country = state.get_table("countries").filter(pl.col("id") == "AAA").row(
        0, named=True
    )
    assert country["gvt_approval"] == 64.0
    assert country["gvt_stability"] == 56.0
    assert country["gvt_corruption"] == 8.0
    assert state.get_table("country_governments").filter(
        pl.col("country_id") == "AAA"
    )["crisis_status"][0] == ("protest" if not law_already_matches else "none")
    if law_already_matches:
        assert state.get_table("political_effects").is_empty()
    else:
        assert state.get_table("political_effects").is_empty()


def test_law_action_rejection_and_due_transition_edge_cases(monkeypatch) -> None:
    state = law_state()
    state.current_actions = [
        ActionChangePoliticalLaw("AI", "AAA", "unknown-law", "New")
    ]
    system = PoliticalLifecycleSystem()
    system.update(state, 0.0)
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert state.get_table("messages").height == 1

    state = law_state()
    system = PoliticalLifecycleSystem()
    system._resolve_due_law_transitions(state, state.time.total_minutes)

    state = law_state()
    state.current_actions = [ActionChangePoliticalLaw("player-1", "AAA", "labor", "New")]
    system.update(state, 0.0)
    state.tables["country_laws"] = state.get_table("country_laws").head(0)
    system._resolve_due_law_transitions(state, 110)
    assert state.get_table("law_transitions")["status"][0] == "rejected"

    state = law_state()
    state.current_actions = [ActionChangePoliticalLaw("player-1", "AAA", "labor", "New")]
    system = PoliticalLifecycleSystem()
    system.update(state, 0.0)
    state.tables["country_laws"] = state.get_table("country_laws").with_columns(
        pl.lit("Changed after scheduling").alias("value")
    )
    system._resolve_due_law_transitions(state, 110)
    assert state.get_table("law_transitions")["status"][0] == "cancelled"

    state = law_state()
    state.current_actions = [ActionChangePoliticalLaw("player-1", "AAA", "labor", "New")]
    system = PoliticalLifecycleSystem()
    system.update(state, 0.0)
    state.tables["law_transitions"] = state.get_table("law_transitions").with_columns(
        pl.lit('[{"domain":"rights","effect":"public_rights","value":"force-nan"}]')
        .alias("effects_json")
    )
    original_finite = system._finite
    monkeypatch.setattr(
        system,
        "_finite",
        lambda value, default=0.0: (
            math.nan if value == "force-nan" else original_finite(value, default)
        ),
    )
    system._resolve_due_law_transitions(state, 110)
    assert state.get_table("political_effects").is_empty()


def test_election_override_can_create_missing_schedule_and_reject_missing_country() -> None:
    override = {
        "type": "postpone",
        "minimum_duration_days": 2,
        "maximum_duration_days": 30,
        "cost": 10.0,
        "cooldown_days": 10,
    }
    state = election_state([override])
    state.current_actions = [
        ActionSetElectionOverride("AI", "ZZZ", "postpone", 3)
    ]
    PoliticalLifecycleSystem().update(state, 0.0)
    assert "unavailable" in state.journal.command_results[-1]["reason"]

    state = election_state([override])
    state.tables["political_elections"] = state.get_table(
        "political_elections"
    ).head(0)
    state.current_actions = [
        ActionSetElectionOverride("player-1", "AAA", "postpone", 3)
    ]
    PoliticalLifecycleSystem().update(state, 0.0)
    election = state.get_table("political_elections").filter(
        pl.col("status") == "scheduled"
    ).row(0, named=True)
    assert election["override_type"] == "postpone"
    assert election["scheduled_at_minute"] == 5_000 + 3 * 24 * 60


def test_election_schedule_reconciliation_and_due_resolution_fallbacks() -> None:
    state = election_state([])
    system = PoliticalLifecycleSystem()
    system._resolve_due_elections(state, state.time.total_minutes)

    state = election_state([])
    state.tables["country_governments"] = state.get_table(
        "country_governments"
    ).with_columns(pl.lit(False).alias("election_eligible"))
    state.tables["political_elections"] = state.get_table(
        "political_elections"
    ).with_columns(pl.lit(900).alias("scheduled_at_minute"))
    system._resolve_due_elections(state, 1_000)
    assert state.get_table("political_elections")["status"][0] == "cancelled"

    state = election_state([])
    state.tables["political_parties"] = state.get_table(
        "political_parties"
    ).head(0)
    system._resolve_due_elections(state, 5_000)
    parties = state.get_table("political_parties")
    assert parties.height == 1
    assert parties["party_id"][0] == "alpha"


def test_election_schedule_reconciliation_supersedes_stale_rows_and_repairs_form() -> None:
    state = election_state([])
    governments = state.get_table("country_governments")
    stale_government = {
        **governments.row(0, named=True),
        "country_id": "",
    }
    state.tables["country_governments"] = governments.vstack(
        pl.DataFrame([stale_government], schema=governments.schema, strict=False)
    )
    state.tables["country_governments"] = state.get_table(
        "country_governments"
    ).with_columns(
        pl.when(pl.col("country_id") == "AAA")
        .then(pl.lit(6_000))
        .otherwise(pl.col("next_election_at_minute"))
        .alias("next_election_at_minute")
    )
    system = PoliticalLifecycleSystem()
    system._ensure_scheduled_elections(state, 1_000)
    elections = state.get_table("political_elections")
    assert elections.filter(pl.col("status") == "superseded").height == 1
    assert elections.filter(
        (pl.col("status") == "scheduled")
        & (pl.col("scheduled_at_minute") == 6_000)
    ).height == 1

    state = election_state([])
    state.tables["political_elections"] = state.get_table(
        "political_elections"
    ).with_columns(pl.lit("legacy form").alias("government_form_id"))
    system._ensure_scheduled_elections(state, 1_000)
    assert state.get_table("political_elections")["government_form_id"][0] == (
        "transitional republic"
    )
