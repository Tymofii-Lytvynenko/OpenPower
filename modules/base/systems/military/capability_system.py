"""Authoritative unit training and derived capability projections."""

from __future__ import annotations

import json
import weakref
from typing import Any

import polars as pl

from modules.base.systems.military.capability_catalog import (
    TRAINING_LEVELS,
    get_role_profile,
    project_capabilities,
    researched_capabilities,
    trained_capabilities,
)
from modules.base.systems.military.training_eligibility_policy import (
    facility_domains,
    select_training_facility,
    training_cost,
    training_level_steps,
)
from modules.base.systems.military.authority_policy import player_controls_country
from src.shared.actions import ActionCancelUnitTraining, ActionSetUnitTrainingPaused, ActionTrainUnit
from src.shared.events import EventRealSecond
from src.shared.state import GameState
from src.shared.system_state import SYSTEM_STATE_CACHE
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


_SECONDS_PER_DAY = 24 * 60 * 60
_TRAINING_ORDER_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "unit_id": pl.Utf8,
    "country_id": pl.Utf8,
    "facility_id": pl.Utf8,
    "training_location_region_id": pl.Int32,
    "from_level": pl.Utf8,
    "target_level": pl.Utf8,
    "progress": pl.Float64,
    "required_days": pl.Float64,
    "cost": pl.Float64,
    "status": pl.Utf8,
    "return_region_id": pl.Int32,
    "return_latitude": pl.Float64,
    "return_longitude": pl.Float64,
    "started_at_minute": pl.Int64,
    "updated_at_minute": pl.Int64,
    "completed_at_minute": pl.Int64,
    "cancelled_at_minute": pl.Int64,
    "last_event": pl.Utf8,
    "last_event_at_minute": pl.Int64,
    "blocking_reason": pl.Utf8,
}
_TRAINING_FACILITY_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "country_id": pl.Utf8,
    "region_id": pl.Int32,
    "supported_domains": pl.List(pl.Utf8),
    "capacity": pl.Int32,
    "instructor_count": pl.Int32,
    "enabled": pl.Boolean,
}
_PROJECTION_SCHEMA: dict[str, pl.DataType] = {
    "unit_id": pl.Utf8,
    "country_id": pl.Utf8,
    "role": pl.Utf8,
    "domain": pl.Utf8,
    "capabilities_json": pl.Utf8,
    "valid_targets_json": pl.Utf8,
    "vulnerabilities_json": pl.Utf8,
    "training_level": pl.Utf8,
    "research_level": pl.Int32,
    "updated_at_minute": pl.Int64,
}


