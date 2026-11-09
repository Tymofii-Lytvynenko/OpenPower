from __future__ import annotations

import polars as pl

from modules.base.systems.politics.identity_policy_system import IdentityPolicySystem
from src.shared.actions import ActionSetCountryIdentityPolicy
from src.shared.state import GameState


def _action(
    *,
    identity_type: str = "language",
    identity_id: str = "english",
    status: str = "legal",
) -> ActionSetCountryIdentityPolicy:
    return ActionSetCountryIdentityPolicy(
        player_id="USA",
        country_tag="USA",
        identity_type=identity_type,
        identity_id=identity_id,
        status=status,
    )


def _state_with_group() -> GameState:
    return GameState(
        tables={
            "country_identity_groups": pl.DataFrame(
                [
                    {
                        "country_id": "USA",
                        "identity_type": "language",
                        "identity_id": "english",
                        "legal_status": "legal",
                        "population_share": 100.0,
                        "is_other_bucket": False,
                    }
                ]
            )
        }
    )


def test_update_ignores_policy_actions_before_identity_groups_are_available():
    state = GameState()
    state.current_actions = [_action()]

    IdentityPolicySystem().update(state, 0.0)

    assert state.journal.command_results == []


def test_policy_update_rejects_invalid_type_and_skips_optional_tables():
    state = _state_with_group()
    state.current_actions = [_action(identity_type="ethnicity")]

    IdentityPolicySystem().update(state, 0.0)

    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "Identity type" in state.journal.command_results[-1]["reason"]


def test_policy_update_rejects_empty_identity_and_unsupported_status():
    state = _state_with_group()
    state.current_actions = [_action(identity_id="", status="unsupported")]

    IdentityPolicySystem().update(state, 0.0)

    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "Choose a listed identity group" in state.journal.command_results[-1]["reason"]


def test_policy_update_rejects_group_missing_from_country_data():
    state = _state_with_group()
    state.current_actions = [_action(identity_id="not-listed")]

    IdentityPolicySystem().update(state, 0.0)

    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "not present" in state.journal.command_results[-1]["reason"]


def test_reapplying_the_current_identity_status_is_idempotent():
    state = _state_with_group()
    state.current_actions = [_action(status="legal")]

    IdentityPolicySystem().update(state, 0.0)

    assert state.journal.command_results[-1]["status"] == "applied"
    assert "already has this status" in state.journal.command_results[-1]["reason"]


def test_identity_share_defaults_to_zero_for_unparseable_values():
    assert IdentityPolicySystem._share("not-a-percentage") == 0.0
