"""OpenPower effects for a confirmed foreign government-form transition."""

from __future__ import annotations

import json
from typing import Any

import polars as pl

from src.shared.determinism import DeterministicRuntime
from src.shared.events import EventTreatyLifecycleChanged
from src.shared.state import GameState
from src.shared.treaties import (
    TREATY_EFFECT_SCHEMA,
    TREATY_SCHEMA,
    encode_conditions,
    normalize_treaty_type,
    share_active_treaty,
)


def build_foreign_government_effects(
    state: GameState,
    controller_country: str,
    political_country: str,
    now: int,
) -> tuple[dict[str, pl.DataFrame], tuple[EventTreatyLifecycleChanged, ...]]:
    """Stage region release, transit rights, and bilateral relations together."""

    controller = _tag(controller_country)
    owner = _tag(political_country)
    table_updates: dict[str, pl.DataFrame] = {}
    events: list[EventTreatyLifecycleChanged] = []

    regions = state.tables["regions"]
    region_rows = regions.to_dicts()
    released_regions: set[int] = set()
    owner_region_ids = {
        _integer(region.get("id"))
        for region in region_rows
        if _tag(region.get("owner")) == owner
    }
    occupations = state.tables.get("occupations")
    occupied_region_ids: set[int] = set()
    if occupations is not None and {
        "region_id", "controller_country_id"
    }.issubset(occupations.columns):
        occupied_region_ids = {
            _integer(occupation.get("region_id"))
            for occupation in occupations.iter_rows(named=True)
            if _tag(occupation.get("controller_country_id")) == controller
            and _tag(occupation.get("occupation_status"))
            not in {"ended", "cancelled", "inactive"}
        }
    for region in region_rows:
        if _tag(region.get("owner")) != owner:
            continue
        region_id = _integer(region.get("id"))
        if _tag(region.get("controller")) == controller or (
            not _tag(region.get("controller")) and region_id in occupied_region_ids
        ):
            if "controller" in region:
                region["controller"] = owner
            released_regions.add(region_id)

    if occupations is not None and {
        "region_id", "controller_country_id", "occupation_status"
    }.issubset(occupations.columns):
        occupation_rows = occupations.to_dicts()
        occupations_changed = False
        for occupation in occupation_rows:
            region_id = _integer(occupation.get("region_id"))
            if (
                region_id in owner_region_ids
                and _tag(occupation.get("controller_country_id")) == controller
                and _tag(occupation.get("occupation_status"))
                not in {"ended", "cancelled", "inactive"}
            ):
                occupation["occupation_status"] = "ended"
                occupations_changed = True
        if occupations_changed:
            table_updates["occupations"] = _frame_like(occupations, occupation_rows)

    if released_regions:
        table_updates["regions"] = _frame_like(regions, region_rows)

    relations = state.tables["countries_relations"]
    relation_rows = relations.to_dicts()
    for source, target in ((owner, controller), (controller, owner)):
        relation = next(
            row for row in relation_rows
            if _tag(row.get("source")) == source and _tag(row.get("target")) == target
        )
        relation["value"] = 100.0
    table_updates["countries_relations"] = _frame_like(relations, relation_rows)

    treaties = state.tables["countries_treaties"]
    treaty_effects = state.tables["treaty_effects"]
    treaty_rows = treaties.to_dicts()
    effect_rows = treaty_effects.to_dicts()
    access_type = "military_trespassing_right"
    if not share_active_treaty(treaties, owner, controller, (access_type,)):
        treaty_id = DeterministicRuntime(state.determinism).next_id(
            "treaty", int(state.globals.get("tick", 0))
        )
        members = sorted((owner, controller))
        treaty_rows.append(
            {
                "id": treaty_id,
                "name": f"Military access between {owner} and {controller}",
                "type": access_type,
                "members": members,
                "side_a": [owner],
                "side_b": [controller],
                "status": "active",
                "terms": "Transit rights granted after a constitutional form change.",
                "conditions_json": encode_conditions({"allow_members_at_war": False}),
                "open_to_new_members": False,
                "suspended_members": [],
                "created_at": str(getattr(state.time, "date_str", "") or ""),
                "activated_at_minute": now,
                "expires_at_minute": 0,
                "maintenance_cost": 0.0,
                "source_country_id": owner,
                "target_country_id": controller,
            }
        )
        events.append(
            EventTreatyLifecycleChanged(
                treaty_id=treaty_id,
                treaty_type=access_type,
                transition="activated",
                country_ids=tuple(members),
                at_minute=now,
                reason="Transit rights were granted after the constitutional form change.",
            )
        )
        table_updates["countries_treaties"] = pl.DataFrame(
            treaty_rows, schema=TREATY_SCHEMA, strict=False
        )

    access_treaty = next(
        (
            row for row in treaty_rows
            if str(row.get("status") or "active").casefold() == "active"
            and normalize_treaty_type(row.get("type")) == access_type
            and {owner, controller}.issubset(_tags(row.get("members")))
        ),
        None,
    )
    if access_treaty is not None:
        treaty_id = str(access_treaty.get("id") or "")
        for country, peer in ((owner, controller), (controller, owner)):
            if not any(
                str(effect.get("treaty_id") or "") == treaty_id
                and _tag(effect.get("country_id")) == country
                and str(effect.get("effect") or "") == "transit_rights"
                for effect in effect_rows
            ):
                effect_rows.append(
                    {
                        "treaty_id": treaty_id,
                        "country_id": country,
                        "effect": "transit_rights",
                        "value": 1.0,
                        "detail": json.dumps([peer], separators=(",", ":")),
                    }
                )
        table_updates["treaty_effects"] = pl.DataFrame(
            effect_rows, schema=TREATY_EFFECT_SCHEMA, strict=False
        )

    return table_updates, tuple(events)


def _frame_like(frame: pl.DataFrame, rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=frame.schema, strict=False)


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()


def _tags(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {_tag(item) for item in value if _tag(item)}
    return {_tag(value)} if _tag(value) else set()


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
