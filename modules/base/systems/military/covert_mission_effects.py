"""Apply successful covert-mission effects to authoritative world state."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from modules.base.systems.military.covert_resource_effects import (
    apply_resource_production_delta,
    resource_production_total,
)
from src.shared.covert_mission_options import mission_effect_modifier


_SUCCESSFUL_OUTCOMES = frozenset({"success", "partial_success"})
_POLITICAL_IMPACTS = {
    "assassination": 0.025,
    "terrorism": 0.05,
    "coup_attempt": 0.08,
    "framing": 0.035,
}
_ATTRIBUTION_PENALTIES = {
    "assassination": 8.0,
    "terrorism": 12.0,
    "coup_attempt": 10.0,
    "framing": 6.0,
}


@dataclass(frozen=True, slots=True)
class MissionEffectServices:
    normalize_tag: Callable[[Any], str]
    finite_number: Callable[[Any], float]
    sabotage_unit_candidates: Callable[[Any, pl.DataFrame, str, str], pl.DataFrame]
    write_frame_if_changed: Callable[[Any, str, pl.DataFrame], None]
    adjust_relations: Callable[[list[dict[str, Any]], str, str, float], None]


def apply_mission_effect(
    state: Any,
    mission: Mapping[str, Any],
    target: MutableMapping[str, Any],
    output: MutableMapping[str, Any],
    governments: Sequence[MutableMapping[str, Any]],
    relations: list[dict[str, Any]],
    attributed_country_id: str,
    *,
    partial: bool = False,
    outcome: str = "success",
    services: MissionEffectServices,
) -> None:
    mission_type = str(mission.get("mission_type"))
    scale = mission_effect_modifier(
        str(mission.get("complexity") or "medium"), partial=partial
    )
    target_id = services.normalize_tag(target.get("id"))

    if outcome in _SUCCESSFUL_OUTCOMES:
        if mission_type in {"civilian_sabotage", "military_sabotage"}:
            _apply_sabotage_effect(
                state, mission_type, mission, target, target_id, scale, output, services
            )
        elif mission_type in _POLITICAL_IMPACTS:
            _apply_political_effect(
                mission_type,
                target,
                target_id,
                governments,
                attributed_country_id,
                scale,
                services,
            )

        if mission_type == "civilian_espionage":
            _apply_civilian_espionage_effect(
                state, mission, target_id, scale, output, services
            )

    if attributed_country_id:
        penalty = _ATTRIBUTION_PENALTIES.get(mission_type, 3.0)
        services.adjust_relations(
            relations,
            services.normalize_tag(attributed_country_id),
            target_id,
            -penalty,
        )


def _apply_sabotage_effect(
    state: Any,
    mission_type: str,
    mission: Mapping[str, Any],
    target: MutableMapping[str, Any],
    target_id: str,
    scale: float,
    output: MutableMapping[str, Any],
    services: MissionEffectServices,
) -> None:
    if mission_type == "civilian_sabotage":
        _apply_civilian_sabotage(state, mission, target, target_id, scale, output, services)
    if mission_type == "military_sabotage" and "units" in state.tables:
        _apply_military_sabotage(state, mission, target_id, scale, services)


def _apply_civilian_sabotage(
    state: Any,
    mission: Mapping[str, Any],
    target: MutableMapping[str, Any],
    target_id: str,
    scale: float,
    output: MutableMapping[str, Any],
    services: MissionEffectServices,
) -> None:
    resource_id = str(mission.get("target_resource_id") or "").strip().lower()
    production = resource_production_total(state, target_id, resource_id)
    actual_delta = (
        apply_resource_production_delta(
            state, target_id, resource_id, -production * 0.01 * scale
        )
        if production > 0.0
        else 0.0
    )
    if actual_delta < 0.0:
        output["resource_production_effect"] = {
            "country_id": target_id,
            "resource_id": resource_id,
            "delta": actual_delta,
        }
    elif not resource_id and "economic_health" in target:
        # Only legacy missions without a saved resource can use the old aggregate effect.
        target["economic_health"] = max(
            0.0,
            min(
                1.0,
                services.finite_number(target.get("economic_health")) - 0.02 * scale,
            ),
        )


def _apply_military_sabotage(
    state: Any,
    mission: Mapping[str, Any],
    target_id: str,
    scale: float,
    services: MissionEffectServices,
) -> None:
    units = state.get_table("units")
    if not {"id", "owner", "strength"}.issubset(units.columns):
        return
    target_units = services.sabotage_unit_candidates(
        state,
        units,
        target_id,
        str(mission.get("target_unit_category") or "").strip().lower(),
    )
    if target_units.is_empty():
        return
    unit_id = target_units.item(0, "id")
    strength = int(target_units.item(0, "strength") or 0)
    loss = max(1, int(round(strength * 0.05 * scale)))
    updated = units.with_columns(
        pl.when(pl.col("id") == unit_id)
        .then(pl.lit(max(0, strength - loss)).cast(units.schema["strength"]))
        .otherwise(pl.col("strength"))
        .alias("strength")
    )
    services.write_frame_if_changed(state, "units", updated)


def _apply_political_effect(
    mission_type: str,
    target: MutableMapping[str, Any],
    target_id: str,
    governments: Sequence[MutableMapping[str, Any]],
    attributed_country_id: str,
    scale: float,
    services: MissionEffectServices,
) -> None:
    government = next(
        (
            row
            for row in governments
            if services.normalize_tag(row.get("country_id")) == target_id
        ),
        None,
    )
    if government is not None:
        impact = _POLITICAL_IMPACTS[mission_type] * scale
        government["election_risk"] = min(
            1.0,
            max(
                0.0,
                services.finite_number(government.get("election_risk")) + impact,
            ),
        )
        if mission_type == "coup_attempt":
            balance = services.finite_number(government.get("ideology_balance"))
            direction = 0.025 if attributed_country_id else -0.015
            government["ideology_balance"] = min(
                1.0, max(0.0, balance + direction * scale)
            )
    if mission_type == "terrorism" and "security_upkeep" in target:
        target["security_upkeep"] = max(
            0.0,
            services.finite_number(target.get("security_upkeep"))
            + services.finite_number(target.get("gdp")) * 0.0001 * scale,
        )


def _apply_civilian_espionage_effect(
    state: Any,
    mission: Mapping[str, Any],
    target_id: str,
    scale: float,
    output: MutableMapping[str, Any],
    services: MissionEffectServices,
) -> None:
    resource_id = str(mission.get("target_resource_id") or "").strip().lower()
    target_production = resource_production_total(state, target_id, resource_id)
    owner_id = services.normalize_tag(mission.get("owner_country_id"))
    owner_production = resource_production_total(state, owner_id, resource_id)
    if target_production <= 0.0 or owner_production <= 0.0:
        return
    actual_delta = apply_resource_production_delta(
        state, owner_id, resource_id, target_production * 0.02 * scale
    )
    if actual_delta > 0.0:
        output["resource_production_effect"] = {
            "country_id": owner_id,
            "resource_id": resource_id,
            "delta": actual_delta,
        }
