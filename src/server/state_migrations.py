"""Server-owned migrations for tactical combat state compatibility."""

from __future__ import annotations

from typing import Any

import polars as pl

from src.shared.state import GameState


_READINESS_STATUSES = {"parked", "ready", "fortified"}
_BATTLE_STATUSES = {"active", "stalemate", "concluded", "inactive"}
_TRANSITION_STAGES = {"direct", "parked_to_ready", "parked_to_fortified", "ready_to_fortified"}


def migrate_tactical_combat_state(state: GameState) -> None:
    """Add feature columns to legacy saves before schema validation runs."""

    units = state.tables.get("units")
    if units is None:
        return

    additions: list[pl.Expr] = []
    if "readiness_status" not in units.columns:
        additions.append(pl.lit("ready").alias("readiness_status"))
    if "readiness_transition_id" not in units.columns:
        additions.append(pl.lit("").alias("readiness_transition_id"))
    if "readiness_progress" not in units.columns:
        additions.append(pl.lit(0.0).alias("readiness_progress"))
    if "readiness_eta_minute" not in units.columns:
        additions.append(pl.lit(0).cast(pl.Int64).alias("readiness_eta_minute"))
    if additions:
        units = units.with_columns(additions)

    units = units.with_columns(
        pl.col("readiness_status")
        .cast(pl.Utf8)
        .str.to_lowercase()
        .map_elements(_normalize_status, return_dtype=pl.Utf8)
        .alias("readiness_status"),
        pl.col("readiness_transition_id").cast(pl.Utf8).fill_null("").alias("readiness_transition_id"),
        pl.col("readiness_progress").cast(pl.Float64).fill_null(0.0).clip(0.0, 1.0).alias("readiness_progress"),
        pl.col("readiness_eta_minute").cast(pl.Int64).fill_null(0).alias("readiness_eta_minute"),
    )
    state.update_table("units", units)


