"""Shared treaty vocabulary, schemas, and read-only policy helpers.

The client, simulation, persistence layer, and mods all need to agree on treaty
semantics.  This module keeps that contract data-only so none of those layers
needs to import a gameplay system merely to inspect an agreement.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Iterable, Mapping

import polars as pl


@dataclass(frozen=True, slots=True)
class TreatyDefinition:
    """Rules that are intrinsic to a treaty type rather than a saved treaty."""

    key: str
    label: str
    two_sided: bool
    multi_member: bool
    long_term: bool
    effects: tuple[str, ...]
    description: str


def _definition(
    key: str,
    label: str,
    *,
    two_sided: bool,
    multi_member: bool,
    long_term: bool,
    effects: tuple[str, ...],
    description: str,
) -> TreatyDefinition:
    return TreatyDefinition(
        key=key,
        label=label,
        two_sided=two_sided,
        multi_member=multi_member,
        long_term=long_term,
        effects=effects,
        description=description,
    )


TREATY_DEFINITIONS: dict[str, TreatyDefinition] = {
    "request_war_declaration": _definition(
        "request_war_declaration",
        "Request war declaration",
        two_sided=True,
        multi_member=False,
        long_term=False,
        effects=("declare_war",),
        description="Creates a formal declaration of hostilities between the two sides.",
    ),
    "alliance": _definition(
        "alliance",
        "Alliance",
        two_sided=False,
        multi_member=True,
        long_term=True,
        effects=("mutual_defense", "stationing_rights"),
        description="Members defend one another and may station units on fellow members' territory.",
    ),
    "military_trespassing_right": _definition(
        "military_trespassing_right",
        "Military trespassing right",
        two_sided=True,
        multi_member=False,
        long_term=True,
        effects=("transit_rights",),
        description="Both sides may cross the other side's territory without gaining stationing rights.",
    ),
    "request_military_presence_removal": _definition(
        "request_military_presence_removal",
        "Request military presence removal",
        two_sided=True,
        multi_member=False,
        long_term=False,
        effects=("remove_foreign_units",),
        description="Removes the requested side's remaining units from the requester's territory.",
    ),
    "annexation": _definition(
        "annexation",
        "Annexation",
        two_sided=True,
        multi_member=False,
        long_term=False,
        effects=("schedule_annexation",),
        description="Transfers continuously occupied regions after a six-month verification period.",
    ),
    "free_region": _definition(
        "free_region",
        "Free region",
        two_sided=True,
        multi_member=False,
        long_term=False,
        effects=("release_occupied_regions",),
        description="Returns military control of the target side's regions to their political owner.",
    ),
    "cultural_exchanges": _definition(
        "cultural_exchanges",
        "Cultural exchanges",
        two_sided=False,
        multi_member=True,
        long_term=True,
        effects=("member_relation_bonus",),
        description="Gradually improves diplomatic relations among members.",
    ),
    "noble_cause": _definition(
        "noble_cause",
        "Noble cause",
        two_sided=False,
        multi_member=True,
        long_term=True,
        effects=("member_relation_bonus", "non_member_relation_pressure"),
        description="Builds solidarity among members while exerting economic-strength-weighted pressure on non-members.",
    ),
    "research_partnership": _definition(
        "research_partnership",
        "Research partnership",
        two_sided=False,
        multi_member=True,
        long_term=True,
        effects=("research_capacity_bonus",),
        description="Each member receives a bonus equal to ten percent of the group's combined research capacity.",
    ),
    "human_development_collaboration": _definition(
        "human_development_collaboration",
        "Human development collaboration",
        two_sided=False,
        multi_member=True,
        long_term=True,
        effects=("human_development_convergence",),
        description="Members with stronger human development help other members close the gap.",
    ),
    "economic_partnership": _definition(
        "economic_partnership",
        "Economic partnership",
        two_sided=False,
        multi_member=True,
        long_term=True,
        effects=("resource_production_bonus",),
        description="Resource production receives a contribution-weighted partnership bonus.",
    ),
    "common_market": _definition(
        "common_market",
        "Common market",
        two_sided=False,
        multi_member=True,
        long_term=True,
        effects=("common_market_priority",),
        description="Members satisfy domestic resource needs from the group before the regular market clears.",
    ),
    "economic_aid": _definition(
        "economic_aid",
        "Economic aid",
        two_sided=True,
        multi_member=True,
        long_term=True,
        effects=("economic_aid",),
        description="Side A funds a capped share of Side B's resource-import needs.",
    ),
    "assume_foreign_debt": _definition(
        "assume_foreign_debt",
        "Assume foreign debt",
        two_sided=True,
        multi_member=True,
        long_term=False,
        effects=("assume_foreign_debt",),
        description="Side A pays Side B's outstanding foreign debt in proportion to economic strength.",
    ),
    "economic_embargo": _definition(
        "economic_embargo",
        "Economic embargo",
        two_sided=True,
        multi_member=True,
        long_term=True,
        effects=("resource_trade_embargo",),
        description="Suspends resource trading between the two sides.",
    ),
    "weapons_trade": _definition(
        "weapons_trade",
        "Weapons trade",
        two_sided=False,
        multi_member=True,
        long_term=True,
        effects=("weapons_market_access",),
        description="Members may order military units from one another.",
    ),
    "weapons_trade_embargo": _definition(
        "weapons_trade_embargo",
        "Weapons trade embargo",
        two_sided=True,
        multi_member=True,
        long_term=True,
        effects=("weapons_trade_embargo", "weapons_embargo_relation_pressure"),
        description="Suspends weapons trade between the two sides and penalizes outside suppliers of the embargoed side.",
    ),
}


TREATY_TYPE_ALIASES: dict[str, str] = {
    "military_alliance": "alliance",
    "defensive_alliance": "alliance",
    "defensive_pact": "alliance",
    "military_pact": "alliance",
    "trade_accord": "economic_partnership",
    "research_accord": "research_partnership",
    "military_transit": "military_trespassing_right",
    "transit_rights": "military_trespassing_right",
    "military_presence_removal": "request_military_presence_removal",
    "debt_assumption": "assume_foreign_debt",
    "weapon_trade": "weapons_trade",
    "weapon_trade_embargo": "weapons_trade_embargo",
}


TREATY_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "name": pl.Utf8,
    "type": pl.Utf8,
    "members": pl.List(pl.Utf8),
    "side_a": pl.List(pl.Utf8),
    "side_b": pl.List(pl.Utf8),
    "status": pl.Utf8,
    "terms": pl.Utf8,
    "conditions_json": pl.Utf8,
    "open_to_new_members": pl.Boolean,
    "suspended_members": pl.List(pl.Utf8),
    "created_at": pl.Utf8,
    "activated_at_minute": pl.Int64,
    "expires_at_minute": pl.Int64,
    "maintenance_cost": pl.Float64,
    "source_country_id": pl.Utf8,
    "target_country_id": pl.Utf8,
}


PENDING_TREATY_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "source_country_id": pl.Utf8,
    "target_country_id": pl.Utf8,
    "treaty_type": pl.Utf8,
    "title": pl.Utf8,
    "terms": pl.Utf8,
    "side_a": pl.List(pl.Utf8),
    "side_b": pl.List(pl.Utf8),
    "members": pl.List(pl.Utf8),
    "required_responses": pl.List(pl.Utf8),
    "accepted_members": pl.List(pl.Utf8),
    "conditions_json": pl.Utf8,
    "open_to_new_members": pl.Boolean,
    "status": pl.Utf8,
    "created_at": pl.Utf8,
}


TREATY_EFFECT_SCHEMA: dict[str, pl.DataType] = {
    "treaty_id": pl.Utf8,
    "country_id": pl.Utf8,
    "effect": pl.Utf8,
    "value": pl.Float64,
    "detail": pl.Utf8,
}


ANNEXATION_CLAIM_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "treaty_id": pl.Utf8,
    "region_id": pl.Int32,
    "annexing_country_id": pl.Utf8,
    "political_owner_id": pl.Utf8,
    "controller_at_start": pl.Utf8,
    "due_at_minute": pl.Int64,
    "status": pl.Utf8,
}


DEFAULT_TREATY_CONDITIONS: dict[str, Any] = {
    "minimum_relation": -100.0,
    "max_military_strength_ratio": 0.0,
    "max_economic_strength_ratio": 0.0,
    "government_type": "",
    "max_research_ratio": 0.0,
    "maximum_geographic_distance_km": 0.0,
    "allow_members_at_war": False,
}


def normalize_treaty_type(value: Any) -> str:
    """Return the canonical treaty key while retaining unknown mod treaty keys."""

    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return TREATY_TYPE_ALIASES.get(text, text)


def treaty_definition(value: Any) -> TreatyDefinition | None:
    return TREATY_DEFINITIONS.get(normalize_treaty_type(value))


def normalize_country_tags(values: Any) -> tuple[str, ...]:
    """Normalize persisted list, tuple, comma-delimited, or scalar country data."""

    if values is None:
        return ()
    if isinstance(values, str):
        raw_values: Iterable[Any] = values.split(",")
    elif isinstance(values, Iterable):
        raw_values = values
    else:
        raw_values = (values,)
    return tuple(sorted({str(value).strip().upper() for value in raw_values if str(value).strip()}))


def treaty_members(row: Mapping[str, Any]) -> tuple[str, ...]:
    members = normalize_country_tags(row.get("members"))
    if members:
        return members
    return tuple(sorted(set(normalize_country_tags(row.get("side_a"))) | set(normalize_country_tags(row.get("side_b")))))


def treaty_side(row: Mapping[str, Any], side: str) -> tuple[str, ...]:
    return normalize_country_tags(row.get("side_a" if side.lower() == "a" else "side_b"))


def active_treaty_rows(treaties: pl.DataFrame | None) -> list[dict[str, Any]]:
    if treaties is None or treaties.is_empty():
        return []
    return [
        row
        for row in treaties.to_dicts()
        if str(row.get("status") or "active").strip().lower() == "active"
    ]


def share_active_treaty(
    treaties: pl.DataFrame | None,
    left: str,
    right: str,
    treaty_types: Iterable[str],
) -> bool:
    desired = {normalize_treaty_type(value) for value in treaty_types}
    left_tag = str(left or "").strip().upper()
    right_tag = str(right or "").strip().upper()
    if not left_tag or not right_tag:
        return False
    for row in active_treaty_rows(treaties):
        if normalize_treaty_type(row.get("type")) not in desired:
            continue
        members = set(treaty_members(row)) - set(normalize_country_tags(row.get("suspended_members")))
        if left_tag in members and right_tag in members:
            return True
    return False


def active_treaty_members(
    treaties: pl.DataFrame | None,
    treaty_type: str,
) -> tuple[tuple[str, ...], ...]:
    """Expose active membership groups for systems that apply a treaty effect."""

    normalized_type = normalize_treaty_type(treaty_type)
    groups: list[tuple[str, ...]] = []
    for row in active_treaty_rows(treaties):
        if normalize_treaty_type(row.get("type")) != normalized_type:
            continue
        suspended = set(normalize_country_tags(row.get("suspended_members")))
        members = tuple(tag for tag in treaty_members(row) if tag not in suspended)
        if members:
            groups.append(members)
    return tuple(groups)


def encode_conditions(conditions: Mapping[str, Any] | None) -> str:
    normalized = dict(DEFAULT_TREATY_CONDITIONS)
    if conditions:
        normalized.update({str(key): value for key, value in conditions.items() if key in normalized})
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def decode_conditions(value: Any) -> dict[str, Any]:
    normalized = dict(DEFAULT_TREATY_CONDITIONS)
    if isinstance(value, Mapping):
        payload = value
    else:
        try:
            payload = json.loads(str(value or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
    if isinstance(payload, Mapping):
        normalized.update({str(key): item for key, item in payload.items() if key in normalized})
    return normalized


def treaty_type_labels() -> tuple[tuple[str, str], ...]:
    """Return a stable canonical list suitable for UI choices and mod tooling."""

    return tuple((definition.key, definition.label) for definition in TREATY_DEFINITIONS.values())
