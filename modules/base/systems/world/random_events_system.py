from __future__ import annotations

import json
import math
from typing import Any

import polars as pl

from modules.base.systems.world.random_event_policy import (
    DEFAULT_CATEGORIES,
    DEFAULT_DAILY_CHANCE,
    DEFAULT_MAX_ACTIVE_EVENTS,
    EVENT_BY_TYPE,
    EVENT_CATALOG,
    EVENT_DEFINITIONS,
    MAX_ACTIVE_EVENTS_LIMIT,
    MAX_FREQUENCY_MULTIPLIER,
    MINUTES_PER_DAY,
    MIN_FREQUENCY_MULTIPLIER,
    clamp,
    effect_records,
)
from modules.base.systems.world.ai.random_event_policy import choose_event_response
from modules.base.systems.world.authority_policy import player_controls_country
from src.shared.actions import ActionRespondToRandomEvent, ActionSetRandomEventControls
from src.shared.determinism import DeterminismState, DeterministicRuntime
from src.shared.events import (
    EventNewDay,
    EventRandomEventLifecycleChanged,
    EventRandomEventTriggered,
)
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


# Compatibility exports for callers that used the original module constants.
BASE_DAILY_CHANCE = DEFAULT_DAILY_CHANCE
MAX_ACTIVE_EVENTS = DEFAULT_MAX_ACTIVE_EVENTS
_MINUTES_PER_DAY = MINUTES_PER_DAY
_TOTAL_WEIGHT = sum(float(entry["weight"]) for entry in EVENT_CATALOG)
MAX_SCENARIO_EVENT_SEED = (1 << 63) - 1