def validate_tactical_combat_state(state: GameState) -> tuple[str, ...]:
    """Return deterministic validation issues for feature-owned state tables."""

    issues: list[str] = []
    units = state.tables.get("units")
    if units is not None:
        if "id" not in units.columns:
            issues.append("units.missing_id")
        if "readiness_status" in units.columns:
            invalid = units.filter(~pl.col("readiness_status").is_in(sorted(_READINESS_STATUSES))).height
            if invalid:
                issues.append(f"units.invalid_readiness_status:{invalid}")
        if "readiness_transition_id" in units.columns and "readiness_eta_minute" in units.columns:
            negative_eta = units.filter(pl.col("readiness_eta_minute") < 0).height
            if negative_eta:
                issues.append(f"units.negative_readiness_eta:{negative_eta}")

    unit_rows = units.to_dicts() if units is not None and not units.is_empty() else []
    units_by_id = {str(row.get("id") or ""): row for row in unit_rows}
    transitions = state.tables.get("unit_readiness_transitions")
    transition_rows = transitions.to_dicts() if transitions is not None and not transitions.is_empty() else []
    transitions_by_id = {str(row.get("id") or ""): row for row in transition_rows}
    if transitions is not None and not transitions.is_empty():
        for column in (
            "id",
            "unit_id",
            "from_status",
            "target_status",
            "stage",
            "started_at_minute",
            "completes_at_minute",
            "progress",
            "pending_order_id",
        ):
            if column not in transitions.columns:
                issues.append(f"unit_readiness_transitions.missing_{column}")
        if {"unit_id", "id"}.issubset(transitions.columns):
            duplicate_units = (
                transitions.group_by("unit_id").len().filter(pl.col("len") > 1).height
            )
            if duplicate_units:
                issues.append(f"unit_readiness_transitions.duplicate_unit:{duplicate_units}")

        if {"unit_id", "from_status", "target_status", "stage", "started_at_minute", "completes_at_minute", "progress"}.issubset(transitions.columns):
            for row in transition_rows:
                transition_id = str(row.get("id") or "")
                unit_id = str(row.get("unit_id") or "")
                from_status = str(row.get("from_status") or "").strip().lower()
                target_status = str(row.get("target_status") or "").strip().lower()
                stage = str(row.get("stage") or "").strip().lower()
                started = int(row.get("started_at_minute") or 0)
                completes = int(row.get("completes_at_minute") or 0)
                progress = float(row.get("progress") or 0.0)
                if from_status not in _READINESS_STATUSES:
                    issues.append(f"unit_readiness_transitions.invalid_from_status:{transition_id}")
                if target_status not in _READINESS_STATUSES:
                    issues.append(f"unit_readiness_transitions.invalid_target_status:{transition_id}")
                if stage not in _TRANSITION_STAGES:
                    issues.append(f"unit_readiness_transitions.invalid_stage:{transition_id}")
                if completes < started:
                    issues.append(f"unit_readiness_transitions.invalid_timing:{transition_id}")
                if not 0.0 <= progress <= 1.0:
                    issues.append(f"unit_readiness_transitions.invalid_progress:{transition_id}")
                unit = units_by_id.get(unit_id)
                if unit is None:
                    issues.append(f"unit_readiness_transitions.orphan_unit:{transition_id}")
                else:
                    if str(unit.get("readiness_transition_id") or "") != transition_id:
                        issues.append(f"unit_readiness_transitions.unit_reference_mismatch:{transition_id}")
                    if int(unit.get("readiness_eta_minute") or 0) != completes:
                        issues.append(f"unit_readiness_transitions.eta_mismatch:{transition_id}")

    pending = state.tables.get("unit_pending_orders")
    pending_rows = pending.to_dicts() if pending is not None and not pending.is_empty() else []
    if pending is not None and not pending.is_empty() and {"unit_id", "status"}.issubset(pending.columns):
        duplicate_pending = (
            pending.filter(pl.col("status") == "queued")
            .group_by("unit_id")
            .len()
            .filter(pl.col("len") > 1)
            .height
        )
        if duplicate_pending:
            issues.append(f"unit_pending_orders.duplicate_queued_unit:{duplicate_pending}")

        for row in pending_rows:
            order_id = str(row.get("id") or "")
            unit_id = str(row.get("unit_id") or "")
            status = str(row.get("status") or "").strip().lower()
            if unit_id not in units_by_id:
                issues.append(f"unit_pending_orders.orphan_unit:{order_id}")
            if status == "queued":
                transition_id = str((units_by_id.get(unit_id) or {}).get("readiness_transition_id") or "")
                transition = transitions_by_id.get(transition_id)
                if transition is None or str(transition.get("pending_order_id") or "") != order_id:
                    issues.append(f"unit_pending_orders.unlinked_transition:{order_id}")

    if units is not None and not units.is_empty() and {"id", "readiness_transition_id"}.issubset(units.columns):
        for row in unit_rows:
            transition_id = str(row.get("readiness_transition_id") or "")
            if transition_id and transition_id not in transitions_by_id:
                issues.append(f"units.orphan_readiness_transition:{row.get('id', '')}")

    battles = state.tables.get("battles")
    if battles is not None and not battles.is_empty() and "status" in battles.columns:
        for row in battles.to_dicts():
            status = str(row.get("status") or "").strip().lower()
            battle_id = str(row.get("id") or "")
            if status not in _BATTLE_STATUSES:
                issues.append(f"battles.invalid_status:{battle_id}")
            if int(row.get("updated_at_minute") or 0) < int(row.get("started_at_minute") or 0):
                issues.append(f"battles.invalid_timing:{battle_id}")
            if status == "concluded" and int(row.get("concluded_at_minute") or 0) < int(row.get("started_at_minute") or 0):
                issues.append(f"battles.invalid_conclusion_time:{battle_id}")

    return tuple(issues)


def _normalize_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    return status if status in _READINESS_STATUSES else "ready"
