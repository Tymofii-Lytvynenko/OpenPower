"""Server-owned migrations for tactical combat state compatibility."""

from __future__ import annotations

from typing import Any

import polars as pl

from src.shared.state import GameState


_READINESS_STATUSES = {"parked", "ready", "fortified"}


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

    transitions = state.tables.get("unit_readiness_transitions")
    if transitions is not None and not transitions.is_empty():
        for column in ("id", "unit_id", "from_status", "target_status"):
            if column not in transitions.columns:
                issues.append(f"unit_readiness_transitions.missing_{column}")
        if {"unit_id", "id"}.issubset(transitions.columns):
            duplicate_units = (
                transitions.group_by("unit_id").len().filter(pl.col("len") > 1).height
            )
            if duplicate_units:
                issues.append(f"unit_readiness_transitions.duplicate_unit:{duplicate_units}")

    pending = state.tables.get("unit_pending_orders")
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

    return tuple(issues)


def _normalize_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    return status if status in _READINESS_STATUSES else "ready"