class RandomEventsSystem(ISystem):
    """Own deterministic event eligibility, lifecycle records, and controls."""

    access = SystemAccess(
        reads=frozenset(
            {
                "regions",
                "countries",
                "random_event_instances",
                "random_event_effects",
                "random_event_responses",
                "random_event_controls",
                "random_event_cooldowns",
            }
        ),
        writes=frozenset(
            {
                "countries",
                "random_event_instances",
                "random_event_effects",
                "random_event_responses",
                "random_event_controls",
                "random_event_cooldowns",
            }
        ),
        handles=frozenset(
            {ActionRespondToRandomEvent, ActionSetRandomEventControls}
        ),
        phase=SystemPhase.RANDOM_EVENTS,
    )

    @property
    def id(self) -> str:
        return "base.random_events"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time"]

    def update(self, state: GameState, delta_time: float) -> None:
        required = {
            "random_event_instances",
            "random_event_effects",
            "random_event_responses",
            "random_event_controls",
            "random_event_cooldowns",
        }
        if not required.issubset(state.tables):
            return

        now = max(0, int(state.time.total_minutes))
        self._initialize_controls(state, now)
        projection_dirty = self._import_legacy_events(state, now)
        resolved_ids = self._resolve_due_instances(state, now)
        projection_dirty |= bool(resolved_ids)
        self._resolve_due_effects(state, resolved_ids)
        self._process_actions(state, now)

        runtime, event_determinism = self._event_runtime(state)
        processed_days: set[tuple[int, int, int]] = set()
        for event in state.events:
            if not isinstance(event, EventNewDay):
                continue
            date_key = (event.year, event.month, event.day)
            if date_key in processed_days:
                continue
            processed_days.add(date_key)
            projection_dirty |= self._roll_daily_event(state, now, runtime)

        self._auto_respond_to_ai_events(state, now)

        self._persist_event_runtime(state, event_determinism)

        if (
            projection_dirty
            or bool(state.globals.get("random_event_projection_dirty"))
            or not isinstance(state.globals.get("active_events"), list)
        ):
            self._sync_legacy_projection(state)

    def _initialize_controls(self, state: GameState, now: int) -> None:
        state.globals.setdefault("random_events_enabled", True)
        state.globals.setdefault("random_event_frequency_multiplier", 1.0)
        state.globals.setdefault("random_event_max_active_events", DEFAULT_MAX_ACTIVE_EVENTS)
        state.globals.setdefault("scenario_admin_id", "local_player")
        state.globals.setdefault("random_event_seed", None)

        table = state.tables["random_event_controls"]
        existing = {str(row.get("category") or "") for row in table.iter_rows(named=True)}
        additions = [
            {
                "category": category,
                "enabled": True,
                "frequency_multiplier": 1.0,
                "updated_at_minute": now,
                "updated_by": "scenario",
            }
            for category in DEFAULT_CATEGORIES
            if category not in existing
        ]
        if additions:
            self._append_rows(state, "random_event_controls", additions)

    def _import_legacy_events(self, state: GameState, now: int) -> bool:
        if int(state.globals.get("random_event_state_version", 0) or 0) >= 1:
            return False

        legacy = state.globals.get("active_events", [])
        regions = self._region_index(state)
        country_ids = self._country_ids(state)
        known_ids = set(
            str(value)
            for value in state.tables["random_event_instances"].get_column("id").to_list()
        )
        instances: list[dict[str, Any]] = []
        effects: list[dict[str, Any]] = []
        if isinstance(legacy, list):
            for index, raw in enumerate(legacy):
                if not isinstance(raw, dict):
                    continue
                event_type = str(raw.get("event_type") or "legacy_unknown")
                definition = EVENT_BY_TYPE.get(event_type)
                try:
                    region_id = int(raw.get("region_id") or 0)
                    started = max(0, int(raw.get("start_minute") or 0))
                    expires = max(started, int(raw.get("expire_minute") or started))
                    severity = clamp(float(raw.get("severity") or 0.0), 0.0, 1.0)
                except (TypeError, ValueError, OverflowError):
                    continue
                event_id = str(raw.get("id") or f"legacy-random-event-{index:06d}")
                if event_id in known_ids:
                    continue
                region = regions.get(region_id, {})
                owner = self._tag(region.get("owner"))
                if owner not in country_ids:
                    owner = ""
                status = "active" if expires > now else "resolved"
                label = str(raw.get("label") or (definition.label if definition else event_type))
                category = definition.category if definition else "legacy_unknown"
                seed = self._integer(raw.get("seed"), 0) & 0x7FFF_FFFF_FFFF_FFFF
                effects_json = "[]"
                responses_json = "[]"
                if definition is not None:
                    response_options = self._response_options(definition)
                    responses_json = self._json(response_options)
                    effect_rows = effect_records(
                        event_id=event_id,
                        definition=definition,
                        severity=severity,
                        region_id=region_id,
                        country_id=owner,
                        starts_at_minute=started,
                        expires_at_minute=expires,
                    )
                    effect_rows = [row for row in effect_rows if row["subject_id"]]
                    effects.extend(effect_rows)
                    effects_json = self._json(
                        [
                            {
                                "category": row["category"],
                                "magnitude": row["magnitude"],
                                "subject_type": row["subject_type"],
                                "subject_id": row["subject_id"],
                            }
                            for row in effect_rows
                        ]
                    )
                instances.append(
                    {
                        "id": event_id,
                        "event_type": event_type,
                        "label": label,
                        "category": category,
                        "target_scope": "region",
                        "region_id": region_id,
                        "country_id": owner,
                        "seed": seed,
                        "triggered_at_minute": started,
                        "starts_at_minute": started,
                        "expires_at_minute": expires,
                        "severity": severity,
                        "status": status,
                        "response_id": str(raw.get("response_id") or ""),
                        "response_country_id": str(raw.get("response_country_id") or ""),
                        "effects_json": effects_json,
                        "response_options_json": responses_json,
                        "recovery_state_json": str(raw.get("recovery_state_json") or "{}"),
                        "reason": "Imported from a legacy active-event save.",
                        "next_update_at_minute": expires if status == "active" else 0,
                    }
                )
                known_ids.add(event_id)

        self._append_rows(state, "random_event_instances", instances)
        self._append_rows(state, "random_event_effects", effects)
        state.globals["random_event_state_version"] = 1
        return bool(instances)

    def _resolve_due_instances(self, state: GameState, now: int) -> list[str]:
        instances = state.tables["random_event_instances"]
        revision = int(state.table_revisions.get("random_event_instances", 0))
        cached_revision = int(state.globals.get("random_event_due_cursor_revision", -1))
        next_due = int(state.globals.get("random_event_next_instance_due_minute", -1))
        if cached_revision == revision and next_due > now:
            return []

        due = instances.filter(
            (pl.col("status") == "active")
            & (pl.col("next_update_at_minute") <= now)
        )
        if due.is_empty():
            self._refresh_instance_due_cursor(state)
            return []

        due_rows = due.sort("id").to_dicts()
        due_ids = [str(row["id"]) for row in due_rows]
        reason = "The configured event duration elapsed."
        updated = instances.with_columns(
            pl.when(pl.col("id").is_in(due_ids))
            .then(pl.lit("resolved"))
            .otherwise(pl.col("status"))
            .alias("status"),
            pl.when(pl.col("id").is_in(due_ids))
            .then(pl.lit(reason))
            .otherwise(pl.col("reason"))
            .alias("reason"),
            pl.when(pl.col("id").is_in(due_ids))
            .then(pl.lit(0, dtype=pl.Int64))
            .otherwise(pl.col("next_update_at_minute"))
            .alias("next_update_at_minute"),
        )
        state.update_table("random_event_instances", updated)
        self._refresh_instance_due_cursor(state)
        for row in due_rows:
            state.events.append(
                EventRandomEventLifecycleChanged(
                    event_id=str(row["id"]),
                    event_type=str(row["event_type"]),
                    status="resolved",
                    reason=reason,
                    at_minute=now,
                )
            )
        return due_ids

    @staticmethod
    def _refresh_instance_due_cursor(state: GameState) -> None:
        instances = state.tables["random_event_instances"]
        active = instances.filter(pl.col("status") == "active")
        next_due = (
            int(active.get_column("next_update_at_minute").min())
            if not active.is_empty()
            else (1 << 63) - 1
        )
        state.globals["random_event_next_instance_due_minute"] = next_due
        state.globals["random_event_due_cursor_revision"] = int(
            state.table_revisions.get("random_event_instances", 0)
        )

    def _resolve_due_effects(self, state: GameState, event_ids: list[str]) -> None:
        if not event_ids:
            return
        effects = state.tables["random_event_effects"]
        if effects.is_empty():
            return
        due_effects = effects.filter(
            pl.col("event_id").is_in(event_ids)
            & pl.col("status").is_in(["pending", "active"])
        )
        if due_effects.is_empty():
            return
        effect_ids = due_effects.get_column("id").to_list()
        state.update_table(
            "random_event_effects",
            effects.with_columns(
                pl.when(pl.col("id").is_in(effect_ids))
                .then(pl.lit("resolved"))
                .otherwise(pl.col("status"))
                .alias("status"),
                pl.when(pl.col("id").is_in(effect_ids))
                .then(pl.lit("{}"))
                .otherwise(pl.col("recovery_state_json"))
                .alias("recovery_state_json"),
            ),
        )

    def _process_actions(self, state: GameState, now: int) -> None:
        for action in state.current_actions:
            if isinstance(action, ActionSetRandomEventControls):
                self._set_controls(state, action, now)
            elif isinstance(action, ActionRespondToRandomEvent):
                self._respond_to_event(state, action, now)

    def _set_controls(
        self,
        state: GameState,
        action: ActionSetRandomEventControls,
        now: int,
    ) -> None:
        category = str(action.category or "").strip().lower()
        changes_category = action.category_enabled is not None or (
            action.frequency_multiplier is not None and bool(category)
        )
        if not self._is_scenario_admin(state, action.player_id):
            self._record_result(state, action, "rejected", "Only the scenario administrator may change event controls.")
            return
        if all(
            value is None
            for value in (
                action.enabled,
                action.category_enabled,
                action.frequency_multiplier,
                action.maximum_active_events,
                action.seed,
            )
        ):
            self._record_result(state, action, "rejected", "At least one event-control value is required.")
            return
        controls = state.tables["random_event_controls"]
        categories = set(controls.get_column("category").to_list())
        if changes_category and category not in categories:
            self._record_result(state, action, "rejected", f"Unknown event category '{category}'.")
            return
        if action.frequency_multiplier is not None:
            multiplier = self._finite(action.frequency_multiplier)
            if (
                multiplier is None
                or not MIN_FREQUENCY_MULTIPLIER <= multiplier <= MAX_FREQUENCY_MULTIPLIER
            ):
                self._record_result(state, action, "rejected", "Event frequency must be finite and within 0–4.")
                return
        if action.maximum_active_events is not None:
            if isinstance(action.maximum_active_events, bool):
                self._record_result(state, action, "rejected", "Maximum active events must be a positive integer.")
                return
            maximum = self._integer(action.maximum_active_events, -1)
            if not 1 <= maximum <= MAX_ACTIVE_EVENTS_LIMIT:
                self._record_result(state, action, "rejected", "Maximum active events must be between 1 and 100000.")
                return
        if action.seed is not None and (
            isinstance(action.seed, bool)
            or not isinstance(action.seed, int)
            or not 0 <= action.seed <= MAX_SCENARIO_EVENT_SEED
        ):
            self._record_result(state, action, "rejected", "Event seed must be an integer between 0 and 2^63−1.")
            return

        if changes_category:
            rows = controls.to_dicts()
            for row in rows:
                if str(row["category"]) != category:
                    continue
                if action.category_enabled is not None:
                    row["enabled"] = bool(action.category_enabled)
                if action.frequency_multiplier is not None:
                    row["frequency_multiplier"] = float(action.frequency_multiplier)
                row["updated_at_minute"] = now
                row["updated_by"] = str(action.player_id)
            self._write_rows(state, "random_event_controls", rows)
        if action.enabled is not None:
            state.globals["random_events_enabled"] = bool(action.enabled)
        if action.frequency_multiplier is not None and not category:
            state.globals["random_event_frequency_multiplier"] = float(action.frequency_multiplier)
        if action.maximum_active_events is not None:
            state.globals["random_event_max_active_events"] = int(action.maximum_active_events)
        if action.seed is not None:
            event_determinism = DeterminismState(seed=int(action.seed))
            state.globals["random_event_seed"] = int(action.seed)
            state.globals["random_event_rng_state"] = int(event_determinism.rng_state)
            state.globals["random_event_id_sequence"] = 0
        state.globals["random_event_controls_changed_at_minute"] = now
        changed_category = category if changes_category else "all"
        state.events.append(
            EventRandomEventLifecycleChanged(
                event_id="",
                event_type=changed_category,
                status="controls_changed",
                reason="Scenario administrator updated event controls; active instances retain their configured completion rule.",
                at_minute=now,
            )
        )
        self._record_result(state, action, "applied", "Event controls updated.")

    def _respond_to_event(
        self,
        state: GameState,
        action: ActionRespondToRandomEvent,
        now: int,
        *,
        trusted_ai: bool = False,
    ) -> None:
        instances = state.tables["random_event_instances"]
        matches = instances.filter(pl.col("id") == str(action.event_id))
        if matches.is_empty():
            self._reject_response(state, action, now, "The selected event no longer exists.")
            return
        instance = matches.row(0, named=True)
        event_type = str(instance["event_type"])
        if str(instance["status"]) != "active" or int(instance["expires_at_minute"]) <= now:
            self._reject_response(state, action, now, "The selected event is no longer active.", event_type)
            return
        if str(instance.get("response_id") or ""):
            self._reject_response(state, action, now, "A response has already been applied to this event.", event_type)
            return
        definition = EVENT_BY_TYPE.get(event_type)
        response = next(
            (
                option
                for option in (definition.responses if definition is not None else ())
                if option.response_id == str(action.response_id)
            ),
            None,
        )
        if response is None:
            self._reject_response(state, action, now, "That response is not available for this event.", event_type)
            return
        available_at = int(instance["starts_at_minute"]) + (
            response.available_after_days * MINUTES_PER_DAY
        )
        if now < available_at:
            self._reject_response(
                state,
                action,
                now,
                f"That response becomes available at game minute {available_at}.",
                event_type,
            )
            return
        if str(instance.get("response_id") or ""):
            self._reject_response(state, action, now, "This event has already received a response.", event_type)
            return
        response_time = int(instance["starts_at_minute"]) + response.available_after_days * MINUTES_PER_DAY
        if now < response_time:
            self._reject_response(state, action, now, "That response is not available yet.", event_type)
            return

        region_id = int(instance.get("region_id") or 0)
        region = self._region_index(state).get(region_id)
        if region is None:
            self._reject_response(state, action, now, "The event target region no longer exists.", event_type)
            return
        if response.authority_scope == "region_owner":
            country_id = self._tag(region.get("owner"))
        else:
            self._reject_response(state, action, now, "The response authority is not supported.", event_type)
            return
        requested_country = self._tag(action.country_tag)
        if not country_id or requested_country != country_id:
            self._reject_response(state, action, now, "Only the current regional owner may fund this response.", event_type)
            return
        if not trusted_ai and not player_controls_country(state, action.player_id, country_id):
            self._reject_response(state, action, now, "The actor cannot control the response funding country.", event_type)
            return

        countries = state.tables.get("countries")
        if countries is None or "id" not in countries.columns or "money_reserves" not in countries.columns:
            self._reject_response(state, action, now, "The response funding account is unavailable.", event_type)
            return
        country_row = next(
            (row for row in countries.iter_rows(named=True) if self._tag(row.get("id")) == country_id),
            None,
        )
        if country_row is None:
            self._reject_response(state, action, now, "The response funding country no longer exists.", event_type)
            return
        country_storage_id = str(country_row["id"])
        funds = self._finite(country_row.get("money_reserves"))
        cost = self._finite(response.cost)
        if funds is None or cost is None or cost < 0.0 or funds < cost:
            self._reject_response(state, action, now, "The country lacks funds for this response.", event_type)
            return

        runtime, event_determinism = self._event_runtime(state)
        risk_triggered = response.risk > 0.0 and runtime.random() < response.risk
        secondary_rows = self._secondary_effect_rows(
            event_id=str(instance["id"]),
            country_id=country_id,
            response=response,
            now=now,
            expires=int(instance["expires_at_minute"]),
        ) if risk_triggered else []
        secondary_payload = [
            {"category": row["category"], "magnitude": row["magnitude"], "unit": row["unit"]}
            for row in secondary_rows
        ]
        response_record = {
            "id": runtime.next_id("random-event-response", int(state.globals.get("tick", 0))),
            "event_id": str(instance["id"]),
            "response_id": response.response_id,
            "player_id": str(action.player_id),
            "country_id": country_id,
            "cost": cost,
            "requested_at_minute": now,
            "applied_at_minute": now,
            "mitigation": response.mitigation,
            "risk": response.risk,
            "secondary_effects_json": self._json(secondary_payload),
            "status": "applied",
            "reason": "Response accepted; risk outcome was resolved deterministically.",
        }
        event_id = str(instance["id"])
        state.update_table(
            "countries",
            countries.with_columns(
                pl.when(pl.col("id").cast(pl.String) == country_storage_id)
                .then(pl.lit(funds - cost))
                .otherwise(pl.col("money_reserves"))
                .alias("money_reserves")
            ),
        )
        state.update_table(
            "random_event_instances",
            instances.with_columns(
                pl.when(pl.col("id") == event_id)
                .then(pl.lit(response.response_id))
                .otherwise(pl.col("response_id"))
                .alias("response_id"),
                pl.when(pl.col("id") == event_id)
                .then(pl.lit(country_id))
                .otherwise(pl.col("response_country_id"))
                .alias("response_country_id"),
            ),
        )
        effects = state.tables["random_event_effects"]
        infrastructure_categories = [
            effect.category
            for event_definition in EVENT_DEFINITIONS
            for effect in event_definition.effects
            if effect.category.startswith("infrastructure_")
        ]
        adverse = (pl.col("magnitude") < 0.0) | pl.col("category").is_in(
            infrastructure_categories
        )
        infrastructure_effect = pl.col("category").is_in(infrastructure_categories)
        state.update_table(
            "random_event_effects",
            effects.with_columns(
                pl.when(
                    (pl.col("event_id") == event_id)
                    & pl.col("status").is_in(["pending", "active"])
                    & adverse
                )
                .then(pl.col("magnitude") * (1.0 - response.mitigation))
                .otherwise(pl.col("magnitude"))
                .alias("magnitude"),
                pl.when(
                    (pl.col("event_id") == event_id)
                    & pl.col("status").is_in(["pending", "active"])
                    & adverse
                )
                .then(infrastructure_effect)
                .otherwise(pl.col("mitigation_pending"))
                .alias("mitigation_pending"),
            ),
        )
        self._append_rows(state, "random_event_responses", [response_record])
        self._append_rows(state, "random_event_effects", secondary_rows)
        self._persist_event_runtime(state, event_determinism)
        state.events.append(
            EventRandomEventLifecycleChanged(
                event_id=event_id,
                event_type=event_type,
                status="response_applied",
                reason=f"{response.response_id} cost {cost:.2f}; mitigation {response.mitigation:.0%}; risk {'triggered' if risk_triggered else 'avoided'}.",
                at_minute=now,
            )
        )
        state.globals["random_event_projection_dirty"] = True
        self._record_result(state, action, "applied", "Event response accepted.")

    def _reject_response(
        self,
        state: GameState,
        action: ActionRespondToRandomEvent,
        now: int,
        reason: str,
        event_type: str = "",
    ) -> None:
        self._record_result(state, action, "rejected", reason)
        state.events.append(
            EventRandomEventLifecycleChanged(
                event_id=str(action.event_id),
                event_type=event_type,
                status="response_rejected",
                reason=reason,
                at_minute=now,
            )
        )

    @staticmethod
    def _secondary_effect_rows(
        *,
        event_id: str,
        country_id: str,
        response: Any,
        now: int,
        expires: int,
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": f"{event_id}:response:{response.response_id}:{category}",
                "event_id": event_id,
                "category": category,
                "subject_type": "country",
                "subject_id": country_id,
                "magnitude": float(magnitude),
                "unit": unit,
                "application_mode": "immediate",
                "starts_at_minute": now,
                "expires_at_minute": expires,
                "last_applied_at_minute": 0,
                "status": "pending",
                "mitigation_pending": False,
                "recovery_state_json": "{}",
            }
            for category, magnitude, unit in response.secondary_effects
        ]

    def _roll_daily_event(
        self,
        state: GameState,
        now: int,
        runtime: DeterministicRuntime,
    ) -> bool:
        if not bool(state.globals.get("random_events_enabled", True)):
            return False
        active = state.tables["random_event_instances"].filter(pl.col("status") == "active")
        maximum = self._integer(
            state.globals.get("random_event_max_active_events"), DEFAULT_MAX_ACTIVE_EVENTS
        )
        if active.height >= max(1, min(MAX_ACTIVE_EVENTS_LIMIT, maximum)):
            return False

        controls = {
            str(row["category"]): row
            for row in state.tables["random_event_controls"].iter_rows(named=True)
        }
        enabled_definitions = [
            definition
            for definition in EVENT_DEFINITIONS
            if bool(controls.get(definition.category, {}).get("enabled", False))
            and self._finite(controls.get(definition.category, {}).get("frequency_multiplier"))
            and float(controls[definition.category]["frequency_multiplier"]) > 0.0
        ]
        if not enabled_definitions:
            return False

        global_frequency = self._finite(state.globals.get("random_event_frequency_multiplier"))
        if global_frequency is None or global_frequency <= 0.0:
            return False
        global_frequency = clamp(global_frequency, 0.0, MAX_FREQUENCY_MULTIPLIER)
        base_chance = self._finite(
            state.globals.get("random_event_daily_chance", DEFAULT_DAILY_CHANCE)
        )
        if base_chance is None:
            base_chance = DEFAULT_DAILY_CHANCE
        base_chance = clamp(base_chance, 0.0, 1.0)

        region_rows = self._eligible_region_rows(state)
        if not region_rows:
            daily_chance = self._daily_chance(
                enabled_definitions, controls, global_frequency, base_chance
            )
            if runtime.random() >= daily_chance:
                return False
            definition = self._weighted_choice(enabled_definitions, controls, runtime)
            self._record_skipped_no_target(state, definition, now, runtime)
            return True

        cooldowns = {
            (str(row["event_type"]), str(row["target_scope"]), str(row["target_id"])): int(row["cooldown_until_minute"])
            for row in state.tables["random_event_cooldowns"].iter_rows(named=True)
        }
        candidates: list[tuple[Any, list[dict[str, Any]]]] = []
        for definition in enabled_definitions:
            targets = [
                region
                for region in region_rows
                if cooldowns.get(
                    (definition.event_type, definition.eligible_scope, str(region["id"])), 0
                ) <= now
            ]
            if targets:
                candidates.append((definition, targets))
        if not candidates:
            return False

        candidate_definitions = [definition for definition, _ in candidates]
        daily_chance = self._daily_chance(
            candidate_definitions, controls, global_frequency, base_chance
        )
        if runtime.random() >= daily_chance:
            return False
        definition = self._weighted_choice(candidate_definitions, controls, runtime)
        target_rows = next(rows for candidate, rows in candidates if candidate.event_type == definition.event_type)
        target = runtime.choice(target_rows)
        self._create_instance(state, definition, target, now, runtime)
        return True

    @staticmethod
    def _daily_chance(
        definitions: list[Any],
        controls: dict[str, dict[str, Any]],
        global_frequency: float,
        base_chance: float,
    ) -> float:
        all_weight = sum(definition.weight for definition in EVENT_DEFINITIONS)
        adjusted_weight = sum(
            definition.weight
            * clamp(
                float(controls[definition.category]["frequency_multiplier"]),
                MIN_FREQUENCY_MULTIPLIER,
                MAX_FREQUENCY_MULTIPLIER,
            )
            for definition in definitions
        )
        if all_weight <= 0.0:
            return 0.0
        return clamp(base_chance * global_frequency * adjusted_weight / all_weight, 0.0, 1.0)

    @staticmethod
    def _weighted_choice(definitions: list[Any], controls: dict[str, dict[str, Any]], runtime: DeterministicRuntime) -> Any:
        weights = [
            definition.weight
            * clamp(
                float(controls[definition.category]["frequency_multiplier"]),
                MIN_FREQUENCY_MULTIPLIER,
                MAX_FREQUENCY_MULTIPLIER,
            )
            for definition in definitions
        ]
        total = sum(weights)
        if total <= 0.0:
            return definitions[0]
        roll = runtime.uniform(0.0, total)
        cumulative = 0.0
        for definition, weight in zip(definitions, weights):
            cumulative += weight
            if roll < cumulative:
                return definition
        return definitions[-1]

    def _create_instance(
        self,
        state: GameState,
        definition: Any,
        target: dict[str, Any],
        now: int,
        runtime: DeterministicRuntime,
    ) -> None:
        region_id = int(target["id"])
        country_id = self._tag(target.get("owner"))
        severity = round(runtime.uniform(definition.severity_minimum, definition.severity_maximum), 2)
        duration = definition.duration_days * MINUTES_PER_DAY
        expires = now + duration
        event_id = runtime.next_id("random-event", int(state.globals.get("tick", 0)))
        seed = int(runtime.next_u64() & 0x7FFF_FFFF_FFFF_FFFF) or 1
        effects = effect_records(
            event_id=event_id,
            definition=definition,
            severity=severity,
            region_id=region_id,
            country_id=country_id,
            starts_at_minute=now,
            expires_at_minute=expires,
        )
        effects = [row for row in effects if row["subject_id"]]
        row = {
            "id": event_id,
            "event_type": definition.event_type,
            "label": definition.label,
            "category": definition.category,
            "target_scope": definition.eligible_scope,
            "region_id": region_id,
            "country_id": country_id,
            "seed": seed,
            "triggered_at_minute": now,
            "starts_at_minute": now,
            "expires_at_minute": expires,
            "severity": severity,
            "status": "active",
            "response_id": "",
            "response_country_id": "",
            "effects_json": self._json(
                [
                    {
                        "category": effect["category"],
                        "magnitude": effect["magnitude"],
                        "subject_type": effect["subject_type"],
                        "subject_id": effect["subject_id"],
                    }
                    for effect in effects
                ]
            ),
            "response_options_json": self._json(self._response_options(definition)),
            "recovery_state_json": "{}",
            "reason": "Event conditions and deterministic probability roll were satisfied.",
            "next_update_at_minute": expires,
        }
        self._append_rows(state, "random_event_instances", [row])
        self._append_rows(state, "random_event_effects", effects)
        cooldown = {
            "event_type": definition.event_type,
            "target_scope": definition.eligible_scope,
            "target_id": str(region_id),
            "cooldown_until_minute": now + definition.cooldown_days * MINUTES_PER_DAY,
        }
        self._upsert_cooldown(state, cooldown)
        state.events.append(
            EventRandomEventTriggered(
                event_id=event_id,
                event_type=definition.event_type,
                region_id=region_id,
                severity=severity,
                seed=seed,
                category=definition.category,
            )
        )
        state.globals["random_event_projection_dirty"] = True

    def _record_skipped_no_target(
        self,
        state: GameState,
        definition: Any,
        now: int,
        runtime: DeterministicRuntime,
    ) -> None:
        event_id = runtime.next_id("random-event", int(state.globals.get("tick", 0)))
        seed = int(runtime.next_u64() & 0x7FFF_FFFF_FFFF_FFFF) or 1
        reason = "No eligible owned region and country currently exist for this event."
        state_row = {
            "id": event_id,
            "event_type": definition.event_type,
            "label": definition.label,
            "category": definition.category,
            "target_scope": definition.eligible_scope,
            "region_id": 0,
            "country_id": "",
            "seed": seed,
            "triggered_at_minute": now,
            "starts_at_minute": now,
            "expires_at_minute": now,
            "severity": round(runtime.uniform(definition.severity_minimum, definition.severity_maximum), 2),
            "status": "skipped",
            "response_id": "",
            "response_country_id": "",
            "effects_json": "[]",
            "response_options_json": self._json(self._response_options(definition)),
            "recovery_state_json": "{}",
            "reason": reason,
            "next_update_at_minute": 0,
        }
        self._append_rows(state, "random_event_instances", [state_row])
        state.events.append(
            EventRandomEventLifecycleChanged(
                event_id=event_id,
                event_type=definition.event_type,
                status="skipped",
                reason=reason,
                at_minute=now,
            )
        )

    def _auto_respond_to_ai_events(self, state: GameState, now: int) -> None:
        instances = state.tables["random_event_instances"]
        active = instances.filter(
            (pl.col("status") == "active")
            & (pl.col("response_id") == "")
        ).sort(["starts_at_minute", "id"])
        if active.is_empty():
            return

        player_map = state.globals.get("player_country_map", {})
        player_countries = {
            self._tag(country_id)
            for country_id in player_map.values()
        } if isinstance(player_map, dict) else set()
        player_countries.add(self._tag(state.globals.get("player_tag")))
        player_countries.discard("")
        countries = state.tables.get("countries")
        regions = state.tables.get("regions")
        if countries is None or regions is None:
            return
        country_rows = {
            self._tag(row.get("id")): row
            for row in countries.iter_rows(named=True)
        }
        region_rows = {
            int(row.get("id") or 0): row
            for row in regions.iter_rows(named=True)
        }

        for instance in active.iter_rows(named=True):
            event_type = str(instance.get("event_type") or "")
            definition = EVENT_BY_TYPE.get(event_type)
            region = region_rows.get(int(instance.get("region_id") or 0))
            owner = self._tag(region.get("owner")) if region is not None else ""
            if (
                definition is None
                or region is None
                or not owner
                or owner in player_countries
            ):
                continue
            country = country_rows.get(owner)
            if country is None:
                continue
            response = choose_event_response(
                definition.responses,
                treasury=self._finite(country.get("money_reserves")) or 0.0,
                starts_at_minute=int(instance.get("starts_at_minute") or 0),
                now_minute=now,
                minutes_per_day=MINUTES_PER_DAY,
            )
            if response is None:
                continue
            self._respond_to_event(
                state,
                ActionRespondToRandomEvent(
                    player_id="AI",
                    event_id=str(instance["id"]),
                    response_id=response.response_id,
                    country_tag=owner,
                ),
                now,
                trusted_ai=True,
            )

    def _eligible_region_rows(self, state: GameState) -> list[dict[str, Any]]:
        regions = state.tables.get("regions")
        countries = self._country_ids(state)
        if regions is None or regions.is_empty() or "id" not in regions.columns or not countries:
            return []
        owner_column = "owner" if "owner" in regions.columns else None
        if owner_column is None:
            return []
        return sorted(
            (
                row
                for row in regions.iter_rows(named=True)
                if self._tag(row.get(owner_column)) in countries
            ),
            key=lambda row: int(row["id"]),
        )

    def _upsert_cooldown(self, state: GameState, row: dict[str, Any]) -> None:
        cooldowns = state.tables["random_event_cooldowns"]
        matches = (
            (pl.col("event_type") == row["event_type"])
            & (pl.col("target_scope") == row["target_scope"])
            & (pl.col("target_id") == row["target_id"])
        )
        if cooldowns.is_empty() or cooldowns.filter(matches).is_empty():
            self._append_rows(state, "random_event_cooldowns", [row])
            return
        state.update_table(
            "random_event_cooldowns",
            cooldowns.with_columns(
                pl.when(matches)
                .then(pl.lit(int(row["cooldown_until_minute"])))
                .otherwise(pl.col("cooldown_until_minute"))
                .alias("cooldown_until_minute")
            ),
        )

    def _sync_legacy_projection(self, state: GameState) -> None:
        instances = state.tables["random_event_instances"].filter(pl.col("status") == "active")
        state.globals["active_events"] = [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "label": row["label"],
                "region_id": int(row["region_id"]),
                "severity": float(row["severity"]),
                "start_minute": int(row["starts_at_minute"]),
                "expire_minute": int(row["expires_at_minute"]),
                "category": row["category"],
                "seed": int(row["seed"]),
                "effects_json": row["effects_json"],
                "response_options_json": row["response_options_json"],
                "response_id": row["response_id"],
                "status": row["status"],
            }
            for row in instances.sort("starts_at_minute", descending=True).iter_rows(named=True)
        ]
        state.globals["random_event_projection_dirty"] = False

    @staticmethod
    def _response_options(definition: Any) -> list[dict[str, Any]]:
        return [
            {
                "response_id": response.response_id,
                "authority_scope": response.authority_scope,
                "cost": response.cost,
                "available_after_days": response.available_after_days,
                "mitigation": response.mitigation,
                "risk": response.risk,
                "secondary_effects": [
                    {"category": category, "magnitude": magnitude, "unit": unit}
                    for category, magnitude, unit in response.secondary_effects
                ],
            }
            for response in definition.responses
        ]

    @staticmethod
    def _region_index(state: GameState) -> dict[int, dict[str, Any]]:
        regions = state.tables.get("regions")
        if regions is None or regions.is_empty() or "id" not in regions.columns:
            return {}
        return {int(row["id"]): row for row in regions.iter_rows(named=True)}

    @staticmethod
    def _country_ids(state: GameState) -> set[str]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return set()
        return {str(value).strip().upper() for value in countries.get_column("id").to_list() if value}

    @staticmethod
    def _is_scenario_admin(state: GameState, player_id: str) -> bool:
        actor = str(player_id or "")
        if actor == str(state.globals.get("scenario_admin_id", "local_player")):
            return True
        permissions = state.globals.get("command_permissions")
        return isinstance(permissions, dict) and permissions.get(actor) == "*"

    def _event_runtime(
        self,
        state: GameState,
    ) -> tuple[DeterministicRuntime, DeterminismState | None]:
        configured_seed = state.globals.get("random_event_seed")
        if configured_seed is None:
            return DeterministicRuntime(state.determinism), None
        try:
            seed = int(configured_seed)
            rng_state = int(state.globals.get("random_event_rng_state", seed))
            id_sequence = max(0, int(state.globals.get("random_event_id_sequence", 0)))
        except (TypeError, ValueError, OverflowError):
            return DeterministicRuntime(state.determinism), None
        dedicated = DeterminismState(
            seed=seed,
            rng_state=rng_state,
            id_sequence=id_sequence,
        )
        return DeterministicRuntime(dedicated), dedicated

    @staticmethod
    def _persist_event_runtime(
        state: GameState,
        dedicated: DeterminismState | None,
    ) -> None:
        if dedicated is None:
            return
        state.globals["random_event_rng_state"] = int(dedicated.rng_state)
        state.globals["random_event_id_sequence"] = int(dedicated.id_sequence)

    @staticmethod
    def _record_result(state: GameState, action: Any, status: str, reason: str) -> None:
        state.journal.append_command_result(
            {
                "tick": int(state.globals.get("tick", 0)),
                "player_id": str(action.player_id),
                "action_type": type(action).__name__,
                "status": status,
                "reason": reason,
            }
        )

    @staticmethod
    def _write_rows(state: GameState, name: str, rows: list[dict[str, Any]]) -> None:
        original = state.tables[name]
        if not rows:
            state.update_table(name, original.head(0))
            return
        frame = pl.DataFrame(rows, infer_schema_length=None)
        for column, dtype in original.schema.items():
            if column in frame.columns:
                frame = frame.with_columns(pl.col(column).cast(dtype, strict=False))
        columns = [column for column in original.columns if column in frame.columns]
        columns.extend(column for column in frame.columns if column not in columns)
        state.update_table(name, frame.select(columns))

    @classmethod
    def _append_rows(cls, state: GameState, name: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        original = state.tables[name]
        additions = pl.DataFrame(rows, infer_schema_length=None)
        for column, dtype in original.schema.items():
            if column in additions.columns:
                additions = additions.with_columns(pl.col(column).cast(dtype, strict=False))
            else:
                additions = additions.with_columns(pl.lit(None, dtype=dtype).alias(column))
        additions = additions.select(original.columns)
        if original.is_empty():
            state.update_table(name, additions)
        else:
            state.update_table(name, pl.concat([original, additions], how="vertical"))

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _integer(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return default

    @staticmethod
    def _finite(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if math.isfinite(number) else None
