from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import polars as pl

from modules.base.systems.world.ai.battle_strategy_candidates import (
    BattleStrategyCandidateBuilder,
    BattleStrategyCandidateProvider,
)
from src.core.ai_framework import AITableContext, empty_candidates
from src.shared.actions import ActionSetBattleStrategy, GameAction


class BattleStrategyPolicy:
    """Suggests deterministic posture orders for AI-controlled battle forces."""

    id = "battle_strategy"
    required_tables = frozenset({"countries", "battles", "battle_units", "units"})
    cadence_days = 1

    def __init__(self, candidate_provider: BattleStrategyCandidateProvider | None = None) -> None:
        self._candidate_provider = (
            candidate_provider if candidate_provider is not None else BattleStrategyCandidateBuilder()
        )

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        candidates = self._candidate_provider.build(
            context,
            policy_id=self.id,
            cadence_days=self.cadence_days,
        )
        return pl.DataFrame(candidates).lazy() if candidates else self._empty_candidates()

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        if str(row.get("action_kind") or "") != "set_battle_strategy":
            return None
        return ActionSetBattleStrategy(
            "ai_system",
            str(row.get("battle_id") or ""),
            str(row.get("strategy") or "hold"),
            country_tag=str(row.get("country_id") or ""),
            unit_type=str(row.get("unit_type") or "all"),
        )

    def _empty_candidates(self) -> pl.LazyFrame:
        return empty_candidates({
            "battle_id": pl.Utf8,
            "strategy": pl.Utf8,
            "unit_type": pl.Utf8,
        })
