from modules.base.systems.economy.economic_policy_transition import (
    DeterministicEconomicPolicyApplicationPlanner,
    DeterministicEconomicPolicyTransitionPlanner,
    EconomicPolicyApplicationInputs,
    EconomicPolicyTransitionInputs,
    _bounded,
)


def _inputs(**overrides):
    values = {
        "transition_id": "transition-1",
        "country_id": "AAA",
        "player_id": "player-1",
        "policy_name": "corporate_tax_rate",
        "previous_value": 0.2,
        "target_value": 0.25,
        "current_reserves": 1_000.0,
        "transition_cost_setting": 100.0,
        "delay_minutes_setting": 60,
        "cooldown_minutes_setting": 120,
        "cooldown_active": False,
        "now": 500,
    }
    values.update(overrides)
    return EconomicPolicyTransitionInputs(**values)


def test_transition_finalize_preserves_preparation_rejection():
    planner = DeterministicEconomicPolicyTransitionPlanner()
    draft = planner.prepare(_inputs(cooldown_active=True))

    plan = planner.finalize(draft, transition_id_exists=False)

    assert plan.row is None
    assert plan.rejection_reason == "Policy cooldown has not elapsed."


def test_transition_finalize_rejects_an_existing_deterministic_identity():
    planner = DeterministicEconomicPolicyTransitionPlanner()
    draft = planner.prepare(_inputs())

    plan = planner.finalize(draft, transition_id_exists=True)

    assert plan.row is None
    assert plan.rejection_reason == "A request with this deterministic identity already exists."


def test_application_plan_rejects_a_missing_country():
    plan = DeterministicEconomicPolicyApplicationPlanner().plan(
        EconomicPolicyApplicationInputs(
            country_exists=False,
            policy_name="corporate_tax_rate",
            supported_policies=frozenset({"corporate_tax_rate"}),
        )
    )

    assert not plan.should_apply
    assert plan.reason == "Country or policy no longer exists."


def test_bounded_number_uses_default_for_nonfinite_values():
    assert _bounded(float("nan"), 0.0, 1.0, default=0.4) == 0.4
