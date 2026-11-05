from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class EconomicPolicyTransitionInputs:
    transition_id: str
    country_id: str
    player_id: str
    policy_name: str
    previous_value: float
    target_value: float
    current_reserves: float
    transition_cost_setting: Any
    delay_minutes_setting: Any
    cooldown_minutes_setting: Any
    cooldown_active: bool
    now: int


@dataclass(frozen=True)
class EconomicPolicyTransitionDraft:
    inputs: EconomicPolicyTransitionInputs
    transition_cost: float
    delay_minutes: int
    cooldown_minutes: int
    rejection_reason: str | None = None


@dataclass(frozen=True)
class EconomicPolicyTransitionPlan:
    row: dict[str, Any] | None
    transition_cost: float
    rejection_reason: str | None = None


class EconomicPolicyTransitionPlanner(Protocol):
    def prepare(self, inputs: EconomicPolicyTransitionInputs) -> EconomicPolicyTransitionDraft: ...

    def finalize(
        self,
        draft: EconomicPolicyTransitionDraft,
        transition_id_exists: bool,
    ) -> EconomicPolicyTransitionPlan: ...


class DeterministicEconomicPolicyTransitionPlanner:
    def prepare(self, inputs: EconomicPolicyTransitionInputs) -> EconomicPolicyTransitionDraft:
        if inputs.cooldown_active:
            return EconomicPolicyTransitionDraft(
                inputs=inputs,
                transition_cost=0.0,
                delay_minutes=0,
                cooldown_minutes=0,
                rejection_reason="Policy cooldown has not elapsed.",
            )

        transition_cost = _bounded(inputs.transition_cost_setting, 0.0, 1_000_000_000_000.0)
        if inputs.current_reserves < transition_cost:
            return EconomicPolicyTransitionDraft(
                inputs=inputs,
                transition_cost=transition_cost,
                delay_minutes=0,
                cooldown_minutes=0,
                rejection_reason="Treasury cannot cover the configured policy transition cost.",
            )

        delay = int(_bounded(inputs.delay_minutes_setting, 0.0, 525_600.0, 1_440.0))
        cooldown = int(_bounded(inputs.cooldown_minutes_setting, 0.0, 5_256_000.0, 43_200.0))
        return EconomicPolicyTransitionDraft(
            inputs=inputs,
            transition_cost=transition_cost,
            delay_minutes=delay,
            cooldown_minutes=cooldown,
        )

    def finalize(
        self,
        draft: EconomicPolicyTransitionDraft,
        transition_id_exists: bool,
    ) -> EconomicPolicyTransitionPlan:
        if draft.rejection_reason is not None:
            return EconomicPolicyTransitionPlan(
                row=None,
                transition_cost=draft.transition_cost,
                rejection_reason=draft.rejection_reason,
            )

        inputs = draft.inputs
        if transition_id_exists:
            return EconomicPolicyTransitionPlan(
                row=None,
                transition_cost=draft.transition_cost,
                rejection_reason="A request with this deterministic identity already exists.",
            )

        reason = (
            f"Accepted at a one-time cost of {draft.transition_cost:.2f}; "
            "the policy takes effect at its persisted effective minute."
        )
        return EconomicPolicyTransitionPlan(
            row={
                "id": inputs.transition_id,
                "country_id": inputs.country_id,
                "player_id": inputs.player_id,
                "policy_name": inputs.policy_name,
                "previous_value": inputs.previous_value,
                "target_value": inputs.target_value,
                "transition_cost": draft.transition_cost,
                "created_at_minute": inputs.now,
                "effective_at_minute": inputs.now + draft.delay_minutes,
                "cooldown_until_minute": inputs.now + draft.delay_minutes + draft.cooldown_minutes,
                "status": "scheduled",
                "reason": reason,
            },
            transition_cost=draft.transition_cost,
        )


def _bounded(value: Any, minimum: float, maximum: float, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        number = default
    if not math.isfinite(number):
        number = default
    return min(max(number, minimum), maximum)
