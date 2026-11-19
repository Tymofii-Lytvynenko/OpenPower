"""Military-value diplomatic pressure, separate from domestic political dissent."""
from __future__ import annotations

import polars as pl

from src.shared.treaties import normalize_country_tags


def military_values(state) -> dict[str, float]:
    """Value fielded equipment against its current authoritative design cost."""
    designs = state.tables.get("unit_designs")
    units = state.tables.get("units")
    if designs is None or units is None or not {"id", "cost"}.issubset(designs.columns) or not {"owner", "design_id"}.issubset(units.columns):
        return {}
    quantity = "equipment_quantity" if "equipment_quantity" in units.columns else "strength"
    if quantity not in units.columns:
        return {}
    # Aggregate in tables rather than copying every unit into Python on each UI frame.
    costs = designs.select(
        pl.col("id").cast(pl.Utf8).alias("design_id"),
        pl.col("cost").cast(pl.Float64, strict=False).fill_null(0.0).clip(lower_bound=0.0).alias("_cost"),
    ).unique(subset=["design_id"], keep="last")
    valued = units.select(
        pl.col("owner").cast(pl.Utf8).str.strip_chars().str.to_uppercase(),
        pl.col("design_id").cast(pl.Utf8),
        pl.col(quantity).cast(pl.Float64, strict=False).fill_null(0.0).clip(lower_bound=0.0).alias("_quantity"),
    ).join(costs, on="design_id", how="left").with_columns(
        (pl.col("_cost").fill_null(0.0) * pl.col("_quantity")).alias("_value"),
    ).filter(pl.col("_value").is_finite()).group_by("owner").agg(pl.col("_value").sum())
    return {row["owner"]: row["_value"] for row in valued.to_dicts()}


def treaty_pressure_summary(state, row: dict) -> dict:
    supporters = normalize_country_tags(row.get("pressure_members"))
    if not supporters:
        return {"share": None, "countries": ()}
    values = military_values(state)
    world = sum(values.values())
    if world <= 0.0:
        return {"share": None, "countries": ()}
    shares = tuple((tag, values.get(tag, 0.0) / world) for tag in supporters)
    # Reference: GTreatyDetailsWindow::FillPressure, relative to all fielded unit value.
    return {"share": min(1.0, sum(share for _, share in shares)), "countries": shares}


def pressure_sponsors_by_target(treaties, pending) -> dict[str, set[str]]:
    pressure_on = {}
    for table, is_pending in ((treaties, False), (pending, True)):
        if table is None:
            continue
        for row in table.to_dicts():
            expected_status = "pending" if is_pending else "active"
            if str(row.get("status") or expected_status) != expected_status:
                continue
            targets = (set(normalize_country_tags(row.get("required_responses")))
                       - set(normalize_country_tags(row.get("accepted_members")))) if is_pending else set(normalize_country_tags(row.get("suspended_members")))
            supporters = set(normalize_country_tags(row.get("pressure_members")))
            for target in targets:
                pressure_on.setdefault(target, set()).update(supporters - {target})
    return pressure_on


def pressure_relation_loss_counts(treaties, pending) -> dict[tuple[str, str], int]:
    """Count each pressured-sponsor/target pair once per treaty, as the reference does."""
    loss_counts: dict[tuple[str, str], int] = {}
    for table, is_pending in ((treaties, False), (pending, True)):
        if table is None:
            continue
        for row in table.to_dicts():
            expected_status = "pending" if is_pending else "active"
            if str(row.get("status") or expected_status) != expected_status:
                continue
            targets = (
                set(normalize_country_tags(row.get("required_responses")))
                - set(normalize_country_tags(row.get("accepted_members")))
                if is_pending
                else set(normalize_country_tags(row.get("suspended_members")))
            )
            supporters = set(normalize_country_tags(row.get("pressure_members")))
            for target in targets:
                for sponsor in supporters - {target}:
                    pair = (sponsor, target)
                    loss_counts[pair] = loss_counts.get(pair, 0) + 1
    return loss_counts


def national_pressure_ratios(state, treaties, pending) -> dict[str, float]:
    pressure_on = pressure_sponsors_by_target(treaties, pending)
    if not any(pressure_on.values()):
        return {}
    values = military_values(state)
    # Reference: GWorldBehavior::IterateLossRelationsFromPressure; deduplicate sponsors across treaties.
    return {target: min(1.0, sum(values.get(tag, 0.0) for tag in sponsors) / (values.get(target, 0.0) + 1.0))
            for target, sponsors in pressure_on.items()}
