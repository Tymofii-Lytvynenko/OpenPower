import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from modules.base.systems.military.covert_mission_profiles import MISSION_PROFILES
from modules.base.systems.military.covert_policy import skill_profile
from src.shared.covert_mission_options import (
    UNIT_CATEGORY_OPTIONS,
    allowed_complexities,
    country_resource_ids,
    default_complexity,
    mission_sector,
)


TagNormalizer = Callable[[Any], str]
FiniteNumber = Callable[[Any], float]
AuthorizationCheck = Callable[[Any, Any, str], bool]


@dataclass(frozen=True, slots=True)
class MissionStartPlan:
    cell_id: Any
    owner_id: str
    target_id: str
    cover_id: str
    mission_type: str
    target_sector: str
    complexity: str
    target_resource_id: str
    target_unit_category: str
    assignment: str
    risk: float
    execution_cost: float
    preparation_minutes: int
    requires_execution_confirmation: bool


@dataclass(frozen=True, slots=True)
class MissionStartResult:
    plan: MissionStartPlan | None = None
    rejection_reason: str = ""


@dataclass(frozen=True, slots=True)
class _MissionParameters:
    framed_id: str
    target_sector: str
    complexity: str
    target_resource_id: str
    target_unit_category: str


@dataclass(frozen=True, slots=True)
class _MissionRequestContext:
    state: Any
    action: Any
    countries: Sequence[dict[str, Any]]
    mission_type: str
    target_id: str
    framed_id: str
    normalize_tag: TagNormalizer


def plan_mission_start(
    state,
    cells: Sequence[dict[str, Any]],
    countries: Sequence[dict[str, Any]],
    missions: Sequence[dict[str, Any]],
    action,
    *,
    normalize_tag: TagNormalizer,
    finite_number: FiniteNumber,
    is_authorized: AuthorizationCheck,
) -> MissionStartResult:
    if type(action.requires_execution_confirmation) is not bool:
        return _rejected("Choose a boolean mission execution mode.")

    cell = next(
        (row for row in cells if str(row.get("id")) == str(action.cell_id)), None
    )
    mission_type = str(action.mission_type or "").strip().lower()
    target_id = normalize_tag(action.target_country_tag)
    framed_id = normalize_tag(action.cover_country_tag)
    if cell is None or mission_type not in MISSION_PROFILES:
        return _rejected("The cell or mission type is invalid.")

    owner_id = normalize_tag(cell.get("country_id"))
    reason = _cell_start_rejection(
        state,
        cell,
        missions,
        action,
        owner_id,
        target_id,
        normalize_tag,
        is_authorized,
    )
    if reason:
        return _rejected(reason)

    parameters, reason = _mission_parameters(
        _MissionRequestContext(
            state, action, countries, mission_type, target_id, framed_id, normalize_tag
        )
    )
    if parameters is None:
        return _rejected(reason)

    assignment = _mission_assignment(mission_type)
    cell_assignment = str(cell.get("assignment") or "unassigned").strip().lower()
    if cell_assignment not in {"unassigned", assignment}:
        return _rejected("The cell's active assignment does not support this mission.")

    risk = MISSION_PROFILES[mission_type][0]
    profile = skill_profile(cell.get("skill_level"))
    if risk > profile.max_mission_risk:
        return _rejected("This mission exceeds the cell's current skill capability.")

    execution_cost, reason = _mission_execution_cost(
        state, countries, owner_id, finite_number, normalize_tag
    )
    if reason:
        return _rejected(reason)

    configured_prep = max(
        1.0,
        finite_number(
            state.globals.get(f"covert_{mission_type}_preparation_minutes", 1440)
        ),
    )
    preparation_minutes = max(
        1, int(math.ceil(configured_prep * profile.preparation_multiplier))
    )
    return MissionStartResult(
        plan=MissionStartPlan(
            cell_id=cell.get("id"),
            owner_id=owner_id,
            target_id=target_id,
            cover_id=parameters.framed_id,
            mission_type=mission_type,
            target_sector=parameters.target_sector,
            complexity=parameters.complexity,
            target_resource_id=parameters.target_resource_id,
            target_unit_category=parameters.target_unit_category,
            assignment=assignment,
            risk=risk,
            execution_cost=execution_cost,
            preparation_minutes=preparation_minutes,
            requires_execution_confirmation=action.requires_execution_confirmation,
        )
    )


