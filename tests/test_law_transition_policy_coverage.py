from modules.base.systems.politics import law_transition_policy as policy


def _valid_inputs(**law_overrides):
    law = {
        "law_id": "labor",
        "value": "Old",
        "legal_authority": "government",
        "allowed_values_json": '["Old", "New"]',
        "change_cost": 10.0,
        "transition_minutes": 30,
        "cooldown_minutes": 60,
        "cooldown_until_minute": 0,
        "carry_over_rule": "carry_over",
        "effects_by_value_json": '{"New": [{"domain": "rights", "effect": "public_rights", "value": 0.25}]}',
    }
    law.update(law_overrides)
    return {
        "law": law,
        "government": {"crisis_status": "none"},
        "form_rule": {"law_permissions_json": '["*"]'},
        "target_value": "New",
        "now_minute": 100,
        "treasury": 50.0,
        "has_pending_transition": False,
        "crisis_active": False,
    }


def test_validation_rejects_empty_ids_unsupported_authority_and_unchanged_values():
    cases = (
        (_valid_inputs(law_id=""), "The requested law does not exist."),
        (
            _valid_inputs(legal_authority="parliament"),
            "The configured legal authority 'parliament' is not available for this action.",
        ),
        (_valid_inputs(), "The law already has the requested value."),
    )
    cases[-1][0]["target_value"] = " old "

    for arguments, expected_reason in cases:
        decision, reason = policy.validate_law_change(**arguments)
        assert decision is None
        assert reason == expected_reason


def test_validation_canonicalizes_legacy_carry_over_rules():
    decision, reason = policy.validate_law_change(
        **_valid_inputs(carry_over_rule="legacy_policy")
    )

    assert reason == ""
    assert decision is not None
    assert decision.carry_over_rule == "cancel_on_regime_change"


def test_effect_normalization_skips_invalid_shapes_and_clamps_valid_values():
    assert policy._normalize_effects({"domain": "rights"}) == []
    assert policy._normalize_effects(["not an effect"]) == []
    assert policy._normalize_effects(
        [
            {"domain": "", "effect": "public_rights", "value": 0.1},
            {"domain": "rights", "effect": "", "value": 0.1},
            {"domain": "rights", "effect": "public_rights", "value": "nan"},
        ]
    ) == []
    assert policy._normalize_effects(
        [{"domain": " RIGHTS ", "effect": "Public_Rights", "value": 7.5}]
    ) == [{"domain": "rights", "effect": "public_rights", "value": 1.0}]


def test_json_decoders_accept_native_values_and_reject_malformed_or_wrong_shapes():
    assert policy._decode_string_list([" New ", " ", 7]) == ["New", "7"]
    assert policy._decode_string_list("{malformed") == []
    assert policy._decode_string_list('{"value": "New"}') == []

    value = {"New": []}
    assert policy._decode_object(value) is value
    assert policy._decode_object("{malformed") == {}
    assert policy._decode_object("[]") == {}


def test_numeric_helpers_handle_non_finite_invalid_and_missing_values():
    for invalid in (None, "not numeric", 10**400):
        assert policy._finite_number(invalid) is None
    assert policy._finite_number(float("inf")) is None

    assert policy._finite_or_default(None, 2.5) == 2.5
    assert policy._finite_or_default("not numeric", 2.5) == 2.5
    assert policy._non_negative_int("not an integer", 4) == 4
