"""Authoritative resolution for queued AI policy recommendations."""

from __future__ import annotations

import json
from dataclasses import is_dataclass
from typing import Any

import polars as pl

from modules.base.systems.world.authority_policy import player_controls_country
from src.shared.actions import (
    ActionBuildUnit,
    ActionBuyMarketUnit,
    ActionChangeEconomicPolicy,
    ActionChangePoliticalLaw,
    ActionQueueUnitProduction,
    ActionRequestDebtContract,
    ActionResolveAdvisorRecommendation,
    ActionResolveDebtContract,
    ActionResolvePoliticalCrisis,
    ActionSetElectionOverride,
    ActionTrainUnit,
    ActionUpdateBudget,
    GameAction,
)
from src.shared.determinism import DeterministicRuntime
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


_ALLOWED_RECOMMENDATION_ACTIONS = frozenset({
    ActionBuildUnit,
    ActionBuyMarketUnit,
    ActionChangeEconomicPolicy,
    ActionChangePoliticalLaw,
    ActionQueueUnitProduction,
    ActionRequestDebtContract,
    ActionResolveDebtContract,
    ActionResolvePoliticalCrisis,
    ActionSetElectionOverride,
    ActionTrainUnit,
    ActionUpdateBudget,
})
_ACTION_TYPES = {action_type.__name__: action_type for action_type in _ALLOWED_RECOMMENDATION_ACTIONS}


class AdvisorRecommendationSystem(ISystem):
    """Validates the player answer and executes only stored advisor policy actions."""

    access = SystemAccess(
        reads=frozenset({"advisor_recommendations"}),
        writes=frozenset({"advisor_recommendations"}),
        handles=frozenset({ActionResolveAdvisorRecommendation}),
        phase=SystemPhase.BOOTSTRAP + 1,
    )

    @property
    def id(self) -> str:
        return "base.advisor_recommendations"

    @property
    def dependencies(self) -> list[str]:
        return ["base.bootstrap"]

    def update(self, state: GameState, delta_time: float) -> None:
        actions = [
            action for action in state.current_actions
            if isinstance(action, ActionResolveAdvisorRecommendation)
        ]
        if not actions:
            return

        table = state.tables.get("advisor_recommendations")
        if table is None:
            for action in actions:
                self._record_result(state, action, "rejected", "Advisor recommendations are unavailable.", "")
            return

        rows = table.to_dicts()
        by_id = {str(row.get("id") or ""): row for row in rows}
        changed = False
        for action in actions:
            recommendation_id = str(action.recommendation_id or "").strip()
            row = by_id.get(recommendation_id)
            if row is None:
                self._record_result(state, action, "rejected", "The advisor recommendation is unavailable.", "")
                continue

            country = str(row.get("actor_country_id") or "").strip().upper()
            if not player_controls_country(state, action.player_id, country):
                self._record_result(state, action, "rejected", "The issuer does not control this advisor recommendation.", country)
                continue
            if str(row.get("status") or "").strip().lower() != "active":
                self._record_result(state, action, "rejected", "The advisor recommendation is no longer active.", country)
                continue

            if action.accept:
                resolved = self._deserialize_action(row.get("optional_action_json"))
                if resolved is None:
                    self._record_result(state, action, "rejected", "This advisor message has no supported action to accept.", country)
                    continue
                if not self._action_matches_country(state, resolved, country):
                    self._record_result(
                        state,
                        action,
                        "rejected",
                        "The stored action does not belong to this recommendation's country.",
                        country,
                    )
                    continue
                state.current_actions.append(resolved)
                row["status"] = "accepted"
                reason = "Advisor recommendation accepted."
            else:
                row["status"] = "dismissed"
                reason = "Advisor recommendation dismissed."
            changed = True
            self._record_result(state, action, "applied", reason, country)

        if changed:
            state.update_table(
                "advisor_recommendations",
                pl.DataFrame(rows, schema=table.schema, strict=False),
            )

    @staticmethod
    def _deserialize_action(value: Any) -> GameAction | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            payload = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        action_type = _ACTION_TYPES.get(str(payload.get("type") or ""))
        fields = payload.get("fields")
        if action_type is None or not isinstance(fields, dict):
            return None
        if str(fields.get("player_id") or "").strip().lower() != "ai_system":
            return None
        try:
            action = action_type(**fields)
        except (TypeError, ValueError):
            return None
        return action if is_dataclass(action) and isinstance(action, GameAction) else None

    @staticmethod
    def _action_matches_country(state: GameState, action: GameAction, country: str) -> bool:
        expected_country = str(country or "").strip().upper()
        if isinstance(action, ActionRequestDebtContract):
            return str(action.debtor_country_id or "").strip().upper() == expected_country
        if isinstance(action, ActionResolveDebtContract):
            contracts = state.tables.get("debt_contracts")
            if contracts is None or not {"id", "creditor_country_id"}.issubset(contracts.columns):
                return False
            contract = next(
                (row for row in contracts.to_dicts() if str(row.get("id") or "") == action.contract_id),
                None,
            )
            return bool(
                contract
                and str(contract.get("creditor_country_id") or "").strip().upper() == expected_country
            )

        action_country = getattr(action, "country_tag", None)
        if action_country is None:
            action_country = getattr(action, "buyer_country_tag", None)
        return bool(action_country) and str(action_country).strip().upper() == expected_country

    @staticmethod
    def _record_result(
        state: GameState,
        action: ActionResolveAdvisorRecommendation,
        status: str,
        reason: str,
        country: str,
    ) -> None:
        result_id = DeterministicRuntime(state.determinism).next_id(
            "advisor-recommendation-command", int(state.globals.get("tick", 0))
        )
        state.journal.append_command_result({
            "result_id": result_id,
            "action_type": type(action).__name__,
            "player_id": str(action.player_id),
            "status": status,
            "reason": reason,
            "game_minute": int(state.time.total_minutes),
            "country_id": country,
            "recommendation_id": str(action.recommendation_id or ""),
        })