def _cell_start_rejection(
    state,
    cell: Mapping[str, Any],
    missions: Sequence[dict[str, Any]],
    action,
    owner_id: str,
    target_id: str,
    normalize_tag: TagNormalizer,
    is_authorized: AuthorizationCheck,
) -> str:
    if not is_authorized(state, action.player_id, owner_id) or cell.get("status") not in {"active", "idle"}:
        return "The issuer cannot command this cell or the cell is unavailable."
    if not bool(cell.get("communications_ready", True)) or normalize_tag(cell.get("location_country_id")) != target_id:
        return "The cell has not reached the target or lacks communications."
    if normalize_tag(cell.get("target_country_id")) != target_id or _has_active_mission(cell, missions):
        return "The target does not match the assignment or this cell already has an active mission."
    return ""


def _has_active_mission(
    cell: Mapping[str, Any], missions: Sequence[dict[str, Any]]
) -> bool:
    active_statuses = {"preparation", "ready", "executing", "cleanup"}
    return any(
        row.get("cell_id") == cell.get("id")
        and row.get("status") in active_statuses
        for row in missions
    )


def _mission_parameters(
    context: _MissionRequestContext,
) -> tuple[_MissionParameters | None, str]:
    target_sector, reason = _validated_target_sector(
        context.action, context.mission_type
    )
    if reason:
        return None, reason

    complexity, reason = _validated_complexity(
        context.action, context.mission_type, target_sector
    )
    if reason:
        return None, reason

    target_resource_id, target_unit_category, reason = _validated_specific_targets(
        context.state, context.action, context.target_id, target_sector
    )
    if reason:
        return None, reason

    reason = _cover_country_rejection(
        context.countries, context.framed_id, context.target_id, context.normalize_tag
    )
    if reason:
        return None, reason

    return (
        _MissionParameters(
            context.framed_id,
            target_sector,
            complexity,
            target_resource_id,
            target_unit_category,
        ),
        "",
    )


def _validated_target_sector(action, mission_type: str) -> tuple[str, str]:
    requested_sector = str(action.target_sector or "").strip().lower()
    profile_sector = mission_sector(mission_type)
    if requested_sector and requested_sector not in {"civilian", "military"}:
        return "", "Choose a valid covert mission target sector."
    if profile_sector and requested_sector and requested_sector != profile_sector:
        return "", "The target sector does not match the selected mission profile."

    target_sector = profile_sector or requested_sector
    sectorless_missions = {"assassination", "terrorism", "coup_attempt", "framing"}
    if mission_type in sectorless_missions and target_sector:
        return "", "This mission type does not use a target sector."
    return target_sector, ""


def _validated_complexity(
    action, mission_type: str, target_sector: str
) -> tuple[str, str]:
    complexity = str(action.complexity or default_complexity(mission_type)).strip().lower()
    if complexity not in allowed_complexities(mission_type, target_sector):
        return "", "Choose a complexity available for this mission."
    return complexity, ""


def _validated_specific_targets(
    state, action, target_id: str, target_sector: str
) -> tuple[str, str, str]:
    target_resource_id = str(action.target_resource_id or "").strip().lower()
    if target_resource_id and (
        target_sector != "civilian"
        or target_resource_id not in country_resource_ids(state, target_id)
    ):
        return "", "", "Choose a resource available to the target country."

    target_unit_category = str(action.target_unit_category or "").strip().lower()
    valid_unit_categories = {value for value, _label in UNIT_CATEGORY_OPTIONS}
    if target_unit_category and (
        target_sector != "military" or target_unit_category not in valid_unit_categories
    ):
        return "", "", "Choose a unit category available for a military mission."
    return target_resource_id, target_unit_category, ""


def _cover_country_rejection(
    countries: Sequence[dict[str, Any]],
    framed_id: str,
    target_id: str,
    normalize_tag: TagNormalizer,
) -> str:
    country_ids = {normalize_tag(row.get("id")) for row in countries}
    if framed_id and (framed_id not in country_ids or framed_id == target_id):
        return "Choose an existing country other than the mission target to frame."
    return ""


def _mission_assignment(mission_type: str) -> str:
    if mission_type.endswith("espionage"):
        return "espionage"
    if mission_type.endswith("sabotage"):
        return "sabotage"
    return "political"


def _mission_execution_cost(
    state,
    countries: Sequence[dict[str, Any]],
    owner_id: str,
    finite_number: FiniteNumber,
    normalize_tag: TagNormalizer,
) -> tuple[float, str]:
    cost = max(0.0, finite_number(state.globals.get("covert_mission_cost", 2.0)))
    owner = next(
        (row for row in countries if normalize_tag(row.get("id")) == owner_id), None
    )
    if owner is None or finite_number(owner.get("money_reserves")) < cost:
        return 0.0, "The owner cannot fund mission preparation."
    return cost, ""


def _rejected(reason: str) -> MissionStartResult:
    return MissionStartResult(rejection_reason=reason)
