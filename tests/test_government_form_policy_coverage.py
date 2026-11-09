from __future__ import annotations

import polars as pl
import pytest

from modules.base.systems.politics import government_form_policy as policy
from src.shared.actions import ActionSetGovernmentForm
from src.shared.state import GameState
from tests.test_government_form_changes import _foreign_world, _world


def _action(**overrides) -> ActionSetGovernmentForm:
    values = {
        "player_id": "player",
        "country_tag": "AAA",
        "expected_form_id": "custom republic",
        "target_form_id": "single-party democracy",
        "expected_martial_law": True,
        "target_martial_law": True,
    }
    values.update(overrides)
    return ActionSetGovernmentForm(**values)


def _reason(
    state: GameState,
    action: ActionSetGovernmentForm | None = None,
    *,
    country: str = "AAA",
    now: int = 100,
) -> str:
    return policy._validate_government_form_change(state, action or _action(), country, now)


def _foreign_action(**overrides) -> ActionSetGovernmentForm:
    values = {
        "player_id": "player",
        "country_tag": "POL",
        "expected_form_id": "custom republic",
        "target_form_id": "single-party democracy",
        "expected_martial_law": False,
        "target_martial_law": False,
        "confirmed_foreign_change": True,
    }
    values.update(overrides)
    return ActionSetGovernmentForm(**values)


def test_validation_reports_missing_country_and_government_records() -> None:
    state, _ = _world()
    missing_government, _ = _world()
    missing_government.tables.pop("country_governments")
    ambiguous_government, _ = _world()
    governments = ambiguous_government.tables["country_governments"]
    ambiguous_government.update_table(
        "country_governments",
        pl.concat([governments, governments], how="vertical"),
    )

    assert "Select a country" in _reason(state, country="")
    assert "unavailable" in _reason(state, country="BBB")
    assert "government record is unavailable" in _reason(missing_government)
    assert "missing or ambiguous" in _reason(ambiguous_government)


def test_validation_rejects_invalid_martial_law_values_and_unchanged_forms() -> None:
    state, _ = _world()

    invalid_expected = _reason(state, _action(expected_martial_law="yes"))
    invalid_target = _reason(state, _action(target_martial_law="yes"))
    missing_target = _reason(state, _action(target_form_id=""))
    unchanged = _reason(state, _action(target_form_id="custom republic"))

    assert "expected martial-law state is invalid" in invalid_expected
    assert "requested martial-law state is invalid" in invalid_target
    assert "Select an available government form" in missing_target
    assert "already in effect" in unchanged


def test_foreign_change_requires_form_only_and_available_treaty_and_relation_data() -> None:
    martial_state, _ = _foreign_world(controlled_regions=3, at_war=False)
    missing_treaties, _ = _foreign_world(controlled_regions=3, at_war=False)
    missing_treaties.tables.pop("treaty_effects")
    missing_relations, _ = _foreign_world(controlled_regions=3, at_war=False)
    relations = missing_relations.tables["countries_relations"]
    missing_relations.update_table("countries_relations", relations.head(0))

    martial_reason = _reason(
        martial_state,
        _foreign_action(target_martial_law=True),
        country="POL",
    )
    treaty_reason = _reason(missing_treaties, _foreign_action(), country="POL")
    relation_reason = _reason(missing_relations, _foreign_action(), country="POL")

    assert "cannot change martial-law status" in martial_reason
    assert "treaty data is unavailable" in treaty_reason
    assert "relation data is unavailable" in relation_reason


def test_validation_rejects_missing_rules_crises_and_unavailable_party_data() -> None:
    missing_rules, _ = _world()
    missing_rules.tables.pop("government_form_rules")
    political_crisis, _ = _world()
    political_crisis.update_table(
        "country_governments",
        political_crisis.tables["country_governments"].with_columns(
            pl.lit("active").alias("crisis_status")
        ),
    )
    missing_party_columns, _ = _world()
    missing_party_columns.tables["political_parties"] = pl.DataFrame({"country_id": ["AAA"]})
    no_parties, _ = _world()
    no_parties.update_table(
        "political_parties", no_parties.tables["political_parties"].head(0)
    )
    ineligible_ruler, _ = _world()
    ineligible_ruler.update_table(
        "political_parties",
        ineligible_ruler.tables["political_parties"].with_columns(
            pl.lit(False).alias("eligible")
        ),
    )

    assert "rules are unavailable" in _reason(missing_rules)
    assert "during a political crisis" in _reason(political_crisis)
    assert "political-party data is unavailable" in _reason(missing_party_columns)
    assert "political-party data is unavailable" in _reason(no_parties)
    assert "ruling party is not eligible" in _reason(ineligible_ruler)


def test_validation_rejects_invalid_party_election_limits_and_overflow() -> None:
    invalid_party_limits, _ = _world()
    invalid_party_limits.update_table(
        "government_form_rules",
        invalid_party_limits.tables["government_form_rules"].with_columns(
            pl.lit(0).alias("minimum_eligible_parties")
        ),
    )
    invalid_election_rules, _ = _world()
    invalid_election_rules.update_table(
        "government_form_rules",
        invalid_election_rules.tables["government_form_rules"].with_columns(
            pl.lit(None, dtype=pl.Boolean).alias("election_eligible")
        ),
    )
    overflow, _ = _world()

    assert "invalid party-count limits" in _reason(invalid_party_limits)
    assert "invalid election rules" in _reason(invalid_election_rules)
    assert "exceeds the supported range" in _reason(overflow, now=2**63 - 1)


def test_validation_helpers_normalize_player_ids_and_require_bidirectional_relations() -> None:
    state, _ = _world()
    assert policy._player_country_tag(state, "player") == "AAA"

    state.globals["player_country_map"] = {}
    state.globals["player_tag"] = "BBB"
    assert policy._player_country_tag(state, "local_admin") == "BBB"
    assert policy._player_country_tag(state, "other-player") == "OTHER-PLAYER"

    assert not policy._has_relation_pair(state, "", "AAA")
    state.tables.pop("countries_relations", None)
    assert not policy._has_relation_pair(state, "AAA", "BBB")

    state.tables["countries_relations"] = pl.DataFrame({"source": ["AAA"]})
    assert not policy._has_relation_pair(state, "AAA", "BBB")
    state.tables["countries_relations"] = pl.DataFrame([
        {"source": "AAA", "target": "BBB", "value": 0.0},
        {"source": "BBB", "target": "AAA", "value": 0.0},
    ])
    assert policy._has_relation_pair(state, "AAA", "BBB")


def test_process_rejects_a_form_removed_after_validation(monkeypatch) -> None:
    state, _ = _world()
    action = _action()
    validate = policy._validate_government_form_change

    def validate_then_remove_rule(
        candidate: GameState,
        candidate_action: ActionSetGovernmentForm,
        country: str,
        now: int,
    ) -> str:
        reason = validate(candidate, candidate_action, country, now)
        if not reason:
            rules = candidate.tables["government_form_rules"]
            candidate.update_table(
                "government_form_rules",
                rules.filter(pl.col("government_form_id") != candidate_action.target_form_id),
            )
        return reason

    monkeypatch.setattr(policy, "_validate_government_form_change", validate_then_remove_rule)
    policy.process_government_form_change(state, action, 100)

    result = state.journal.command_results[-1]
    assert result["status"] == "rejected"
    assert "unavailable" in result["reason"]
