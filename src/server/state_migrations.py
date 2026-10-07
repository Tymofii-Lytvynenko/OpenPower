"""Server-owned migrations for tactical combat state compatibility."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import polars as pl

from modules.base.schema import BASE_TABLE_SCHEMAS
from src.shared.state import GameState
from src.shared.schema import WorldSchemaRegistry


_READINESS_STATUSES = {"parked", "ready", "fortified"}
_BATTLE_STATUSES = {"active", "stalemate", "concluded", "inactive"}
_TRANSITION_STAGES = {"direct", "parked_to_ready", "parked_to_fortified", "ready_to_fortified"}
_ANCHOR_SOURCES = {"contact", "region_center"}
_POLITICAL_TABLE_NAMES = frozenset(
    {
        "country_governments",
        "government_form_rules",
        "political_parties",
        "country_laws",
        "law_transitions",
        "political_elections",
        "political_crises",
        "political_effects",
        "political_history",
    }
)
_POLITICAL_SCHEMA_REGISTRY = WorldSchemaRegistry(
    replace(schema, preserve_extra_columns=True)
    for schema in BASE_TABLE_SCHEMAS
    if schema.name in _POLITICAL_TABLE_NAMES
)


def migrate_political_state(state: GameState) -> None:
    """Add versioned political table fields to legacy runtime state without reseeding it."""

    for table_name in sorted(_POLITICAL_TABLE_NAMES):
        schema = _POLITICAL_SCHEMA_REGISTRY.get(table_name)
        if schema is None:
            continue
        current = state.tables.get(table_name)
        if current is None:
            current = pl.DataFrame(
                schema={column: field.dtype for column, field in schema.columns.items()}
            )
        normalized = _POLITICAL_SCHEMA_REGISTRY.normalize(table_name, current)
        if table_name not in state.tables or not normalized.equals(current):
            state.update_table(table_name, normalized)


def migrate_tactical_combat_state(state: GameState) -> None:
    """Add feature columns to legacy saves before schema validation runs."""

    units = state.tables.get("units")
    if units is not None:
        additions: list[pl.Expr] = []
        if "readiness_status" not in units.columns:
            additions.append(pl.lit("ready").alias("readiness_status"))
        if "readiness_transition_id" not in units.columns:
            additions.append(pl.lit("").alias("readiness_transition_id"))
        if "readiness_progress" not in units.columns:
            additions.append(pl.lit(0.0).alias("readiness_progress"))
        if "readiness_eta_minute" not in units.columns:
            additions.append(pl.lit(0).cast(pl.Int64).alias("readiness_eta_minute"))
        if "unit_lifecycle" not in units.columns:
            additions.append(pl.lit("available").alias("unit_lifecycle"))
        if "training_state" not in units.columns:
            additions.append(pl.lit("").alias("training_state"))
        if "training_progress" not in units.columns:
            additions.append(pl.lit(0.0).cast(pl.Float64).alias("training_progress"))
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

    _migrate_battle_anchors(state)


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
    if battles is not None and not battles.is_empty():
        for row in battles.to_dicts():
            status = str(row.get("status") or "").strip().lower()
            battle_id = str(row.get("id") or "")
            if "status" in battles.columns:
                if status not in _BATTLE_STATUSES:
                    issues.append(f"battles.invalid_status:{battle_id}")
                if int(row.get("updated_at_minute") or 0) < int(row.get("started_at_minute") or 0):
                    issues.append(f"battles.invalid_timing:{battle_id}")
                if status == "concluded" and int(row.get("concluded_at_minute") or 0) < int(row.get("started_at_minute") or 0):
                    issues.append(f"battles.invalid_conclusion_time:{battle_id}")

            has_anchor_fields = any(
                column in row for column in ("anchor_latitude", "anchor_longitude", "anchor_source")
            )
            if has_anchor_fields:
                latitude = row.get("anchor_latitude")
                longitude = row.get("anchor_longitude")
                source = str(row.get("anchor_source") or "").strip().lower()
                if not _is_valid_coordinate(latitude, longitude):
                    issues.append(f"battles.invalid_anchor_coordinate:{battle_id}")
                if source not in _ANCHOR_SOURCES:
                    issues.append(f"battles.invalid_anchor_source:{battle_id}")

    return tuple(issues)


def _normalize_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    return status if status in _READINESS_STATUSES else "ready"


def _migrate_battle_anchors(state: GameState) -> None:
    """Backfill battle anchors before the world schema is captured."""

    battles = state.tables.get("battles")
    if battles is None:
        return

    regions = state.tables.get("regions")
    regions_by_id: dict[int, dict[str, Any]] = {}
    for region in (regions.to_dicts() if regions is not None and not regions.is_empty() else []):
        try:
            regions_by_id[int(region.get("id") or 0)] = region
        except (TypeError, ValueError):
            continue
    latitude_values: list[float | None] = []
    longitude_values: list[float | None] = []
    source_values: list[str] = []
    for row in battles.to_dicts():
        latitude = row.get("anchor_latitude")
        longitude = row.get("anchor_longitude")
        source = str(row.get("anchor_source") or "").strip().lower()
        if _is_valid_coordinate(latitude, longitude):
            # Preserve an existing coordinate, including the valid 0,0 point.
            latitude_values.append(float(latitude))
            longitude_values.append(_normalize_longitude(float(longitude)))
            if source in _ANCHOR_SOURCES:
                source_values.append(source)
            elif not source:
                # A legacy coordinate with no provenance remains usable; the
                # validator can distinguish it from an explicitly bad value.
                source_values.append("contact")
            else:
                source_values.append(source)
            continue

        try:
            region_id = int(row.get("region_id") or 0)
        except (TypeError, ValueError):
            region_id = 0
        region = regions_by_id.get(region_id)
        if region is not None and _is_valid_coordinate(region.get("latitude"), region.get("longitude")):
            latitude_values.append(float(region["latitude"]))
            longitude_values.append(_normalize_longitude(float(region["longitude"])))
            source_values.append("region_center")
            continue

        # Keep malformed rows visible to validation and isolate them on the
        # client rather than inventing a location or using 0,0 as a sentinel.
        latitude_values.append(None)
        longitude_values.append(None)
        source_values.append("")

    battles = battles.with_columns(
        pl.Series("anchor_latitude", latitude_values, dtype=pl.Float64),
        pl.Series("anchor_longitude", longitude_values, dtype=pl.Float64),
        pl.Series("anchor_source", source_values, dtype=pl.Utf8),
    )
    state.update_table("battles", battles)


def _is_valid_coordinate(latitude: Any, longitude: Any) -> bool:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return False
    return math.isfinite(lat) and math.isfinite(lon) and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _normalize_longitude(longitude: float) -> float:
    normalized = float(longitude)
    while normalized >= 180.0:
        normalized -= 360.0
    while normalized < -180.0:
        normalized += 360.0
    return normalized
