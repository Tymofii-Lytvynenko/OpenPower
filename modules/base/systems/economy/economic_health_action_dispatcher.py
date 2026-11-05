from __future__ import annotations

from typing import Protocol

from src.shared.actions import (
    ActionChangeEconomicPolicy,
    ActionRequestDebtContract,
    ActionRequestDebtRestructuring,
    ActionResolveDebtContract,
    ActionSetTax,
    GameAction,
)
from src.shared.state import GameState


class EconomicHealthActionHandler(Protocol):
    def _request_policy_change(
        self,
        state: GameState,
        action: ActionChangeEconomicPolicy,
        now: int,
    ) -> None: ...

    def _request_debt_contract(
        self,
        state: GameState,
        action: ActionRequestDebtContract,
        now: int,
    ) -> None: ...

    def _resolve_debt_contract(
        self,
        state: GameState,
        action: ActionResolveDebtContract,
        now: int,
    ) -> None: ...

    def _request_restructuring(
        self,
        state: GameState,
        action: ActionRequestDebtRestructuring,
        now: int,
    ) -> None: ...


class EconomicHealthActionDispatcher(Protocol):
    def dispatch(
        self,
        state: GameState,
        action: GameAction,
        now: int,
        handler: EconomicHealthActionHandler,
    ) -> None: ...


class DeterministicEconomicHealthActionDispatcher:
    """Route economic actions without owning their stateful request handling."""

    def dispatch(
        self,
        state: GameState,
        action: GameAction,
        now: int,
        handler: EconomicHealthActionHandler,
    ) -> None:
        if isinstance(action, ActionChangeEconomicPolicy):
            handler._request_policy_change(state, action, now)
        elif isinstance(action, ActionSetTax):
            handler._request_policy_change(
                state,
                ActionChangeEconomicPolicy(
                    player_id=action.player_id,
                    country_tag=action.country_tag,
                    policy_name="personal_income_tax_rate",
                    target_value=action.new_tax_rate,
                ),
                now,
            )
        elif isinstance(action, ActionRequestDebtContract):
            handler._request_debt_contract(state, action, now)
        elif isinstance(action, ActionResolveDebtContract):
            handler._resolve_debt_contract(state, action, now)
        elif isinstance(action, ActionRequestDebtRestructuring):
            handler._request_restructuring(state, action, now)
