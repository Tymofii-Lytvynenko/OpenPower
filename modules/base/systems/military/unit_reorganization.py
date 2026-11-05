"""Authoritative conservation and availability rules for splitting and merging."""
from __future__ import annotations

import math

import polars as pl

from modules.base.systems.military.authority_policy import player_controls_country
from src.shared.actions import ActionDisbandUnits, ActionMergeUnits, ActionSplitUnit
from src.shared.determinism import DeterministicRuntime


class UnitReorganization:
    _TRAITS = ("owner", "unit_type", "design_id", "unit_domain", "readiness_status",
               "training_level", "combat_posture")

    @staticmethod
    def _rows(state, name):
        table = state.tables.get(name)
        return table.to_dicts() if table is not None else []

    @classmethod
    def _unavailable_reason(cls, state, unit):
        if int(unit.get("strength") or 0)<=0 or int(unit.get("equipment_quantity") or 0)<0:
            return "The unit has an invalid personnel or equipment count."
        if bool(unit.get("is_moving")) or str(unit.get("unit_lifecycle") or "available") != "available":
            return "The unit must be stationary and available."
        if unit.get("readiness_transition_id") or int(unit.get("reorganization_until_minute") or 0) > state.time.total_minutes:
            return "The unit is changing readiness or reorganizing."
        if str(unit.get("engagement_mode") or ""):
            return "Units in contact cannot be reorganized."
        if str(unit.get("training_state") or "") in {"training", "queued", "in_progress", "blocked"}:
            return "The unit is assigned to training."
        unit_id = str(unit.get("id"))
        for table, finished in (
            ("unit_training_orders", {"completed", "cancelled", "rejected", "failed"}),
            ("unit_pending_orders", {"completed", "cancelled", "rejected", "failed", "executed"}),
            ("unit_movement_routes", {"completed", "cancelled", "rejected", "failed", "arrived"}),
            ("unit_deployment_orders", {"delivered", "cancelled", "failed", "disbanded"}),
            ("unit_market_listings", {"sold", "withdrawn", "cancelled", "expired"}),
        ):
            if any(str(row.get("unit_id")) == unit_id and str(row.get("status") or "") not in finished
                   for row in cls._rows(state, table)):
                return "The unit has an active order or market listing."
        active_battles = {str(row.get("id")) for row in cls._rows(state, "battles")
                          if str(row.get("status") or "active") not in {"concluded", "ended", "inactive", "resolved"}}
        if any(str(row.get("unit_id")) == unit_id and str(row.get("battle_id")) in active_battles
               for row in cls._rows(state, "battle_units")):
            return "Units in combat cannot be reorganized."
        return ""

    @classmethod
    def apply(cls, state, units):
        action_types = (ActionSplitUnit, ActionMergeUnits, ActionDisbandUnits)
        actions = [a for a in state.current_actions if isinstance(a, action_types)]
        if not actions:
            return units
        rows = units.to_dicts()
        for action in actions:
            by_id = {str(row["id"]): row for row in rows}
            if isinstance(action, ActionSplitUnit):
                ids = [str(action.unit_id)]
            elif isinstance(action, ActionMergeUnits):
                sources = action.source_unit_ids if isinstance(action.source_unit_ids,(list,tuple)) else []
                ids = [str(action.target_unit_id), *[str(key) for key in sources]]
            else:
                requested = action.unit_ids if isinstance(action.unit_ids, (list, tuple)) else []
                ids = [str(key) for key in requested]
            selected = [by_id[key] for key in ids if key in by_id]
            reason = ""
            if len(set(ids)) != len(ids) or len(selected) != len(ids) or not selected:
                reason = "Select distinct existing units."
            elif any(not player_controls_country(state, action.player_id, row.get("owner")) for row in selected):
                reason = "The issuer does not control every selected unit."
            else:
                reason = next((message for row in selected if (message := cls._unavailable_reason(state, row))), "")
            if not reason and isinstance(action, ActionSplitUnit):
                reason = cls._split(state, rows, selected[0], action.detached_strength)
            elif not reason and isinstance(action, ActionMergeUnits):
                reason = cls._merge(rows, selected)
            elif not reason:
                reason = cls._disband(state, rows, selected)
            state.journal.append_command_result({
                "tick": int(state.globals.get("tick", 0)), "player_id": str(action.player_id),
                "action_type": type(action).__name__, "status": "rejected" if reason else "applied",
                "reason": reason or (
                    "Selected units were disbanded."
                    if isinstance(action, ActionDisbandUnits)
                    else "Unit reorganization completed."
                ),
            })
        return pl.DataFrame(rows, schema=units.schema) if rows else units.clear()

    @classmethod
    def _disband(cls, state, rows, selected):
        countries = state.tables.get("countries")
        if countries is None or not {"id", "military_count"}.issubset(countries.columns):
            return "Country military totals are unavailable."

        country_rows = countries.to_dicts()
        countries_by_tag = {
            str(row.get("id") or "").strip().upper(): row
            for row in country_rows
        }
        personnel_by_owner: dict[str, int] = {}
        for unit in selected:
            owner = str(unit.get("owner") or "").strip().upper()
            if owner not in countries_by_tag:
                return "The owner country is unavailable."
            personnel_by_owner[owner] = personnel_by_owner.get(owner, 0) + int(unit.get("strength") or 0)

        for owner, personnel in personnel_by_owner.items():
            country = countries_by_tag[owner]
            country["military_count"] = max(0, int(country.get("military_count") or 0) - personnel)

        removed_ids = {str(unit.get("id") or "") for unit in selected}
        rows[:] = [unit for unit in rows if str(unit.get("id") or "") not in removed_ids]
        state.update_table("countries", pl.DataFrame(country_rows, schema=countries.schema))
        return ""

    @staticmethod
    def _split(state, rows, unit, detached):
        strength = int(unit.get("strength") or 0)
        if isinstance(detached, bool) or not isinstance(detached, int) or not 0 < detached < strength:
            return "Both resulting units must retain at least one person."
        equipment = max(0, int(unit.get("equipment_quantity") or 0))
        # Integer arithmetic avoids rounding-created equipment. The remainder
        # stays with the original unit, including odd or very small inventories.
        detached_equipment = equipment * detached // strength
        runtime = DeterministicRuntime(state.determinism)
        unit_id = runtime.next_id("unit-split", int(state.globals.get("tick", 0)))
        existing = {str(row["id"]) for row in rows}
        while unit_id in existing:
            unit_id = runtime.next_id("unit-split", int(state.globals.get("tick", 0)))
        new = dict(unit, id=unit_id, strength=detached, equipment_quantity=detached_equipment)
        cost = float(unit.get("original_cost") or 0.0)
        if "original_cost" in unit:
            new["original_cost"] = cost * detached / strength
            unit["original_cost"] = cost - new["original_cost"]
        unit["strength"] = strength - detached
        unit["equipment_quantity"] = equipment - detached_equipment
        rows.append(new)
        return ""

    @classmethod
    def _merge(cls, rows, selected):
        if len(selected) < 2:
            return "Select at least two units to merge."
        target = selected[0]
        if any(any(row.get(key) != target.get(key) for key in cls._TRAITS) for row in selected[1:]):
            return "Units must share owner, design, type, training, readiness and posture."
        if any(int(row.get("current_region_id") or 0) != int(target.get("current_region_id") or 0)
               or any(not math.isclose(float(row.get(key) or 0), float(target.get(key) or 0), abs_tol=1e-6, rel_tol=0)
                      for key in ("latitude", "longitude")) for row in selected[1:]):
            return "Units must occupy the same location."
        strength = sum(int(row.get("strength") or 0) for row in selected)
        equipment = sum(int(row.get("equipment_quantity") or 0) for row in selected)
        if any(int(row.get("strength") or 0) <= 0 or int(row.get("equipment_quantity") or 0)<0 for row in selected) or max(strength,equipment) > 2**63-1:
            return "The resulting unit would have an invalid size."
        for key in ("cohesion", "combat_strength_modifier", "war_exhaustion_modifier", "combat_casualty_modifier",
                    "combat_defense_modifier", "combat_attack_risk_modifier", "combat_readiness_modifier",
                    "combat_holding_modifier", "combat_counterattack_modifier"):
            if key in target:
                target[key] = sum(float(row.get(key) or 0) * int(row["strength"]) for row in selected) / strength
        if "original_cost" in target:
            target["original_cost"] = sum(float(row.get("original_cost") or 0) for row in selected)
        target["strength"], target["equipment_quantity"] = strength, equipment
        removed = {str(row["id"]) for row in selected[1:]}
        rows[:] = [row for row in rows if str(row["id"]) not in removed]
        return ""
