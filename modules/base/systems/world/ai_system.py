from __future__ import annotations

import json

import polars as pl

from modules.base.systems.world.ai import (
    BattleStrategyPolicy,
    BudgetPolicy,
    BudgetSurvivalPolicy,
    CovertOperationsPolicy,
    DiplomacyPolicy,
    EconomicPolicy,
    InfrastructurePolicy,
    MigrationPolicy,
    MilitaryOperationsPolicy,
    MilitaryROIPolicy,
    MilitaryTrainingPolicy,
    PoliticalCrisisPolicy,
    PoliticalElectionPolicy,
    PoliticalLawPolicy,
    ProcurementPolicy,
    StrategicWarfarePolicy,
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
                "battle_units",
                "battle_force_postures",
                "unit_designs",
                "unit_training_facilities",
                "unit_training_orders",
                "production_orders",
                "unit_market_listings",
                "country_governments",
                "government_form_rules",
                "political_parties",
                "country_laws",
                "law_transitions",
                "political_elections",
                "political_crises",
                "political_history",
                "regional_infrastructure",
                "infrastructure_projects",
                "infrastructure_damage_records",
                "economic_policy_transitions",
                "debt_contracts",
                "migration_policies",
                "migration_policy_transitions",
                "migration_signals",
                "sphere_delegations",
                "covert_cells",
                "covert_missions",
                "research_tracks",
                "strategic_weapons",
                "strategic_launch_orders",
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
            BudgetSurvivalPolicy(),
            BattleStrategyPolicy(),
            EconomicPolicy(),
            CovertOperationsPolicy(),
            ProcurementPolicy(),
            MilitaryTrainingPolicy(),
            InfrastructurePolicy(),
            MigrationPolicy(),
            MilitaryROIPolicy(),
            MilitaryOperationsPolicy(),
            WarPolicy(),
            DiplomacyPolicy(),
            PoliticalLawPolicy(),
            PoliticalElectionPolicy(),
            PoliticalCrisisPolicy(),
            StrategicWarfarePolicy(),
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

        delegated_domains, delegated_targets, delegated_treaty_ids = self._delegation_context(state)
        context = AITableContext(
            tables=state.tables,
            day_ordinal=max(0, int(state.time.total_minutes) // 1440),
            total_minutes=int(state.time.total_minutes),
            date_text=str(state.time.date_str),
            player_tag=str(state.globals.get("player_tag") or ""),
            globals=state.globals,
            delegated_domains=delegated_domains,
            delegated_targets=delegated_targets,
            delegated_treaty_ids=delegated_treaty_ids,
        )
        evaluation = self._framework.evaluate(context)
        state.current_actions.extend(evaluation.actions)
        self._last_decisions = evaluation.decisions.head(256)

    @staticmethod
    def _delegated_domains(state: GameState) -> dict[str, frozenset[str]]:
        return AISystem._delegation_context(state)[0]

    @staticmethod
    def _delegation_context(
        state: GameState,
    ) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]], dict[str, frozenset[str]]]:
        table = state.tables.get("sphere_delegations")
        if table is None or table.is_empty():
            return {}, {}, {}
        governments = {
            str(row.get("country_id") or "").strip().upper(): str(row.get("ruling_party_id") or "").strip().casefold()
            for row in (state.tables.get("country_governments").to_dicts() if state.tables.get("country_governments") is not None else [])
        }
        parties = state.tables.get("political_parties")
        if parties is not None:
            for row in parties.to_dicts():
                country = str(row.get("country_id") or "").strip().upper()
                if bool(row.get("is_ruling")) and country and not governments.get(country):
                    governments[country] = str(row.get("party_id") or "").strip().casefold()
        treaties_table = state.tables.get("countries_treaties")
        treaty_by_id = {
            str(row.get("id") or ""): row
            for row in (treaties_table.to_dicts() if treaties_table is not None else [])
        }
        delegated: dict[str, set[str]] = {}
        unrestricted: dict[str, set[str]] = {}
        targets: dict[str, set[str]] = {}
        treaty_ids: dict[str, set[str]] = {}
        for row in table.to_dicts():
            country = str(row.get("owner_country_id") or "").strip().upper()
            if (
                not country
                or not bool(row.get("active"))
                or str(row.get("current_controller") or "").strip().lower() != "ai"
            ):
                continue
            scope_type = str(row.get("scope_type") or "country").strip().lower()
            scope_id = str(row.get("scope_id") or "").strip()
            if scope_type == "country" and scope_id.upper() != country:
                continue
            if scope_type == "party" and (not scope_id or governments.get(country) != scope_id.casefold()):
                continue
            sphere_members: set[str] = set()
            if scope_type == "sphere":
                treaty = treaty_by_id.get(scope_id)
                if treaty is None or str(treaty.get("status") or "active").strip().lower() != "active":
                    continue
                members = treaty.get("members") or []
                if isinstance(members, str):
                    try:
                        members = json.loads(members)
                    except (TypeError, ValueError):
                        members = []
                if not isinstance(members, (list, tuple, set)):
                    continue
                sphere_members = {str(item).strip().upper() for item in members if str(item).strip()}
                if country not in sphere_members or len(sphere_members) < 2:
                    continue
            if scope_type not in {"country", "party", "sphere"}:
                continue
            try:
                raw_authority = json.loads(row.get("authority_json") or "[]")
            except (TypeError, ValueError):
                continue
            if not isinstance(raw_authority, list):
                continue
            authority = {str(item).strip().lower() for item in raw_authority if str(item).strip()}
            if not authority:
                continue
            delegated.setdefault(country, set()).update(authority)
            if scope_type == "country":
                unrestricted.setdefault(country, set()).update(authority)
            elif scope_type == "sphere" and "diplomacy" in authority:
                targets.setdefault(country, set()).update(sphere_members - {country})
                treaty_ids.setdefault(country, set()).add(scope_id)
        for country, authority in unrestricted.items():
            if "diplomacy" in authority:
                targets.pop(country, None)
                treaty_ids.pop(country, None)
        return (
            {country: frozenset(domains) for country, domains in delegated.items() if domains},
            {country: frozenset(countries) for country, countries in targets.items()},
            {country: frozenset(ids) for country, ids in treaty_ids.items()},
        )
