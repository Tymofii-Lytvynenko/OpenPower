"""Campaign setup, objective evaluation, delegation, and advisor state."""

from __future__ import annotations

import json
import math
from typing import Any

import polars as pl

from modules.base.schema import BASE_TABLE_SCHEMAS
from modules.base.systems.world.campaign_objective_policy import (
    ObjectiveMeasurementContext,
    measure_objective,
)
from src.shared.actions import ActionSetSphereDelegation, ActionStartCampaign
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_HELPER


_SUPPORTED_OBJECTIVES = frozenset(
    {
        "control_region", "region_control", "conquer_country", "country_conquest",
        "treaty_membership", "treaty_member", "resource_quantity",
        "resource_requirement", "resource", "gdp_per_capita", "gdp_pc",
        "resource_share", "resource_share_threshold", "strategic_weapon_construction",
        "build_strategic_weapon", "nuclear_capability", "population", "population_threshold",
        "population_total", "development", "development_threshold", "human_development", "strategic_weapon_use",
        "use_strategic_weapon", "research_level", "research",
    }
)
_SETUP_FIELDS = {
    "countries": frozenset({
        "gdp", "human_dev", "money_reserves", "military_count", "gvt_approval",
        "gvt_stability", "gvt_corruption", "economic_health", "inflation_rate",
        "unemployment_rate", "employment_rate", "budget_research_ratio",
        "budget_edu_ratio", "budget_health_ratio", "budget_infra_ratio",
    }),
    "regions": frozenset({"owner", "controller"}),
    "country_governments": frozenset({
        "government_type", "government_form_id", "ruling_party_id", "capital_region_id",
        "election_eligible", "next_election_at_minute", "martial_law",
    }),
    "countries_relations": frozenset({"value"}),
    "countries_treaties": frozenset({"members", "side_a", "side_b", "status"}),
    "research_tracks": frozenset({"funding_ratio", "progress", "priority", "focus", "research_level"}),
    "strategic_weapons": frozenset({"quantity", "ready", "operational", "program_level"}),
}
_SETUP_KEYS = {
    "countries": ("id",),
    "regions": ("id",),
    "country_governments": ("country_id",),
    "countries_relations": ("source", "target"),
    "countries_treaties": ("id",),
    "research_tracks": ("id",),
    "strategic_weapons": ("id",),
}
_DELEGATION_AUTHORITY = frozenset({
    "diplomacy", "economy", "infrastructure", "migration", "military", "politics", "research"
})
_RECOMMENDATION_WINDOW_MINUTES = 30 * 24 * 60


class CampaignSetupSystem(ISystem):
    """Applies scenario setup before domain systems run their first update."""

    runtime_state_contract = {"_processor": SYSTEM_STATE_HELPER}

    access = SystemAccess(
        reads=frozenset({
            "countries", "regions", "campaign_scenarios", "campaigns", "objectives",
            "countries_relations", "countries_treaties", "country_governments", "political_parties",
            "research_tracks", "strategic_weapons",
            "sphere_delegations",
        }),
        writes=frozenset({
            "countries", "regions", "countries_relations", "countries_treaties", "country_governments",
            "research_tracks", "strategic_weapons", "campaign_scenarios", "campaigns",
            "objectives", "sphere_delegations",
        }),
        handles=frozenset({ActionStartCampaign, ActionSetSphereDelegation}),
        phase=SystemPhase.BOOTSTRAP,
    )

    def __init__(self) -> None:
        self._processor = CampaignSystem()

    @property
    def id(self) -> str:
        return "base.campaign_setup"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.bootstrap"]

    def update(self, state: GameState, delta_time: float) -> None:
        self._processor._ensure_sandbox_scenario(state)
        for action in state.current_actions:
            if isinstance(action, ActionStartCampaign):
                self._processor._start_campaign(state, action)
            elif isinstance(action, ActionSetSphereDelegation):
                self._processor._set_delegation(state, action)


