from __future__ import annotations

import polars as pl

from modules.base.systems.world.ai import (
    BudgetPolicy,
    DiplomacyPolicy,
    MilitaryOperationsPolicy,
    ProcurementPolicy,
    WarPolicy,
)
from src.core.ai_framework import AITableContext, DeclarativeAIFramework, empty_decision_frame
from src.shared.events import EventNewDay
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE, SYSTEM_STATE_HELPER


class AISystem(ISystem):
    """Produces strategic commands from read-only gameplay table snapshots."""

    access = SystemAccess(
        reads=frozenset(
            {
                "countries",
                "regions",
                "region_adjacency",
                "units",
                "countries_relations",
                "countries_treaties",
                "pending_treaties",
                "treaty_effects",
                "countries_wars",
                "battles",
                "unit_designs",
                "production_orders",
                "unit_market_listings",
                "country_governments",
            }
        ),
        writes=frozenset(),
        phase=SystemPhase.STRATEGY,
    )

    runtime_state_contract = {
        "_framework": SYSTEM_STATE_HELPER,
        "_last_decisions": SYSTEM_STATE_CACHE,
    }

    def __init__(self) -> None:
        self._framework = DeclarativeAIFramework().register(
            BudgetPolicy(),
            ProcurementPolicy(),
            MilitaryOperationsPolicy(),
            WarPolicy(),
            DiplomacyPolicy(),
        )
        self._last_decisions = empty_decision_frame()

    @property
    def id(self) -> str:
        return "base.ai"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.bootstrap"]

    @property
    def last_decisions(self) -> pl.DataFrame:
        return self._last_decisions.clone()

    def update(self, state: GameState, delta_time: float) -> None:
        if state.time.is_paused or "countries" not in state.tables:
            return
        if not any(isinstance(event, EventNewDay) for event in state.events):
            return

        context = AITableContext(
            tables=state.tables,
            day_ordinal=max(0, int(state.time.total_minutes) // 1440),
            total_minutes=int(state.time.total_minutes),
            date_text=str(state.time.date_str),
            player_tag=str(state.globals.get("player_tag") or ""),
        )
        evaluation = self._framework.evaluate(context)
        state.current_actions.extend(evaluation.actions)
        self._last_decisions = evaluation.decisions.head(256)