class MilitaryCapabilitySystem(ISystem):
    """Owns training lifecycle and publishes reusable unit capability data."""

    runtime_state_contract = {
        "_projection_state_ref": SYSTEM_STATE_CACHE,
        "_projection_cache": SYSTEM_STATE_CACHE,
        "_role_profile_cache": SYSTEM_STATE_CACHE,
    }

    def __init__(self) -> None:
        self._projection_state_ref: weakref.ReferenceType[GameState] | None = None
        self._projection_cache: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
        self._role_profile_cache: dict[tuple[str, str], Any] = {}

    access = SystemAccess(
        reads=frozenset({"units", "unit_designs", "unit_training_orders", "unit_training_facilities", "unit_capability_projections", "countries", "regions", "battle_units", "research_tracks"}),
        writes=frozenset({"units", "countries", "unit_training_orders", "unit_capability_projections"}),
        handles=frozenset({ActionTrainUnit, ActionCancelUnitTraining, ActionSetUnitTrainingPaused}),
        phase=SystemPhase.MILITARY - 1,
    )

    @property
    def id(self) -> str:
        return "base.military_capabilities"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.military_programs", "base.diplomacy"]

    def update(self, state: GameState, delta_time: float) -> None:
        if "units" not in state.tables:
            return
        units = self._ensure_unit_columns(state.get_table("units"))
        unit_rows = units.to_dicts()
        by_unit = {str(row.get("id") or ""): row for row in unit_rows}
        countries = state.get_table("countries").to_dicts() if "countries" in state.tables else []
        country_by_id = {self._tag(row.get("id")): row for row in countries}
        orders_table = self._ensure_table(state.tables.get("unit_training_orders"), _TRAINING_ORDER_SCHEMA)
        orders = orders_table.to_dicts()
        facilities_table = self._ensure_table(state.tables.get("unit_training_facilities"), _TRAINING_FACILITY_SCHEMA)
        facilities = facilities_table.to_dicts()

        for action in state.current_actions:
            if isinstance(action, ActionTrainUnit):
                owner = self._tag(action.country_tag)
                unit = by_unit.get(str(action.unit_id or ""))
                if unit is None or self._tag(unit.get("owner")) != owner or not self._authorized(state, action.player_id, owner):
                    self._reject(state, action, "The issuer cannot train this country's unit.")
                    continue
                reason = self._start_training(state, by_unit, country_by_id, orders, facilities, action)
                if reason:
                    self._reject(state, action, reason)
            elif isinstance(action, ActionCancelUnitTraining):
                unit = by_unit.get(str(action.unit_id or ""))
                owner = self._tag(unit.get("owner")) if unit is not None else ""
                if unit is None or not self._authorized(state, action.player_id, owner):
                    self._reject(state, action, "The issuer cannot cancel training for this unit.")
                elif not self._cancel_training(state, by_unit, orders, action.unit_id):
                    self._reject(state, action, "The unit has no active training order to cancel.")
            elif isinstance(action, ActionSetUnitTrainingPaused):
                unit = by_unit.get(str(action.unit_id or ""))
                owner = self._tag(unit.get("owner")) if unit is not None else ""
                if unit is None or not self._authorized(state, action.player_id, owner):
                    self._reject(state, action, "The issuer cannot change this unit's training state.")
                elif not self._set_training_paused(orders, action.unit_id, action.is_paused, int(state.time.total_minutes)):
                    self._reject(state, action, "The unit has no active training order to change.")

        elapsed_days = sum(
            max(0.0, float(event.game_seconds_passed)) / _SECONDS_PER_DAY
            for event in state.events
            if isinstance(event, EventRealSecond) and not event.is_paused
        )
        if elapsed_days > 0.0:
            self._advance_training(state, by_unit, orders, facilities, elapsed_days)

        self._write_frame_if_changed(
            state,
            "units",
            pl.DataFrame(unit_rows, schema=units.schema) if unit_rows else units,
        )
        self._write_if_changed(state, "unit_training_orders", _TRAINING_ORDER_SCHEMA, orders)
        if "countries" in state.tables:
            country_frame = pl.DataFrame(countries, schema=state.get_table("countries").schema) if countries else state.get_table("countries")
            self._write_frame_if_changed(state, "countries", country_frame)
        projections = self._build_projections(state, unit_rows, orders)
        self._write_if_changed(state, "unit_capability_projections", _PROJECTION_SCHEMA, projections)

    def _start_training(
        self,
        state: GameState,
        units: dict[str, dict[str, Any]],
        countries: dict[str, dict[str, Any]],
        orders: list[dict[str, Any]],
        facilities: list[dict[str, Any]],
        action: ActionTrainUnit,
    ) -> str:
        unit_id = str(action.unit_id or "")
        unit = units.get(unit_id)
        owner = self._tag(action.country_tag)
        country = countries.get(owner)
        target = str(action.target_level or "").strip().title()
        current = str(unit.get("training_level") or "Recruit").strip().title() if unit else ""
        if unit is None or country is None or self._tag(unit.get("owner")) != owner:
            return "The unit or owning country is unavailable."
        level_steps = training_level_steps(current, target)
        if target not in TRAINING_LEVELS or level_steps <= 0:
            return "Training must advance to a supported higher level."
        if bool(unit.get("is_moving")) or self._integer(unit.get("current_region_id")) <= 0 or str(unit.get("engagement_mode") or ""):
            return "The unit must be deployed and outside movement or engagement to train."
        if str(unit.get("training_state") or "") == "training" or any(
            row.get("unit_id") == unit_id and row.get("status") == "active" for row in orders
        ):
            return "The unit already has an active training order."
        battle_units = state.tables.get("battle_units")
        if battle_units is not None and not battle_units.is_empty() and "unit_id" in battle_units.columns:
            if battle_units.filter(pl.col("unit_id") == unit_id).height > 0:
                return "A participating battle force cannot begin training."

        facility, facility_error = self._select_training_facility(state, unit, owner, facilities, orders)
        if facility_error:
            return facility_error

        days_per_level = self._bounded_config(state, "unit_training_days_per_level", 30.0, 1.0, 3650.0)
        cost_per_strength = self._bounded_config(state, "unit_training_cost_per_strength_level", 1.0, 0.0, 1_000_000.0)
        cost = training_cost(unit.get("strength"), level_steps, cost_per_strength)
        if self._number(country.get("money_reserves")) < cost:
            return "The country cannot fund the requested training."
        country["money_reserves"] = self._number(country.get("money_reserves")) - cost

        regions = state.tables.get("regions")
        region = None
        if regions is not None:
            region_id = self._integer(unit.get("current_region_id"))
            region = next((row for row in regions.to_dicts() if self._integer(row.get("id")) == region_id), None)
        unit["training_state"] = "training"
        unit["unit_lifecycle"] = "training"
        unit["training_progress"] = 0.0
        unit["training_facility_id"] = str(facility.get("id") or "")
        unit["training_location_region_id"] = self._integer(facility.get("region_id"))
        unit["current_region_id"] = 0
        unit["latitude"] = 0.0
        unit["longitude"] = 0.0
        order_id = f"training-{unit_id}-{state.time.total_minutes}-{target.lower()}"
        orders.append({
            "id": order_id,
            "unit_id": unit_id,
            "country_id": owner,
            "facility_id": str(facility.get("id") or ""),
            "training_location_region_id": self._integer(facility.get("region_id")),
            "from_level": current,
            "target_level": target,
            "progress": 0.0,
            "required_days": days_per_level * level_steps,
            "cost": cost,
            "status": "active",
            "return_region_id": self._integer(region.get("id")) if region else 0,
            "return_latitude": self._number(region.get("latitude")) if region else 0.0,
            "return_longitude": self._number(region.get("longitude")) if region else 0.0,
            "started_at_minute": int(state.time.total_minutes),
            "updated_at_minute": int(state.time.total_minutes),
            "completed_at_minute": 0,
            "cancelled_at_minute": 0,
            "last_event": "started",
            "last_event_at_minute": int(state.time.total_minutes),
            "blocking_reason": "",
        })
        return ""

    def _select_training_facility(
        self,
        state: GameState,
        unit: dict[str, Any],
        owner: str,
        facilities: list[dict[str, Any]],
        orders: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, str]:
        region_id = self._integer(unit.get("current_region_id"))
        local_sites = [
            site for site in facilities
            if self._tag(site.get("country_id")) == owner
            and self._integer(site.get("region_id")) == region_id
        ]
        if not local_sites:
            return None, "No training facility is configured at the unit's location."

        design_id = str(unit.get("design_id") or "")
        designs = state.tables.get("unit_designs")
        design = None
        if designs is not None and not designs.is_empty() and "id" in designs.columns:
            design = next((row for row in designs.to_dicts() if str(row.get("id") or "") == design_id), None)
        domain = str((design or {}).get("domain") or unit.get("unit_domain") or "land").strip().lower()
        return select_training_facility(unit, owner, domain, local_sites, orders)

    def _facility_domains(self, facility: dict[str, Any]) -> set[str]:
        return facility_domains(facility)

    def _cancel_training(
        self,
        state: GameState,
        units: dict[str, dict[str, Any]],
        orders: list[dict[str, Any]],
        unit_id: str,
    ) -> bool:
        unit = units.get(str(unit_id))
        if unit is None:
            return False
        for order in orders:
            if str(order.get("unit_id") or "") != str(unit_id) or str(order.get("status") or "") not in {"active", "paused"}:
                continue
            order["status"] = "cancelled"
            order["blocking_reason"] = "Training was cancelled; completed experience is retained."
            order["updated_at_minute"] = int(state.time.total_minutes)
            order["cancelled_at_minute"] = int(state.time.total_minutes)
            order["last_event"] = "cancelled"
            order["last_event_at_minute"] = int(state.time.total_minutes)
            self._restore_training_location(unit, order)
            return True
        return False

    def _set_training_paused(self, orders: list[dict[str, Any]], unit_id: str, paused: bool, now: int) -> bool:
        for order in orders:
            if str(order.get("unit_id") or "") != str(unit_id):
                continue
            status = str(order.get("status") or "")
            if paused and status == "active":
                order["status"] = "paused"
                order["blocking_reason"] = "Training is paused."
                order["last_event"] = "paused"
                order["last_event_at_minute"] = now
            elif not paused and status == "paused":
                order["status"] = "active"
                order["blocking_reason"] = ""
                order["last_event"] = "resumed"
                order["last_event_at_minute"] = now
                return True
            if (paused and status == "paused") or (not paused and status == "active"):
                return True
            return False
        return False

    def _advance_training(
        self,
        state: GameState,
        units: dict[str, dict[str, Any]],
        orders: list[dict[str, Any]],
        facilities: list[dict[str, Any]],
        elapsed_days: float,
    ) -> None:
        facility_by_id = {str(row.get("id") or ""): row for row in facilities}
        active_counts: dict[str, int] = {}
        active_orders = sorted(
            (order for order in orders if str(order.get("status") or "") == "active"),
            key=lambda order: str(order.get("id") or ""),
        )
        for order in active_orders:
            unit = units.get(str(order.get("unit_id") or ""))
            if unit is None:
                order["status"] = "blocked"
                order["blocking_reason"] = "The trained unit no longer exists."
                order["last_event"] = "blocked"
                order["last_event_at_minute"] = int(state.time.total_minutes)
                continue
            facility_id = str(order.get("facility_id") or "")
            facility = facility_by_id.get(facility_id)
            domains = self._facility_domains(facility or {})
            design_id = str(unit.get("design_id") or "")
            designs = state.tables.get("unit_designs")
            design = None
            if designs is not None and not designs.is_empty() and "id" in designs.columns:
                design = next((row for row in designs.to_dicts() if str(row.get("id") or "") == design_id), None)
            domain = str((design or {}).get("domain") or unit.get("unit_domain") or "land").strip().lower()
            unavailable = (
                facility is None
                or self._tag(facility.get("country_id")) != self._tag(order.get("country_id"))
                or not bool(facility.get("enabled"))
                or self._integer(facility.get("region_id")) != self._integer(order.get("training_location_region_id"))
                or (domain not in domains and "all" not in domains)
                or self._integer(facility.get("instructor_count")) <= 0
            )
            if unavailable:
                self._pause_for_facility(order, state, "The assigned facility or eligible instructor is unavailable.")
                continue
            slot_limit = min(
                max(0, self._integer(facility.get("capacity"))),
                max(0, self._integer(facility.get("instructor_count"))),
            )
            if active_counts.get(facility_id, 0) >= slot_limit:
                self._pause_for_facility(order, state, "The assigned facility has no available training capacity.")
                continue
            active_counts[facility_id] = active_counts.get(facility_id, 0) + 1
            required_days = max(1e-9, self._number(order.get("required_days")))
            progress = min(1.0, max(0.0, self._number(order.get("progress")) + elapsed_days / required_days))
            order["progress"] = progress
            order["updated_at_minute"] = int(state.time.total_minutes)
            unit["training_progress"] = progress
            if progress < 1.0:
                continue
            unit["training_level"] = str(order.get("target_level") or "Recruit")
            self._restore_training_location(unit, order)
            order["status"] = "completed"
            order["blocking_reason"] = ""
            order["completed_at_minute"] = int(state.time.total_minutes)
            order["last_event"] = "completed"
            order["last_event_at_minute"] = int(state.time.total_minutes)

    def _pause_for_facility(self, order: dict[str, Any], state: GameState, reason: str) -> None:
        order["status"] = "paused"
        order["blocking_reason"] = reason
        order["updated_at_minute"] = int(state.time.total_minutes)
        order["last_event"] = "paused"
        order["last_event_at_minute"] = int(state.time.total_minutes)

    def _restore_training_location(self, unit: dict[str, Any], order: dict[str, Any]) -> None:
        unit["current_region_id"] = self._integer(order.get("return_region_id"))
        unit["latitude"] = self._number(order.get("return_latitude"))
        unit["longitude"] = self._number(order.get("return_longitude"))
        unit["source_region_id"] = unit["current_region_id"]
        unit["source_latitude"] = unit["latitude"]
        unit["source_longitude"] = unit["longitude"]
        unit["target_region_id"] = -1
        unit["target_latitude"] = unit["latitude"]
        unit["target_longitude"] = unit["longitude"]
        unit["is_moving"] = False
        unit["training_state"] = ""
        unit["training_progress"] = 0.0
        unit["training_facility_id"] = ""
        unit["training_location_region_id"] = 0
        unit["unit_lifecycle"] = "available"

    def _build_projections(
        self,
        state: GameState,
        units: list[dict[str, Any]],
        orders: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        cache_matches_state = (
            self._projection_state_ref is not None
            and self._projection_state_ref() is state
        )
        if not cache_matches_state:
            self._projection_state_ref = weakref.ref(state)
            self._projection_cache = {}

        designs_table = state.tables.get("unit_designs")
        designs = {} if designs_table is None else {
            str(row.get("id") or ""): row for row in designs_table.to_dicts()
        }
        research_table = state.tables.get("research_tracks")
        research = {} if research_table is None else {
            (self._tag(row.get("country_id")), str(row.get("branch") or "").lower()): self._integer(row.get("research_level"))
            for row in research_table.to_dicts()
        }
        existing_by_id: dict[str, dict[str, Any]] = {}
        if not cache_matches_state:
            existing = state.tables.get("unit_capability_projections")
            if existing is not None:
                existing_by_id = {
                    str(row.get("unit_id") or ""): row for row in existing.to_dicts()
                }
        bonuses = state.globals.get("military_training_bonuses")
        overrides = bonuses if isinstance(bonuses, dict) else None
        research_bonuses = state.globals.get("military_research_capability_bonuses")
        configuration_signature = (
            self._freeze_cache_value(overrides),
            self._freeze_cache_value(research_bonuses),
        )
        now = int(state.time.total_minutes)
        result: list[dict[str, Any]] = []
        next_cache: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
        for unit in units:
            unit_id = str(unit.get("id") or "")
            design_id = str(unit.get("design_id") or "")
            design = designs.get(design_id, {})
            role_value = design.get("class_name") or unit.get("unit_type") or "generic_unit"
            domain_hint = design.get("domain") or unit.get("unit_domain")
            profile = self._role_profile(role_value, domain_hint)
            country_id = self._tag(unit.get("owner"))
            branch = str(design.get("branch") or profile.domain).lower()
            research_level = research.get(
                (country_id, branch),
                research.get((country_id, profile.domain), 0),
            )
            signature = (
                unit_id,
                design_id,
                country_id,
                str(role_value),
                str(domain_hint),
                design.get("class_name"),
                design.get("domain"),
                design.get("branch"),
                design.get("capabilities_json"),
                design.get("valid_targets_json"),
                design.get("vulnerabilities_json"),
                unit.get("training_level"),
                research_level,
                configuration_signature,
            )
            cached = self._projection_cache.get(unit_id) if cache_matches_state else None
            if cached is not None and cached[0] == signature:
                row = dict(cached[1])
                result.append(row)
                next_cache[unit_id] = (signature, row)
                continue

            base_capabilities = self._decode_mapping(design.get("capabilities_json"))
            capabilities = project_capabilities(profile, base_capabilities)
            valid_targets = self._decode_list(design.get("valid_targets_json")) or list(profile.valid_targets)
            vulnerabilities = self._decode_list(design.get("vulnerabilities_json")) or list(profile.vulnerabilities)
            branch_bonuses = research_bonuses.get(branch, research_bonuses.get(profile.domain, {})) if isinstance(research_bonuses, dict) else {}
            capabilities = researched_capabilities(capabilities, research_level, branch_bonuses)
            capabilities = trained_capabilities(capabilities, unit.get("training_level"), overrides)
            row = {
                "unit_id": unit_id,
                "country_id": country_id,
                "role": profile.role,
                "domain": str(design.get("domain") or profile.domain),
                "capabilities_json": self._json(capabilities),
                "valid_targets_json": self._json(valid_targets),
                "vulnerabilities_json": self._json(vulnerabilities),
                "training_level": str(unit.get("training_level") or "Recruit"),
                "research_level": research_level,
                "updated_at_minute": now,
            }
            previous = cached[1] if cached is not None else existing_by_id.get(unit_id)
            if previous is not None and {key: previous.get(key) for key in row if key != "updated_at_minute"} == {key: row[key] for key in row if key != "updated_at_minute"}:
                row["updated_at_minute"] = int(previous.get("updated_at_minute") or now)
            result.append(row)
            next_cache[unit_id] = (signature, row)
        self._projection_cache = next_cache
        return result

    def _role_profile(self, role: Any, domain_hint: Any) -> Any:
        key = (str(role), str(domain_hint))
        profile = self._role_profile_cache.get(key)
        if profile is None:
            profile = get_role_profile(role, domain_hint)
            self._role_profile_cache[key] = profile
        return profile

    def _freeze_cache_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return tuple(
                (str(key), self._freeze_cache_value(item))
                for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
            )
        if isinstance(value, (list, tuple)):
            return tuple(self._freeze_cache_value(item) for item in value)
        if isinstance(value, (set, frozenset)):
            return tuple(sorted((self._freeze_cache_value(item) for item in value), key=repr))
        return value

    def _ensure_unit_columns(self, units: pl.DataFrame) -> pl.DataFrame:
        defaults: dict[str, tuple[pl.DataType, Any]] = {
            "design_id": (pl.Utf8, ""),
            "unit_domain": (pl.Utf8, "land"),
            "training_level": (pl.Utf8, "Recruit"),
            "training_state": (pl.Utf8, ""),
            "training_progress": (pl.Float64, 0.0),
            "training_facility_id": (pl.Utf8, ""),
            "training_location_region_id": (pl.Int32, 0),
            "unit_lifecycle": (pl.Utf8, "available"),
        }
        for column, (dtype, default) in defaults.items():
            if column not in units.columns:
                units = units.with_columns(pl.lit(default).cast(dtype).alias(column))
        return units

    def _ensure_table(self, table: pl.DataFrame | None, schema: dict[str, pl.DataType]) -> pl.DataFrame:
        if table is None:
            return pl.DataFrame(schema=schema)
        for column, dtype in schema.items():
            if column not in table.columns:
                default = [] if dtype == pl.List(pl.Utf8) else (0 if dtype in {pl.Int32, pl.Int64, pl.Float64} else "")
                table = table.with_columns(pl.lit(default).cast(dtype).alias(column))
        return table.select([pl.col(column).cast(dtype) for column, dtype in schema.items()])

    def _write_if_changed(self, state: GameState, name: str, schema: dict[str, pl.DataType], rows: list[dict[str, Any]]) -> None:
        frame = pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)
        self._write_frame_if_changed(state, name, frame)

    def _write_frame_if_changed(self, state: GameState, name: str, frame: pl.DataFrame) -> None:
        current = state.tables.get(name)
        if current is None or not current.equals(frame):
            state.update_table(name, frame)

    def _decode_mapping(self, value: Any) -> dict[str, Any]:
        try:
            parsed = json.loads(str(value or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _decode_list(self, value: Any) -> list[str]:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        return [str(item) for item in parsed if item] if isinstance(parsed, list) else []

    def _authorized(self, state: GameState, player_id: Any, country: str) -> bool:
        return player_controls_country(state, player_id, country)

    def _reject(self, state: GameState, action: Any, reason: str) -> None:
        state.journal.append_command_result({
            "tick": int(state.globals.get("tick", 0)),
            "player_id": str(action.player_id),
            "action_type": type(action).__name__,
            "status": "rejected",
            "reason": reason,
        })

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()

    def _json(self, value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    def _bounded_config(self, state: GameState, key: str, default: float, minimum: float, maximum: float) -> float:
        value = self._number(state.globals.get(key, default))
        return min(maximum, max(minimum, value))

    def _integer(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return 0

    def _number(self, value: Any) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return result if result == result and abs(result) != float("inf") else 0.0