class CampaignSystem(ISystem):
    """Runs after domain systems so campaign measurements use authoritative outputs."""

    access = SystemAccess(
        reads=frozenset({
            "countries", "regions", "countries_treaties", "domestic_production",
            "regional_production", "research_tracks", "strategic_weapons",
            "strategic_launch_orders", "political_crises", "news_items",
            "campaign_scenarios", "campaigns", "objectives", "sphere_delegations", "political_parties",
            "messages", "debt_distress_cases", "migration_signals", "infrastructure_damage_records",
            "regions",
            "advisor_recommendations",
        }),
        writes=frozenset({
            "campaigns", "objectives", "sphere_delegations", "advisor_recommendations",
        }),
        phase=SystemPhase.POST_PROCESS,
    )

    @property
    def id(self) -> str:
        return "base.campaign"

    @property
    def dependencies(self) -> list[str]:
        return ["base.campaign_setup"]

    def update(self, state: GameState, delta_time: float) -> None:
        self._evaluate_objectives(state)
        self._evaluate_campaign_outcomes(state)
        self._refresh_recommendations(state)
        self._publish_active_rules(state)

    def _ensure_sandbox_scenario(self, state: GameState) -> None:
        table = state.tables.get("campaign_scenarios")
        if table is None or not table.is_empty():
            return
        defaults = self._defaults_for("campaign_scenarios")
        defaults.update({
            "id": "open_sandbox",
            "title": "Open Sandbox",
            "description": "Play without a forced victory condition or deadline.",
            "selectable_country_ids_json": "[]",
            "political_scope": "country",
            "sphere_scope": "",
            "starting_setup_json": "{}",
            "enabled_rules_json": "{}",
            "objectives_json": "[]",
            "win_conditions_json": "{}",
            "loss_conditions_json": "{}",
            "max_duration_minutes": 0,
            "sandbox_allowed": True,
            "enabled": True,
        })
        state.update_table("campaign_scenarios", self._frame(table, [defaults]))

    def _start_campaign(self, state: GameState, action: ActionStartCampaign) -> None:
        actor = self._tag(action.country_tag)
        player_tag = self._tag(state.globals.get("player_tag"))
        if player_tag and actor != player_tag:
            self._result(state, action, "rejected", "The selected country is not assigned to this player.")
            return

        scenarios = state.tables.get("campaign_scenarios")
        scenario = next(
            (row for row in self._rows(scenarios) if row.get("id") == action.scenario_id and bool(row.get("enabled", True))),
            None,
        )
        if scenario is None:
            self._result(state, action, "rejected", "The selected scenario is unavailable or disabled.")
            return
        if not self._country_exists(state, actor):
            self._result(state, action, "rejected", "The selected country has no current country record.")
            return
        try:
            selectable = self._json_list(scenario.get("selectable_country_ids_json") or "[]", "selectable countries")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self._result(state, action, "rejected", str(exc))
            return
        if selectable and actor not in {self._tag(value) for value in selectable}:
            self._result(state, action, "rejected", "The selected country is not available in this scenario.")
            return
        campaigns = self._rows(state.tables.get("campaigns"))
        if any(
            str(row.get("scenario_id")) == str(action.scenario_id)
            and self._tag(row.get("actor_country_id")) == actor
            for row in campaigns
        ):
            self._result(state, action, "rejected", "This country has already started this scenario in the current game.")
            return

        try:
            objective_definitions = self._objective_definitions(scenario)
            prepared_setup, provenance = self._prepare_setup(state, scenario.get("starting_setup_json") or "{}")
            actor_scope = self._validate_actor_scope(state, scenario, actor, prepared_setup)
            enabled_rules = self._json_object(scenario.get("enabled_rules_json") or "{}", "enabled rules")
            win_rules = self._json_object(scenario.get("win_conditions_json") or "{}", "win conditions")
            loss_rules = self._json_object(scenario.get("loss_conditions_json") or "{}", "loss conditions")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self._result(state, action, "rejected", str(exc))
            return

        has_required_objectives = any(bool(item.get("required", True)) for item in objective_definitions)
        is_open_sandbox = (
            not has_required_objectives
            and not win_rules
            and not loss_rules
            and int(scenario.get("max_duration_minutes") or 0) <= 0
            and bool(scenario.get("sandbox_allowed", True))
        )
        invalid_no_outcome = (
            not has_required_objectives
            and not win_rules
            and not loss_rules
            and int(scenario.get("max_duration_minutes") or 0) <= 0
            and not bool(scenario.get("sandbox_allowed", True))
        )
        if invalid_no_outcome:
            self._result(state, action, "rejected", "A scenario with no required objectives or outcome rules must allow sandbox continuation.")
            return

        now = int(state.time.total_minutes)
        campaign_id = f"campaign:{scenario['id']}:{actor}:{int(state.globals.get('tick', 0))}:{len(campaigns) + 1}"
        for table_name, frame in prepared_setup.items():
            state.update_table(table_name, frame)

        new_objectives = [
            self._build_objective(state, campaign_id, actor, definition, now, index)
            for index, definition in enumerate(objective_definitions, start=1)
        ]
        objective_table = state.tables["objectives"]
        old_objectives = objective_table.to_dicts()
        state.update_table("objectives", self._frame(objective_table, old_objectives + new_objectives))

        campaign = self._defaults_for("campaigns")
        campaign.update({
            "id": campaign_id,
            "scenario_id": str(scenario["id"]),
            "player_id": str(action.player_id),
            "actor_country_id": actor,
            "actor_scope": actor_scope,
            "started_at_minute": now,
            "setup_applied": True,
            "setup_provenance_json": json.dumps(provenance, sort_keys=True, separators=(",", ":")),
            "enabled_rules_json": json.dumps(enabled_rules, sort_keys=True, separators=(",", ":")),
            "outcome": "sandbox" if is_open_sandbox else "ongoing",
            "outcome_reason": "No forced victory, loss, or deadline is configured." if is_open_sandbox else "",
            "outcome_at_minute": now if is_open_sandbox else -1,
            "sandbox_continuation": bool(scenario.get("sandbox_allowed", True)),
        })
        state.update_table("campaigns", self._frame(state.tables["campaigns"], campaigns + [campaign]))
        self._result(state, action, "applied", "Scenario setup was applied once and campaign objectives were initialized.")

    def _objective_definitions(self, scenario: dict[str, Any]) -> list[dict[str, Any]]:
        definitions = self._json_list(scenario.get("objectives_json") or "[]", "scenario objectives")
        seen: set[str] = set()
        for definition in definitions:
            if not isinstance(definition, dict):
                raise ValueError("Each objective definition must be an object.")
            objective_type = str(definition.get("objective_type", "")).strip().lower()
            if objective_type not in _SUPPORTED_OBJECTIVES:
                raise ValueError(f"Unsupported objective type '{objective_type}'.")
            objective_id = str(definition.get("id") or definition.get("title") or "").strip()
            if objective_id and objective_id in seen:
                raise ValueError(f"Duplicate objective id '{objective_id}'.")
            if objective_id:
                seen.add(objective_id)
            target_value = float(definition.get("target_value", 1.0))
            if not math.isfinite(target_value):
                raise ValueError("Objective target_value must be finite.")
            hold = int(definition.get("hold_duration_minutes", 0))
            if hold < 0:
                raise ValueError("Objective hold_duration_minutes cannot be negative.")
            comparison = str(definition.get("comparison", "at_least")).lower()
            if comparison not in {"at_least", "at_most", "equals"}:
                raise ValueError(f"Unsupported objective comparison '{comparison}'.")
            if str(definition.get("progress_rule", "reset")).lower() not in {"reset", "decay"}:
                raise ValueError("Objective progress_rule must be 'reset' or 'decay'.")
            failure_conditions = definition.get("failure_conditions", [])
            if not isinstance(failure_conditions, list):
                raise ValueError("Objective failure_conditions must be a list.")
            for condition in failure_conditions:
                if not isinstance(condition, dict):
                    raise ValueError("Each objective failure condition must be an object.")
                condition_type = str(condition.get("objective_type") or "").strip().lower()
                if condition_type not in _SUPPORTED_OBJECTIVES:
                    raise ValueError(f"Unsupported objective failure condition '{condition_type}'.")
                condition_comparison = str(condition.get("comparison", "at_least")).lower()
                if condition_comparison not in {"at_least", "at_most", "equals"}:
                    raise ValueError(f"Unsupported failure condition comparison '{condition_comparison}'.")
                try:
                    condition_target = float(condition.get("target_value", 1.0))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("Objective failure condition target_value must be finite.") from exc
                if not math.isfinite(condition_target):
                    raise ValueError("Objective failure condition target_value must be finite.")
        return definitions

    def _build_objective(
        self,
        state: GameState,
        campaign_id: str,
        actor: str,
        definition: dict[str, Any],
        now: int,
        index: int,
    ) -> dict[str, Any]:
        target = float(definition.get("target_value", 1.0))
        relative_deadline = definition.get("deadline_minutes")
        deadline = int(definition.get("deadline_at_minute", -1))
        if relative_deadline is not None:
            deadline = now + max(0, int(relative_deadline))
        row = self._defaults_for("objectives")
        objective_id = str(definition.get("id") or f"objective-{index}")
        row.update({
            "id": f"{campaign_id}:{objective_id}",
            "country_id": actor,
            "title": str(definition.get("title") or objective_id),
            "description": str(definition.get("description") or ""),
            "status": "pending",
            "progress": 0.0,
            "campaign_id": campaign_id,
            "objective_type": str(definition["objective_type"]).strip().lower(),
            "actor_id": self._tag(definition.get("actor_id") or actor),
            "target_id": str(definition.get("target_id") or ""),
            "target_ids_json": json.dumps(definition.get("target_ids", []), separators=(",", ":")),
            "target_resource_id": str(definition.get("target_resource_id") or ""),
            "target_branch": str(definition.get("target_branch") or ""),
            "control_field": str(definition.get("control_field") or ""),
            "failure_conditions_json": json.dumps(
                definition.get("failure_conditions", []), sort_keys=True, separators=(",", ":")
            ),
            "target_value": target,
            "current_value": 0.0,
            "remaining": max(0.0, target),
            "comparison": str(definition.get("comparison", "at_least")).lower(),
            "required": bool(definition.get("required", True)),
            "deadline_at_minute": deadline,
            "hold_duration_minutes": int(definition.get("hold_duration_minutes", 0)),
            "hold_started_at_minute": -1,
            "held_minutes": 0,
            "progress_rule": str(definition.get("progress_rule", "reset")).lower(),
            "last_evaluated_at_minute": now,
            "last_changed_at_minute": now,
            "evidence_json": "[]",
            "reason": "Objective initialized from the selected campaign scenario.",
            "missing_data_reason": "",
        })
        return row

    def _prepare_setup(self, state: GameState, raw_setup: Any) -> tuple[dict[str, pl.DataFrame], list[dict[str, Any]]]:
        setup = self._json_object(raw_setup, "starting setup")
        unexpected_setup_keys = set(setup) - {"updates"}
        if unexpected_setup_keys:
            raise ValueError(f"Starting setup contains unsupported keys {sorted(unexpected_setup_keys)}.")
        updates = setup.get("updates", [])
        if not isinstance(updates, list):
            raise ValueError("starting_setup_json.updates must be a list.")
        prepared: dict[str, list[dict[str, Any]]] = {}
        provenance: list[dict[str, Any]] = []
        for update in updates:
            if not isinstance(update, dict):
                raise ValueError("Each starting setup update must be an object.")
            unexpected_update_keys = set(update) - {"table", "key", "values"}
            if unexpected_update_keys:
                raise ValueError(f"Starting setup update contains unsupported keys {sorted(unexpected_update_keys)}.")
            table_name = str(update.get("table") or "")
            if table_name not in _SETUP_FIELDS:
                raise ValueError(f"Table '{table_name}' is not permitted for scenario setup.")
            frame = state.tables.get(table_name)
            if frame is None:
                raise ValueError(f"Scenario setup source table '{table_name}' is unavailable.")
            keys = _SETUP_KEYS[table_name]
            raw_key = update.get("key")
            key_values = raw_key if isinstance(raw_key, dict) else ({keys[0]: raw_key} if len(keys) == 1 else {})
            if set(key_values) != set(keys):
                raise ValueError(f"Scenario setup for '{table_name}' requires key fields {keys}.")
            values = update.get("values")
            if not isinstance(values, dict) or not values:
                raise ValueError("Each starting setup update requires a non-empty values object.")
            invalid_fields = set(values) - _SETUP_FIELDS[table_name]
            if invalid_fields:
                raise ValueError(f"Scenario setup cannot change {table_name} fields {sorted(invalid_fields)}.")
            if any(key not in frame.columns for key in keys) or any(field not in frame.columns for field in values):
                raise ValueError(f"Scenario setup references unavailable columns in '{table_name}'.")
            rows = prepared.setdefault(table_name, frame.to_dicts())
            matching = [
                row for row in rows
                if all(str(row.get(key)) == str(key_values[key]) for key in keys)
            ]
            if len(matching) != 1:
                raise ValueError(f"Scenario setup expected exactly one '{table_name}' row for key {key_values}.")
            target_row = matching[0]
            for field, value in values.items():
                if value is None:
                    raise ValueError(f"Scenario setup value for {table_name}.{field} cannot be null.")
                if isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(value):
                    raise ValueError(f"Scenario setup value for {table_name}.{field} must be finite.")
                target_row[field] = value
            provenance.append({"table": table_name, "key": key_values, "values": values})
        validated_frames: dict[str, pl.DataFrame] = {}
        for table_name, rows in prepared.items():
            try:
                frame = pl.DataFrame(
                    rows,
                    schema=state.tables[table_name].schema,
                    strict=True,
                )
                if state.schema_registry is not None:
                    frame = state.schema_registry.normalize(table_name, frame)
                validated_frames[table_name] = frame
            except (TypeError, ValueError, pl.exceptions.PolarsError) as exc:
                # Validate all casts before committing any table to prevent partial scenario setup.
                raise ValueError(f"Scenario setup values do not match the '{table_name}' schema: {exc}") from exc
        return validated_frames, provenance

    def _validate_actor_scope(
        self,
        state: GameState,
        scenario: dict[str, Any],
        actor: str,
        staged_setup: dict[str, pl.DataFrame],
    ) -> str:
        scope = str(scenario.get("political_scope") or "country").strip().lower()
        if scope not in {"country", "party", "sphere"}:
            raise ValueError(f"Unsupported campaign actor scope '{scope}'.")
        if scope == "party":
            governments = staged_setup.get("country_governments", state.tables.get("country_governments"))
            government = next(
                (row for row in self._rows(governments) if self._tag(row.get("country_id")) == actor),
                None,
            )
            party_id = str(government.get("ruling_party_id") or "").strip() if government else ""
            parties = self._rows(state.tables.get("political_parties"))
            if not party_id or not any(
                self._tag(row.get("country_id")) == actor
                and str(row.get("party_id") or "").strip().casefold() == party_id.casefold()
                for row in parties
            ):
                raise ValueError("Party-scoped campaigns require an existing ruling party for the selected country.")
        elif scope == "sphere":
            sphere_id = str(scenario.get("sphere_scope") or "").strip()
            treaties = staged_setup.get("countries_treaties", state.tables.get("countries_treaties"))
            treaty = next(
                (row for row in self._rows(treaties) if str(row.get("id") or "") == sphere_id),
                None,
            )
            members = self._tag_list(treaty.get("members")) if treaty else set()
            if (
                not sphere_id
                or treaty is None
                or str(treaty.get("status") or "active").strip().lower() != "active"
                or actor not in members
                or len(members) < 2
            ):
                raise ValueError("Sphere-scoped campaigns require an active selected treaty containing the selected country.")
        return scope

    def _set_delegation(self, state: GameState, action: ActionSetSphereDelegation) -> None:
        actor = self._tag(action.country_tag)
        player_tag = self._tag(state.globals.get("player_tag"))
        scope_type = str(action.scope_type or "").strip().lower()
        scope_id = str(action.scope_id or "").strip()
        authority = sorted({str(item).strip().lower() for item in action.authority if str(item).strip()})
        if player_tag and actor != player_tag:
            self._result(state, action, "rejected", "Only the campaign owner may change delegation.")
            return
        if scope_type not in {"country", "party", "sphere"} or not scope_id:
            self._result(state, action, "rejected", "Delegation requires a valid scope type and scope id.")
            return
        if not set(authority).issubset(_DELEGATION_AUTHORITY):
            self._result(state, action, "rejected", "Delegation authority contains an unsupported domain.")
            return
        return_condition = str(action.return_condition or "manual").strip().lower()
        if return_condition not in {"manual", "campaign_end"}:
            self._result(state, action, "rejected", "Delegation return condition must be 'manual' or 'campaign_end'.")
            return
        if action.active and str(action.delegate_id or "ai").strip().lower() != "ai":
            self._result(state, action, "rejected", "Only the existing AI controller can be delegated in this single-player build.")
            return
        if scope_type == "country" and scope_id.upper() != actor:
            self._result(state, action, "rejected", "Country delegation scope must be the campaign actor country.")
            return
        if scope_type == "party" and action.active:
            parties = self._rows(state.tables.get("political_parties"))
            party_exists = any(
                self._tag(row.get("country_id")) == actor
                and str(row.get("party_id") or "").strip().casefold() == scope_id.casefold()
                for row in parties
            )
            governments = self._rows(state.tables.get("country_governments"))
            government = next((row for row in governments if self._tag(row.get("country_id")) == actor), {})
            ruling_party = str(government.get("ruling_party_id") or "").strip()
            if not ruling_party:
                ruling_party = next((
                    str(row.get("party_id") or "").strip() for row in parties
                    if self._tag(row.get("country_id")) == actor and bool(row.get("is_ruling"))
                ), "")
            if not authority or not set(authority).issubset({"politics"}):
                self._result(state, action, "rejected", "Party delegation can grant political authority only.")
                return
            if not party_exists or ruling_party.casefold() != scope_id.casefold():
                self._result(state, action, "rejected", "Party delegation requires the campaign actor's current ruling party.")
                return
        if scope_type == "sphere" and action.active:
            treaties = self._rows(state.tables.get("countries_treaties"))
            treaty = next((row for row in treaties if str(row.get("id") or "") == scope_id), None)
            members = self._tag_list(treaty.get("members")) if treaty else set()
            if not authority or not set(authority).issubset({"diplomacy"}):
                self._result(state, action, "rejected", "Sphere delegation is limited to diplomacy within its treaty membership.")
                return
            if treaty is None or str(treaty.get("status") or "active").lower() != "active" or actor not in members or len(members) < 2:
                self._result(state, action, "rejected", "Sphere scope must be an active treaty that includes the campaign actor.")
                return
        if action.active and not authority:
            self._result(state, action, "rejected", "Active delegation requires at least one authority domain.")
            return
        campaign = next(
            (row for row in self._rows(state.tables.get("campaigns"))
             if self._tag(row.get("actor_country_id")) == actor and row.get("outcome") in {"ongoing", "sandbox"}),
            None,
        )
        if campaign is None:
            self._result(state, action, "rejected", "An active campaign is required before delegating control.")
            return
        delegations_table = state.tables["sphere_delegations"]
        rows = self._rows(delegations_table)
        delegation_id = f"delegation:{campaign['id']}:{scope_type}:{scope_id}"
        updated = self._defaults_for("sphere_delegations")
        updated.update({
            "id": delegation_id,
            "campaign_id": str(campaign["id"]),
            "owner_country_id": actor,
            "delegate_id": str(action.delegate_id or "ai"),
            "scope_type": scope_type,
            "scope_id": scope_id,
            "authority_json": json.dumps(authority, separators=(",", ":")),
            "priorities_json": json.dumps(list(action.priorities), separators=(",", ":")),
            "started_at_minute": int(state.time.total_minutes),
            "return_condition": return_condition,
            "current_controller": str(action.delegate_id or "ai") if action.active else "human",
            "active": bool(action.active),
            "reason": "Delegation is explicitly bounded by the recorded scope and authority list.",
        })
        rows = [row for row in rows if row.get("id") != delegation_id] + [updated]
        state.update_table("sphere_delegations", self._frame(delegations_table, rows))
        self._result(state, action, "applied", "Delegation state was updated without changing country ownership.")

    def _evaluate_objectives(self, state: GameState) -> None:
        table = state.tables.get("objectives")
        if table is None or table.is_empty():
            return
        now = int(state.time.total_minutes)
        rows = table.to_dicts()
        measurement_context = ObjectiveMeasurementContext(state)
        evidence_json_cache: dict[tuple[Any, ...], str] = {}
        changed = False
        for row in rows:
            if not row.get("objective_type"):
                continue
            if row.get("status") in {"completed", "failed", "expired", "cancelled"}:
                continue
            measurement = measure_objective(state, row, measurement_context)
            current = float(measurement.value)
            previous_current = float(row.get("current_value") or 0.0)
            status_before = str(row.get("status") or "pending")
            reason_before = str(row.get("reason") or "")
            missing_before = str(row.get("missing_data_reason") or "")
            target = float(row.get("target_value") or 0.0)
            satisfied = self._meets_target(current, target, str(row.get("comparison") or "at_least"))
            hold_start = self._as_int(row.get("hold_started_at_minute"), -1)
            held = max(0, int(row.get("held_minutes") or 0))
            previous_eval = int(row.get("last_evaluated_at_minute") or now)
            delta_minutes = max(0, now - previous_eval)
            hold_duration = max(0, int(row.get("hold_duration_minutes") or 0))
            status = "active"
            reason = "Condition is not yet satisfied."
            missing_reason = ""
            progress = self._progress(current, target, satisfied, str(row.get("comparison") or "at_least"))
            failure_configuration_error = False
            try:
                failure_conditions = self._json_list(row.get("failure_conditions_json") or "[]", "objective failure conditions")
            except (TypeError, ValueError, json.JSONDecodeError):
                failure_conditions = []
                failure_configuration_error = True
            failed = any(
                self._condition_matches(state, condition, self._tag(row.get("actor_id")), measurement_context)
                for condition in failure_conditions
            )

            if failure_configuration_error:
                status = "blocked"
                reason = "Objective failure-condition data is invalid and requires correction."
                missing_reason = reason
            elif failed:
                status = "failed"
                reason = "An authoritative objective failure condition was met."
            elif not measurement.available:
                status = "blocked"
                missing_reason = measurement.reason
                reason = measurement.reason
            elif satisfied:
                if hold_start < 0:
                    # A decay hold preserves prior progress but never counts the time spent without control.
                    hold_start = now - held
                held = max(0, now - hold_start)
                if held >= hold_duration:
                    status = "completed"
                    reason = "The authoritative condition was met for the required duration."
                elif hold_duration > 0:
                    reason = "Condition is met; the configured hold duration is still running."
                    progress = min(1.0, held / hold_duration)
            else:
                if hold_duration > 0:
                    if str(row.get("progress_rule") or "reset") == "reset":
                        held = 0
                    else:
                        held = max(0, held - delta_minutes)
                    hold_start = -1
                    progress = min(1.0, held / hold_duration)
                if measurement.available:
                    status = "active"

            deadline = self._as_int(row.get("deadline_at_minute"), -1)
            if status not in {"completed", "failed"} and deadline >= 0 and now > deadline:
                status = "expired"
                reason = "The objective deadline elapsed before completion."
            comparison = str(row.get("comparison") or "at_least")
            if comparison == "at_least":
                remaining = max(0.0, target - current)
            elif comparison == "at_most":
                remaining = max(0.0, current - target)
            else:
                remaining = abs(target - current)

            meaningful_change = (
                not math.isclose(current, previous_current, rel_tol=1e-9, abs_tol=1e-9)
                or status != status_before
                or reason != reason_before
                or missing_reason != missing_before
                or hold_start != self._as_int(row.get("hold_started_at_minute"), -1)
                or held != int(row.get("held_minutes") or 0)
                or not math.isclose(progress, float(row.get("progress") or 0.0), rel_tol=1e-9, abs_tol=1e-9)
            )
            row["current_value"] = current
            row["remaining"] = remaining
            row["progress"] = progress
            row["status"] = status
            row["reason"] = reason
            row["missing_data_reason"] = missing_reason
            row["hold_started_at_minute"] = hold_start
            row["held_minutes"] = held
            row["last_evaluated_at_minute"] = now
            if meaningful_change:
                evidence_entry = {
                    "tick": int(state.globals.get("tick", 0)),
                    "game_minute": now,
                    "source_table": measurement.source_table,
                    "current_value": current,
                    "target_value": target,
                    "status": status,
                    "reason": reason,
                    "completeness": "complete" if measurement.available else "missing",
                }
                cache_key = (
                    evidence_entry["tick"], evidence_entry["game_minute"], evidence_entry["source_table"],
                    evidence_entry["current_value"], evidence_entry["target_value"], evidence_entry["status"],
                    evidence_entry["reason"], evidence_entry["completeness"],
                )
                serialized_single_entry = evidence_json_cache.get(cache_key)
                if serialized_single_entry is None:
                    serialized_single_entry = json.dumps([evidence_entry], sort_keys=True, separators=(",", ":"))
                    evidence_json_cache[cache_key] = serialized_single_entry
                prior_evidence = row.get("evidence_json")
                if prior_evidence in (None, "", "[]"):
                    row["evidence_json"] = serialized_single_entry
                else:
                    evidence = self._json_list(prior_evidence, "objective evidence")
                    evidence.append(evidence_entry)
                    row["evidence_json"] = json.dumps(evidence[-64:], sort_keys=True, separators=(",", ":"))
                row["last_changed_at_minute"] = now
                changed = True
        if changed:
            state.update_table("objectives", self._frame(table, rows))

    def _evaluate_campaign_outcomes(self, state: GameState) -> None:
        campaign_table = state.tables.get("campaigns")
        if campaign_table is None or campaign_table.is_empty():
            return
        now = int(state.time.total_minutes)
        campaigns = campaign_table.to_dicts()
        scenario_by_id = {str(row.get("id")): row for row in self._rows(state.tables.get("campaign_scenarios"))}
        objectives = self._rows(state.tables.get("objectives"))
        measurement_context = ObjectiveMeasurementContext(state)
        changed = False
        for campaign in campaigns:
            if campaign.get("outcome") not in {"ongoing", "sandbox"}:
                continue
            scenario = scenario_by_id.get(str(campaign.get("scenario_id")), {})
            actor = self._tag(campaign.get("actor_country_id"))
            campaign_objectives = [row for row in objectives if row.get("campaign_id") == campaign.get("id")]
            required = [row for row in campaign_objectives if bool(row.get("required", True))]
            try:
                win_rules = self._json_object(scenario.get("win_conditions_json", "{}"), "win conditions")
                loss_rules = self._json_object(scenario.get("loss_conditions_json", "{}"), "loss conditions")
            except (TypeError, ValueError, json.JSONDecodeError):
                win_rules, loss_rules = {}, {}
            selected_objectives = [
                row for row in required
                if not win_rules.get("objective_ids")
                or str(row.get("id")) in {str(value) for value in win_rules.get("objective_ids", [])}
            ]
            win_mode = str(win_rules.get("objective_mode", "all")).strip().lower()
            objective_win = False
            if selected_objectives:
                completions = [row.get("status") == "completed" for row in selected_objectives]
                objective_win = any(completions) if win_mode == "any" else all(completions)
            win_conditions = win_rules.get("conditions", [])
            if isinstance(win_conditions, list) and win_conditions:
                condition_results = [
                    self._condition_matches(state, condition, actor, measurement_context)
                    for condition in win_conditions
                ]
                condition_mode = str(win_rules.get("condition_mode", "all")).strip().lower()
                conditions_met = any(condition_results) if condition_mode == "any" else all(condition_results)
                objective_win = (
                    objective_win and conditions_met
                    if selected_objectives
                    else conditions_met
                )

            loss_objectives = [
                row for row in required
                if not loss_rules.get("objective_ids")
                or str(row.get("id")) in {str(value) for value in loss_rules.get("objective_ids", [])}
            ]
            any_failed = bool(loss_rules.get("required_objective_failure", True)) and any(
                row.get("status") in {"failed", "expired"} for row in loss_objectives
            )
            max_duration = max(0, int(scenario.get("max_duration_minutes") or 0))
            deadline_elapsed = max_duration > 0 and now > int(campaign.get("started_at_minute") or 0) + max_duration
            absolute_deadline = self._as_int(loss_rules.get("deadline_at_minute"), -1)
            if absolute_deadline >= 0 and now > absolute_deadline:
                deadline_elapsed = True
            duration_deadline = self._as_int(loss_rules.get("deadline_minutes"), 0)
            if duration_deadline > 0 and now > int(campaign.get("started_at_minute") or 0) + duration_deadline:
                deadline_elapsed = True
            loss_conditions = loss_rules.get("conditions", [])
            if isinstance(loss_conditions, list) and loss_conditions:
                condition_results = [
                    self._condition_matches(state, condition, actor, measurement_context)
                    for condition in loss_conditions
                ]
                condition_mode = str(loss_rules.get("condition_mode", "any")).strip().lower()
                any_failed = any_failed or (all(condition_results) if condition_mode == "all" else any(condition_results))
            loss_met = any_failed or deadline_elapsed
            if loss_rules.get("lose_if_no_territory"):
                regions = self._rows(state.tables.get("regions"))
                if regions:
                    owned = any(
                        self._tag(row.get("controller") or row.get("owner")) == actor
                        for row in regions
                    )
                    loss_met = loss_met or not owned

            if objective_win and loss_met and bool(loss_rules.get("draw_on_simultaneous", False)):
                outcome, reason = "draw", "Win and loss conditions were met at the same evaluation boundary."
            elif objective_win:
                outcome = "victory"
                reason = "The configured campaign win conditions are satisfied."
            elif loss_met:
                outcome = "defeat"
                reason = "A configured loss condition or campaign deadline was reached."
            else:
                continue
            campaign.update({
                "outcome": outcome,
                "outcome_reason": reason,
                "outcome_at_minute": now,
                "sandbox_continuation": bool(scenario.get("sandbox_allowed", True)),
            })
            changed = True
        if changed:
            state.update_table("campaigns", self._frame(campaign_table, campaigns))
        closed_objectives = False
        for campaign in campaigns:
            if campaign.get("outcome") not in {"victory", "defeat", "draw"} or campaign.get("sandbox_continuation"):
                continue
            close_status = "failed" if campaign.get("outcome") == "defeat" else "cancelled"
            for objective in objectives:
                if objective.get("campaign_id") != campaign.get("id") or objective.get("status") in {
                    "completed", "failed", "expired", "cancelled",
                }:
                    continue
                reason = (
                    "The campaign ended in defeat before this objective was resolved."
                    if close_status == "failed"
                    else "The campaign ended before this objective was resolved."
                )
                objective["status"] = close_status
                objective["reason"] = reason
                objective["last_evaluated_at_minute"] = now
                objective["last_changed_at_minute"] = now
                evidence = self._json_list(objective.get("evidence_json") or "[]", "objective evidence")
                evidence.append({
                    "tick": int(state.globals.get("tick", 0)),
                    "game_minute": now,
                    "source_table": "campaigns",
                    "current_value": float(objective.get("current_value") or 0.0),
                    "target_value": float(objective.get("target_value") or 0.0),
                    "status": close_status,
                    "reason": reason,
                    "completeness": "complete",
                })
                objective["evidence_json"] = json.dumps(evidence[-64:], sort_keys=True, separators=(",", ":"))
                closed_objectives = True
        if closed_objectives:
            objective_table = state.tables.get("objectives")
            if objective_table is not None:
                state.update_table("objectives", self._frame(objective_table, objectives))
        delegations_table = state.tables.get("sphere_delegations")
        if delegations_table is not None and not delegations_table.is_empty():
            delegations = delegations_table.to_dicts()
            closed_campaign_ids = {
                str(row.get("id") or "")
                for row in campaigns
                if row.get("outcome") in {"victory", "defeat", "draw"}
                and not row.get("sandbox_continuation")
            }
            delegation_changed = False
            for delegation in delegations:
                if (
                    delegation.get("active")
                    and delegation.get("return_condition") == "campaign_end"
                    and str(delegation.get("campaign_id") or "") in closed_campaign_ids
                ):
                    delegation.update(
                        active=False,
                        current_controller="human",
                        reason="The campaign ended and the configured return condition restored human control.",
                    )
                    delegation_changed = True
            if delegation_changed:
                state.update_table("sphere_delegations", self._frame(delegations_table, delegations))

    def _condition_matches(
        self,
        state: GameState,
        condition: Any,
        actor: str,
        measurement_context: ObjectiveMeasurementContext | None = None,
    ) -> bool:
        if not isinstance(condition, dict):
            return False
        objective = {**condition, "actor_id": condition.get("actor_id") or actor}
        measurement = measure_objective(state, objective, measurement_context)
        if not measurement.available:
            return False
        try:
            target = float(condition.get("target_value", 1.0))
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(target):
            return False
        return self._meets_target(
            float(measurement.value),
            target,
            str(condition.get("comparison", "at_least")).strip().lower(),
        )

    def _publish_active_rules(self, state: GameState) -> None:
        player_tag = self._tag(state.globals.get("player_tag"))
        active = [
            row for row in self._rows(state.tables.get("campaigns"))
            if self._tag(row.get("actor_country_id")) == player_tag
            and (
                row.get("outcome") in {"ongoing", "sandbox"}
                or bool(row.get("sandbox_continuation"))
            )
        ]
        active.sort(key=lambda row: (self._as_int(row.get("started_at_minute")), str(row.get("id") or "")), reverse=True)
        campaign = active[0] if active else None
        try:
            rules = self._json_object(campaign.get("enabled_rules_json", "{}"), "enabled rules") if campaign else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            rules = {}
        campaign_id = str(campaign.get("id") or "") if campaign else ""
        if state.globals.get("active_campaign_id") != campaign_id:
            state.globals["active_campaign_id"] = campaign_id
        if state.globals.get("active_scenario_rules") != rules:
            state.globals["active_scenario_rules"] = rules

    def _refresh_recommendations(self, state: GameState) -> None:
        campaigns_table = state.tables.get("campaigns")
        recommendations_table = state.tables.get("advisor_recommendations")
        if campaigns_table is None or recommendations_table is None:
            return
        campaigns = [
            row for row in self._rows(campaigns_table)
            if row.get("outcome") in {"ongoing", "sandbox"} or bool(row.get("sandbox_continuation"))
        ]
        all_objectives = self._rows(state.tables.get("objectives"))
        crises = self._rows(state.tables.get("political_crises"))
        news_items = self._rows(state.tables.get("news_items"))
        messages = self._rows(state.tables.get("messages"))
        debt_cases = self._rows(state.tables.get("debt_distress_cases"))
        migration_signals = self._rows(state.tables.get("migration_signals"))
        damage_records = self._rows(state.tables.get("infrastructure_damage_records"))
        regions = self._rows(state.tables.get("regions"))
        existing = self._rows(recommendations_table)
        by_id = {str(row.get("id")): row for row in existing}
        now = int(state.time.total_minutes)
        changed = False
        current_signals: set[tuple[str, str]] = set()
        for item in existing:
            if item.get("status") == "active" and self._as_int(item.get("expires_at_minute")) <= now:
                item["status"] = "expired"
                item["stale_reason"] = "Recommendation expired before it was acted on."
                changed = True

        for campaign in campaigns:
            campaign_id = str(campaign.get("id"))
            actor = self._tag(campaign.get("actor_country_id"))
            objectives = [
                row for row in all_objectives
                if row.get("campaign_id") == campaign_id and row.get("required", True)
                and row.get("status") not in {"completed", "failed", "expired", "cancelled"}
            ]
            for objective in objectives:
                status = str(objective.get("status") or "active")
                deadline = self._as_int(objective.get("deadline_at_minute"), -1)
                is_due = deadline >= 0 and 0 <= deadline - now <= _RECOMMENDATION_WINDOW_MINUTES
                if status != "blocked" and not is_due:
                    continue
                signal = f"objective:{objective.get('id')}:{'blocked' if status == 'blocked' else 'deadline'}"
                current_signals.add((campaign_id, signal))
                recommendation_id = f"advisor:{campaign_id}:{signal}"
                if recommendation_id in by_id:
                    continue
                urgent = 0.95 if status == "blocked" else max(0.55, 1.0 - (deadline - now) / _RECOMMENDATION_WINDOW_MINUTES)
                row = self._defaults_for("advisor_recommendations")
                row.update({
                    "id": recommendation_id,
                    "campaign_id": campaign_id,
                    "actor_country_id": actor,
                    "title": "Resolve a blocked objective" if status == "blocked" else "Campaign deadline approaching",
                    "reason": str(objective.get("missing_data_reason") or objective.get("reason") or "Review the objective status and required next action."),
                    "source_signal": signal,
                    "affected_country_id": self._tag(objective.get("actor_id")),
                    "affected_region_id": self._safe_int(objective.get("target_id")),
                    "confidence": 0.8,
                    "urgency": min(1.0, max(0.0, urgent)),
                    "expires_at_minute": now + 7 * 24 * 60,
                    "optional_action_json": "",
                    "status": "active",
                    "created_at_minute": now,
                    "stale_reason": "",
                })
                existing.append(row)
                by_id[recommendation_id] = row
                changed = True

            for crisis in crises:
                if self._tag(crisis.get("country_id")) != actor or str(crisis.get("status", "")).lower() not in {"pending", "active", "resolving"}:
                    continue
                signal = f"political_crisis:{crisis.get('id')}"
                current_signals.add((campaign_id, signal))
                recommendation_id = f"advisor:{campaign_id}:{signal}"
                if recommendation_id in by_id:
                    continue
                row = self._defaults_for("advisor_recommendations")
                row.update({
                    "id": recommendation_id,
                    "campaign_id": campaign_id,
                    "actor_country_id": actor,
                    "title": "Political crisis requires review",
                    "reason": str(crisis.get("reason") or crisis.get("trigger") or "An unresolved political crisis is active."),
                    "source_signal": signal,
                    "affected_country_id": actor,
                    "confidence": 0.85,
                    "urgency": 0.95,
                    "expires_at_minute": max(now + 1, int(crisis.get("deadline_at_minute") or now + 7 * 24 * 60)),
                    "optional_action_json": "",
                    "status": "active",
                    "created_at_minute": now,
                    "stale_reason": "",
                })
                existing.append(row)
                by_id[recommendation_id] = row
                changed = True

            for news in news_items:
                category = str(news.get("category") or "").strip().lower()
                severity = str(news.get("severity") or "").strip().lower()
                related = self._tag(news.get("related_country_id"))
                if related and related != actor:
                    continue
                if severity not in {"critical", "urgent", "warning"} and category != "opportunity":
                    continue
                news_id = str(news.get("id") or "").strip()
                if not news_id:
                    continue
                signal = f"news:{news_id}"
                current_signals.add((campaign_id, signal))
                recommendation_id = f"advisor:{campaign_id}:{signal}"
                if recommendation_id in by_id:
                    continue
                urgency = 0.95 if severity in {"critical", "urgent"} else 0.7 if severity == "warning" else 0.6
                row = self._defaults_for("advisor_recommendations")
                row.update({
                    "id": recommendation_id,
                    "campaign_id": campaign_id,
                    "actor_country_id": actor,
                    "title": str(news.get("headline") or "Review a new opportunity"),
                    "reason": str(news.get("body") or "Review the latest campaign signal."),
                    "source_signal": signal,
                    "affected_country_id": related or actor,
                    "confidence": 0.75,
                    "urgency": urgency,
                    "expires_at_minute": now + 7 * 24 * 60,
                    "optional_action_json": "",
                    "status": "active",
                    "created_at_minute": now,
                    "stale_reason": "",
                })
                existing.append(row)
                by_id[recommendation_id] = row
                changed = True

            for message in messages:
                if self._tag(message.get("country_id")) != actor or bool(message.get("is_read")):
                    continue
                message_id = str(message.get("id") or "").strip()
                if not message_id:
                    continue
                signal = f"message:{message_id}"
                current_signals.add((campaign_id, signal))
                recommendation_id = f"advisor:{campaign_id}:{signal}"
                if recommendation_id in by_id:
                    continue
                category = str(message.get("category") or "").strip().lower()
                row = self._defaults_for("advisor_recommendations")
                row.update({
                    "id": recommendation_id, "campaign_id": campaign_id, "actor_country_id": actor,
                    "title": str(message.get("subject") or "Unread campaign message"),
                    "reason": str(message.get("body") or "Review the unread message for its required response."),
                    "source_signal": signal, "affected_country_id": actor,
                    "confidence": 0.9,
                    "urgency": 0.9 if category in {"war", "politics", "strategic", "covert"} else 0.7,
                    "expires_at_minute": now + 7 * 24 * 60, "optional_action_json": "",
                    "status": "active", "created_at_minute": now, "stale_reason": "",
                })
                existing.append(row)
                by_id[recommendation_id] = row
                changed = True

            for case in debt_cases:
                if self._tag(case.get("country_id")) != actor:
                    continue
                status = str(case.get("status") or "").strip().lower()
                if status in {"", "resolved", "recovered", "closed"}:
                    continue
                signal = f"debt_distress:{case.get('id')}:{status}"
                current_signals.add((campaign_id, signal))
                recommendation_id = f"advisor:{campaign_id}:{signal}"
                if recommendation_id in by_id:
                    continue
                row = self._defaults_for("advisor_recommendations")
                row.update({
                    "id": recommendation_id, "campaign_id": campaign_id, "actor_country_id": actor,
                    "title": "Debt distress requires a recovery plan",
                    "reason": str(case.get("reason") or case.get("recovery_condition") or case.get("trigger") or status),
                    "source_signal": signal, "affected_country_id": actor,
                    "confidence": 0.95, "urgency": 0.95,
                    "expires_at_minute": now + 7 * 24 * 60, "optional_action_json": "",
                    "status": "active", "created_at_minute": now, "stale_reason": "",
                })
                existing.append(row)
                by_id[recommendation_id] = row
                changed = True

            for migration in migration_signals:
                if self._tag(migration.get("country_id")) != actor:
                    continue
                political = abs(float(migration.get("political_pressure") or 0.0))
                service = abs(float(migration.get("service_pressure") or 0.0))
                law = abs(float(migration.get("law_pressure") or 0.0))
                if max(political, service, law) < 0.65:
                    continue
                signal = f"migration_pressure:{actor}:{self._as_int(migration.get('window_start_minute'))}"
                current_signals.add((campaign_id, signal))
                recommendation_id = f"advisor:{campaign_id}:{signal}"
                if recommendation_id in by_id:
                    continue
                reasons = [
                    name for name, value in (("political", political), ("service", service), ("law", law))
                    if value >= 0.65
                ]
                row = self._defaults_for("advisor_recommendations")
                row.update({
                    "id": recommendation_id, "campaign_id": campaign_id, "actor_country_id": actor,
                    "title": "Migration pressure is elevated",
                    "reason": "Recorded migration signals exceed the advisory pressure threshold in: " + ", ".join(reasons),
                    "source_signal": signal, "affected_country_id": actor,
                    "confidence": 0.8, "urgency": min(0.95, 0.6 + max(political, service, law) * 0.3),
                    "expires_at_minute": now + 7 * 24 * 60, "optional_action_json": "",
                    "status": "active", "created_at_minute": now, "stale_reason": "",
                })
                existing.append(row)
                by_id[recommendation_id] = row
                changed = True

            owner_by_region = {
                self._safe_int(region.get("id")): self._tag(region.get("owner") or region.get("controller"))
                for region in regions
            }
            for damage in damage_records:
                region_id = self._safe_int(damage.get("region_id"))
                if bool(damage.get("recovered")) or owner_by_region.get(region_id) != actor:
                    continue
                severity = float(damage.get("severity") or 0.0)
                if severity < 0.5:
                    continue
                signal = f"infrastructure_damage:{damage.get('id')}"
                current_signals.add((campaign_id, signal))
                recommendation_id = f"advisor:{campaign_id}:{signal}"
                if recommendation_id in by_id:
                    continue
                row = self._defaults_for("advisor_recommendations")
                row.update({
                    "id": recommendation_id, "campaign_id": campaign_id, "actor_country_id": actor,
                    "title": "Major regional infrastructure damage",
                    "reason": f"{damage.get('category') or 'Infrastructure'} damage is at severity {severity:.2f}; review repair capacity.",
                    "source_signal": signal, "affected_country_id": actor, "affected_region_id": region_id,
                    "confidence": 0.95, "urgency": min(1.0, 0.65 + severity * 0.35),
                    "expires_at_minute": now + 7 * 24 * 60, "optional_action_json": "",
                    "status": "active", "created_at_minute": now, "stale_reason": "",
                })
                existing.append(row)
                by_id[recommendation_id] = row
                changed = True

        for item in existing:
            if item.get("status") == "active" and (
                str(item.get("campaign_id") or ""),
                str(item.get("source_signal") or ""),
            ) not in current_signals:
                item["status"] = "stale"
                item["stale_reason"] = "The source signal is no longer active."
                changed = True

        if changed:
            state.update_table("advisor_recommendations", self._frame(recommendations_table, existing))

    @staticmethod
    def _meets_target(current: float, target: float, comparison: str) -> bool:
        if comparison == "at_most":
            return current <= target
        if comparison == "equals":
            return math.isclose(current, target, rel_tol=1e-9, abs_tol=1e-9)
        return current >= target

    @staticmethod
    def _progress(current: float, target: float, satisfied: bool, comparison: str) -> float:
        if comparison == "at_most":
            if target <= 0.0:
                return 1.0 if satisfied else 0.0
            return min(1.0, max(0.0, target / max(target, current)))
        if comparison == "equals":
            return 1.0 if satisfied else 0.0
        if target <= 0.0:
            return 1.0 if satisfied else 0.0
        return min(1.0, max(0.0, current / target))

    @staticmethod
    def _country_exists(state: GameState, country_tag: str) -> bool:
        countries = state.tables.get("countries")
        if countries is None or "id" not in countries.columns:
            return False
        return any(str(value).upper() == country_tag for value in countries["id"].to_list())

    @staticmethod
    def _defaults_for(table_name: str) -> dict[str, Any]:
        schema = next((schema for schema in BASE_TABLE_SCHEMAS if schema.name == table_name), None)
        if schema is None:
            return {}
        return {name: field.default for name, field in schema.columns.items()}

    @staticmethod
    def _frame(current: pl.DataFrame, rows: list[dict[str, Any]]) -> pl.DataFrame:
        return pl.DataFrame(rows, schema=current.schema, strict=False) if rows else current.head(0)

    @staticmethod
    def _rows(table: pl.DataFrame | None) -> list[dict[str, Any]]:
        return [] if table is None or table.is_empty() else table.to_dicts()

    @staticmethod
    def _json_object(value: Any, label: str) -> dict[str, Any]:
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, dict):
            raise ValueError(f"{label} must be a JSON object.")
        return parsed

    @staticmethod
    def _json_list(value: Any, label: str) -> list[Any]:
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, list):
            raise ValueError(f"{label} must be a JSON list.")
        return parsed

    @staticmethod
    def _tag(value: Any) -> str:
        return "" if value is None else str(value).strip().upper()

    @staticmethod
    def _tag_list(values: Any) -> set[str]:
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except (TypeError, ValueError):
                values = [item for item in values.split(",") if item]
        if not isinstance(values, (list, tuple, set)):
            return set()
        return {str(item).strip().upper() for item in values if str(item).strip()}

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return 0

    @staticmethod
    def _as_int(value: Any, fallback: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return fallback

    @staticmethod
    def _result(state: GameState, action: Any, status: str, reason: str) -> None:
        state.journal.append_command_result({
            "tick": int(state.globals.get("tick", 0)),
            "player_id": str(action.player_id),
            "action_type": type(action).__name__,
            "status": status,
            "reason": reason,
        })
