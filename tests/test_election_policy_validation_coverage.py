from __future__ import annotations

from modules.base.systems.politics.election_policy import (
    MAX_GAME_MINUTE,
    _decode_override_rules,
    _finite_optional,
    _ratio,
    _strict_int,
    resolve_election,
    validate_election_override,
)


def _valid_args(
    override_type: str = "postpone",
    *,
    rule_updates: dict | None = None,
    government_updates: dict | None = None,
    **argument_updates,
) -> dict:
    rule = {
        "type": override_type,
        "minimum_duration_days": 1,
        "maximum_duration_days": 30,
        "minimum_notice_days": 1,
        "cooldown_days": 0,
        "cost": 0.0,
        "approval_delta": 0.0,
        "stability_delta": 0.0,
    }
    rule.update(rule_updates or {})
    government = {
        "election_eligible": True,
        "crisis_status": "none",
        "succession_party_id": "alpha",
    }
    government.update(government_updates or {})
    arguments = {
        "override_type": override_type,
        "duration_days": 2,
        "now_minute": 100,
        "current_election_minute": 10_000,
        "form_rule": {
            "election_eligible": True,
            "election_overrides_json": [rule],
        },
        "government": government,
        "treasury": 100.0,
        "party_ids": ["alpha"],
    }
    arguments.update(argument_updates)
    return arguments


def _assert_rejected(arguments: dict, reason_fragment: str) -> None:
    decision, reason = validate_election_override(**arguments)
    assert decision is None
    assert reason_fragment in reason


def test_override_validation_rejects_unsupported_disabled_and_foreign_authority_rules() -> None:
    _assert_rejected(_valid_args("unknown"), "not supported")
    _assert_rejected(
        _valid_args(rule_updates={"enabled": False}),
        "disabled",
    )
    _assert_rejected(
        _valid_args(rule_updates={"legal_authority": "court"}),
        "not available",
    )


def test_override_validation_rejects_invalid_dates_cooldown_and_effects() -> None:
    _assert_rejected(
        _valid_args(current_election_minute=None),
        "date is unavailable",
    )
    _assert_rejected(
        _valid_args(rule_updates={"cooldown_days": -1}),
        "dates are invalid",
    )
    _assert_rejected(
        _valid_args(last_override_at_minute="invalid"),
        "previous election override date is invalid",
    )
    _assert_rejected(
        _valid_args(rule_updates={"approval_delta": "invalid"}),
        "consequences are invalid",
    )


def test_override_validation_rejects_non_actionable_dates_and_unknown_successors() -> None:
    _assert_rejected(
        _valid_args(
            "accelerate",
            now_minute=9_500,
            current_election_minute=10_000,
        ),
        "cannot be accelerated",
    )
    _assert_rejected(
        _valid_args("suspend"),
        "would not change",
    )
    _assert_rejected(
        _valid_args(
            "succession",
            government_updates={"succession_party_id": "missing"},
        ),
        "succession party is unavailable",
    )
    _assert_rejected(
        _valid_args(current_election_minute=MAX_GAME_MINUTE),
        "supported game-date range",
    )


def test_override_validation_builds_a_decision_with_a_supported_date() -> None:
    decision, reason = validate_election_override(**_valid_args())

    assert reason == ""
    assert decision is not None
    assert decision.override_type == "postpone"
    assert decision.next_election_at_minute == 12_880


def test_election_numeric_and_rule_helpers_cover_fallback_inputs() -> None:
    assert _ratio(50.0) == 0.5
    assert _decode_override_rules([{"type": "postpone"}]) == [{"type": "postpone"}]
    assert _decode_override_rules("not-json") == []
    assert _strict_int(True) is None
    assert _strict_int("not-an-integer") is None
    assert _strict_int(1.5) is None
    assert _finite_optional("not-a-number") is None


def test_election_assigns_fallback_weights_when_all_support_is_zero() -> None:
    result = resolve_election(
        [
            {
                "party_id": "alpha",
                "support_share": 0.0,
                "organization": 0.0,
                "eligible": True,
            }
        ],
        ruling_party_id="alpha",
        approval=50.0,
        stability=50.0,
        form_rule={},
    )

    assert result.winner_party_id == "alpha"
    assert result.eligible_party_ids == ("alpha",)
