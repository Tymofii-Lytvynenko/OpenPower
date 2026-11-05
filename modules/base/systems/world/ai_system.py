from __future__ import annotations

import json
from dataclasses import dataclass

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
from src.core.ai_framework import (
    AIEvaluation,
    AITableContext,
    DeclarativeAIFramework,
    empty_decision_frame,
)
from src.shared.events import EventNewDay
from src.shared.advisor_settings import ADVISOR_STATUS_COLUMNS
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE, SYSTEM_STATE_HELPER


@dataclass(frozen=True, slots=True)
class _PlayerAdvisorEvaluation:
    modes: dict[str, str]
    player_tag: str
    evaluation: AIEvaluation


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
                "advisor_recommendations",
            }
        ),
        writes=frozenset({"advisor_recommendations"}),
        phase=SystemPhase.STRATEGY,
    )

    _ADVISOR_POLICY_DOMAINS = {
        "economy": frozenset({"budget", "budget_survival", "economic_health"}),
        "politics": frozenset({"political_law", "political_election", "political_crisis"}),
        "military": frozenset({"procurement", "military_training", "military_roi"}),
    }
    _POLICY_DOMAIN = {
        policy_id: domain
        for domain, policy_ids in _ADVISOR_POLICY_DOMAINS.items()
        for policy_id in policy_ids
    }

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
        player_evaluation = self._evaluate_player_advisor(state, context)
        if player_evaluation is not None:
            self._apply_player_advisor(state, player_evaluation)
            self._last_decisions = pl.concat(
                [evaluation.decisions, player_evaluation.evaluation.decisions], how="diagonal_relaxed"
            ).head(256)
        else:
            self._last_decisions = evaluation.decisions.head(256)

    def _evaluate_player_advisor(
        self,
        state: GameState,
        context: AITableContext,
    ) -> _PlayerAdvisorEvaluation | None:
        countries = state.tables.get("countries")
        player_tag = str(context.player_tag or "").strip().upper()
        if not player_tag or countries is None or "id" not in countries.columns:
            return None

        rows = countries.filter(
            pl.col("id").cast(pl.Utf8, strict=False).str.strip_chars().str.to_uppercase()
            == player_tag
        )
        if rows.height != 1:
            return None

        modes = {
            domain: str(rows[column][0] or "manual").strip().lower()
            if column in rows.columns
            else "manual"
            for domain, column in ADVISOR_STATUS_COLUMNS.items()
        }
        active_domains = {
            domain for domain, mode in modes.items()
            if mode in {"automatic", "confirmations"}
        }
        policy_ids = frozenset().union(
            *(self._ADVISOR_POLICY_DOMAINS[domain] for domain in active_domains)
        ) if active_domains else frozenset()
        if not policy_ids:
            return None

        player_tables = dict(context.tables)
        player_tables["countries"] = rows
        player_context = AITableContext(
            tables=player_tables,
            day_ordinal=context.day_ordinal,
            total_minutes=context.total_minutes,
            date_text=context.date_text,
            globals=context.globals,
        )
        evaluation = self._framework.evaluate(player_context, policy_ids=policy_ids)
        return _PlayerAdvisorEvaluation(modes, player_tag, evaluation)

    def _apply_player_advisor(
        self,
        state: GameState,
        player_evaluation: _PlayerAdvisorEvaluation,
    ) -> None:
        modes = player_evaluation.modes
        player_tag = player_evaluation.player_tag
        evaluation = player_evaluation.evaluation
        recommendation_table = state.tables.get("advisor_recommendations")
        recommendation_rows = recommendation_table.to_dicts() if recommendation_table is not None else []
        known_ids = {str(row.get("id") or "") for row in recommendation_rows}
        changed = False

        for decision, action in evaluation.resolved_actions:
            if str(decision.get("country_id") or "").strip().upper() != player_tag:
                continue
            domain = self._POLICY_DOMAIN.get(str(decision.get("policy_id") or ""))
            mode = modes.get(domain or "", "manual")
            if mode == "automatic":
                state.current_actions.append(action)
            elif mode == "confirmations":
                changed |= self._queue_recommendation(
                    recommendation_rows,
                    known_ids,
                    player_tag,
                    domain,
                    decision,
                    action,
                    int(state.time.total_minutes),
                    str(state.globals.get("active_campaign_id") or ""),
                )

        if changed and recommendation_table is not None:
            state.update_table(
                "advisor_recommendations",
                pl.DataFrame(recommendation_rows, schema=recommendation_table.schema, strict=False),
            )

    @staticmethod
    def _queue_recommendation(
        rows: list[dict],
        known_ids: set[str],
        player_tag: str,
        domain: str | None,
        decision: dict,
        action,
        now: int,
        campaign_id: str,
    ) -> bool:
        import hashlib
        import json
        from dataclasses import asdict

        if not domain:
            return False
        action_payload = {
            "type": type(action).__name__,
            "fields": asdict(action),
        }
        encoded_action = json.dumps(action_payload, sort_keys=True, separators=(",", ":"))
        identity = "|".join((player_tag, str(decision.get("policy_id") or ""), encoded_action))
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        recommendation_id = f"advisor:ai:{player_tag}:{digest}"
        if recommendation_id in known_ids:
            return False

        policy_label = str(decision.get("policy_id") or "AI policy").replace("_", " ").title()
        reason_code = str(decision.get("reason_code") or "").replace("_", " ").strip()
        reason = f"Generated by the {policy_label} policy."
        if reason_code:
            reason += f" Decision reason: {reason_code}."
        rows.append({
            "id": recommendation_id,
            "campaign_id": campaign_id,
            "actor_country_id": player_tag,
            "title": f"{domain.title()} recommendation: {policy_label}",
            "reason": reason,
            "source_signal": f"ai_policy:{domain}:{decision.get('policy_id')}:{digest}",
            "affected_country_id": player_tag,
            "affected_region_id": 0,
            "confidence": 0.0,
            "urgency": 0.0,
            "expires_at_minute": now + 7 * 24 * 60,
            "optional_action_json": encoded_action,
            "status": "active",
            "created_at_minute": now,
            "stale_reason": "",
        })
        known_ids.add(recommendation_id)
        return True

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
