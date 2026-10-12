from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

import polars as pl

from modules.base.systems.world.ai.common import active_war_pairs, country_frame
from src.core.ai_framework import AITableContext, empty_candidates
from src.shared.actions import ActionLaunchStrategicStrike, GameAction


_CANDIDATE_SCHEMA = {
    "target_country_id": pl.Utf8,
    "target_region_id": pl.Int32,
    "origin_region_id": pl.Int32,
    "weapon_id": pl.Utf8,
    "weapon_type": pl.Utf8,
    "payload_level": pl.Int32,
}


class StrategicWarfarePolicy:
    """Authorize a single, conservative retaliatory launch through the normal action path."""

    id = "strategic_warfare"
    required_tables = frozenset({
        "countries",
        "regions",
        "countries_wars",
        "research_tracks",
        "strategic_weapons",
        "strategic_launch_orders",
    })
    cadence_days = 1

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        doctrine = str(context.globals.get("strategic_ai_doctrine", "retaliatory")).strip().lower()
        if doctrine != "retaliatory":
            return empty_candidates(_CANDIDATE_SCHEMA)

        scheduled_frame = country_frame(context, self.cadence_days).select("country_id").collect()
        if scheduled_frame.is_empty():
            return empty_candidates(_CANDIDATE_SCHEMA)
        countries_table = context.table("countries")
        regions_table = context.table("regions")
        tracks_table = context.table("research_tracks")
        weapons_table = context.table("strategic_weapons")
        orders_table = context.table("strategic_launch_orders")
        if any(table is None for table in (countries_table, regions_table, tracks_table, weapons_table, orders_table)):
            return empty_candidates(_CANDIDATE_SCHEMA)

        scheduled_ids = scheduled_frame.get_column("country_id").drop_nulls().unique().to_list()
        active_wars = active_war_pairs(context).collect()
        if active_wars.is_empty():
            return empty_candidates(_CANDIDATE_SCHEMA)
        status_column = pl.col("status").cast(pl.Utf8).fill_null("").str.to_lowercase()
        incoming_orders = orders_table.filter(
            (status_column == "impact")
            & pl.col("target_country_id").cast(pl.Utf8).str.to_uppercase().is_in(scheduled_ids)
        ).select(
            pl.col("country_id").cast(pl.Utf8).str.to_uppercase().alias("_opponent"),
            pl.col("target_country_id").cast(pl.Utf8).str.to_uppercase().alias("_owner"),
        )
        active_pairs = active_wars.lazy().select(
            pl.col("source_country").alias("_owner"),
            pl.col("target_country").alias("_opponent"),
        )
        if incoming_orders.join(
            active_pairs,
            on=["_owner", "_opponent"],
            how="inner",
        ).collect().is_empty():
            return empty_candidates(_CANDIDATE_SCHEMA)

        countries = countries_table.collect().to_dicts()
        regions = regions_table.collect().to_dicts()
        tracks = tracks_table.collect().to_dicts()
        weapons = weapons_table.collect().to_dicts()
        orders = orders_table.collect().to_dicts()
        country_by_id = {self._tag(row.get("id")): row for row in countries}
        regions_by_country: dict[str, list[dict[str, Any]]] = {}
        regions_by_id: dict[int, dict[str, Any]] = {}
        for region in regions:
            owner = self._tag(region.get("owner"))
            region_id = self._integer(region.get("id"))
            if owner:
                regions_by_country.setdefault(owner, []).append(region)
            if region_id:
                regions_by_id[region_id] = region

        levels_by_country: dict[str, dict[str, int]] = {}
        for row in tracks:
            owner = self._tag(row.get("country_id"))
            branch = str(row.get("branch") or "").strip().lower()
            if owner and branch:
                levels_by_country.setdefault(owner, {})[branch] = max(
                    levels_by_country.setdefault(owner, {}).get(branch, 0),
                    max(0, self._integer(row.get("research_level"))),
                )

        opponents: dict[str, set[str]] = {}
        for row in active_wars.to_dicts():
            owner = self._tag(row.get("source_country"))
            opponent = self._tag(row.get("target_country"))
            if owner and opponent:
                opponents.setdefault(owner, set()).add(opponent)

        pending_weapon_ids = {
            str(row.get("weapon_id") or "")
            for row in orders
            if str(row.get("status") or "").strip().lower() == "pending"
        }
        outgoing_by_pair: dict[tuple[str, str], list[int]] = {}
        for row in orders:
            owner = self._tag(row.get("country_id"))
            target = self._tag(row.get("target_country_id"))
            if owner and target:
                outgoing_by_pair.setdefault((owner, target), []).append(
                    self._integer(row.get("launched_at_minute"))
                )

        governments_table = context.table("country_governments")
        capitals = {}
        if governments_table is not None:
            capitals = {
                self._tag(row.get("country_id")): self._integer(row.get("capital_region_id"))
                for row in governments_table.collect().to_dicts()
            }

        candidates: list[dict[str, Any]] = []
        research_gate = bool(context.globals.get("strategic_research_gate_enabled", True))
        required_program_level = max(1, self._integer(context.globals.get("strategic_program_research_level", 1)))
        required_weapon_level = max(1, self._integer(context.globals.get("strategic_weapon_research_level", 1)))
        for scheduled_country in scheduled_frame.sort("country_id").to_dicts():
            owner = self._tag(scheduled_country.get("country_id"))
            if not owner or owner not in country_by_id:
                continue
            owner_levels = levels_by_country.get(owner, {})
            if research_gate and owner_levels.get("strategic_program", 0) < required_program_level:
                continue

            incoming = sorted(
                (
                    row for row in orders
                    if self._tag(row.get("target_country_id")) == owner
                    and str(row.get("status") or "").strip().lower() == "impact"
                    and self._tag(row.get("country_id")) in opponents.get(owner, set())
                ),
                key=lambda row: (-self._integer(row.get("updated_at_minute")), str(row.get("id") or "")),
            )
            for incident in incoming:
                target_country = self._tag(incident.get("country_id"))
                incident_minute = self._integer(incident.get("updated_at_minute"))
                if not target_country or any(
                    minute >= incident_minute
                    for minute in outgoing_by_pair.get((owner, target_country), ())
                ):
                    continue
                country = country_by_id[owner]
                origin = self._origin_region(owner, regions_by_country, regions_by_id, capitals)
                if origin is None:
                    continue
                target = self._target_region(
                    owner,
                    target_country,
                    origin,
                    regions_by_country,
                    regions_by_id,
                    weapons,
                    owner_levels,
                    pending_weapon_ids,
                    research_gate,
                    required_weapon_level,
                    country,
                )
                if target is None:
                    continue
                weapon, target_region = target
                candidates.append({
                    "country_id": owner,
                    "policy_id": self.id,
                    "domain": "strategic_warfare",
                    "utility": 0.95,
                    "conflict_key": f"strategic-retaliation:{owner}",
                    "action_kind": "launch_strategic_strike",
                    "reason_code": "retaliation_after_confirmed_impact",
                    "quota": 1,
                    "target_country_id": target_country,
                    "target_region_id": self._integer(target_region.get("id")),
                    "origin_region_id": self._integer(weapon.get("origin_region_id")) or self._integer(origin.get("id")),
                    "weapon_id": str(weapon.get("id") or ""),
                    "weapon_type": str(weapon.get("weapon_type") or weapon.get("weapon_class") or "icbm"),
                    "payload_level": 1,
                })
                break

        return pl.DataFrame(candidates, schema_overrides=_CANDIDATE_SCHEMA).lazy() if candidates else empty_candidates(_CANDIDATE_SCHEMA)

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        if str(row.get("action_kind") or "") != "launch_strategic_strike":
            return None
        owner = self._tag(row.get("country_id"))
        target = self._tag(row.get("target_country_id"))
        weapon_id = str(row.get("weapon_id") or "")
        region_id = self._integer(row.get("target_region_id"))
        if not owner or not target or not weapon_id or not region_id:
            return None
        return ActionLaunchStrategicStrike(
            "ai_system",
            owner,
            region_id,
            str(row.get("weapon_type") or "icbm"),
            target_country_tag=target,
            target_mode="military",
            weapon_id=weapon_id,
            payload_level=max(1, self._integer(row.get("payload_level"), 1)),
            origin_region_id=max(0, self._integer(row.get("origin_region_id"))),
        )

    def _target_region(
        self,
        owner: str,
        target_country: str,
        origin: dict[str, Any],
        regions_by_country: dict[str, list[dict[str, Any]]],
        regions_by_id: dict[int, dict[str, Any]],
        weapons: list[dict[str, Any]],
        levels: dict[str, int],
        pending_weapon_ids: set[str],
        research_gate: bool,
        required_level: int,
        country: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        target_regions = regions_by_country.get(target_country, ())
        if not target_regions:
            return None
        eligible = []
        for weapon in weapons:
            weapon_id = str(weapon.get("id") or "")
            if (
                self._tag(weapon.get("country_id")) != owner
                or not weapon_id
                or weapon_id in pending_weapon_ids
                or not bool(weapon.get("operational", True))
                or self._integer(weapon.get("ready")) < 1
                or self._integer(weapon.get("quantity")) < 1
            ):
                continue
            weapon_level = levels.get("strategic_weapons", 0)
            asset_required_level = max(1, required_level, self._integer(weapon.get("required_research_level"), 1))
            if research_gate and weapon_level < asset_required_level:
                continue
            max_payload = min(10, max(1, self._integer(weapon.get("max_payload_level"), 1)))
            if research_gate and min(max_payload, weapon_level) < 1:
                continue
            if self._number(country.get("money_reserves")) < max(0.0, self._number(weapon.get("launch_cost"))):
                continue
            weapon_range = max(0.0, self._number(weapon.get("range_km")))
            weapon_origin_id = self._integer(weapon.get("origin_region_id"))
            weapon_origin = regions_by_id.get(weapon_origin_id)
            if weapon_origin is not None and self._tag(weapon_origin.get("owner")) != owner:
                continue
            if weapon_origin is None:
                weapon_origin = origin
            for target_region in target_regions:
                if self._distance_km(weapon_origin, target_region) <= weapon_range:
                    eligible.append((weapon, target_region))

        if not eligible:
            return None
        weapon, target_region = min(
            eligible,
            key=lambda pair: (
                max(0.0, self._number(pair[0].get("launch_cost"))),
                self._integer(pair[1].get("id")),
                str(pair[0].get("id") or ""),
            ),
        )
        return weapon, target_region

    def _origin_region(
        self,
        owner: str,
        regions_by_country: dict[str, list[dict[str, Any]]],
        regions_by_id: dict[int, dict[str, Any]],
        capitals: dict[str, int],
    ) -> dict[str, Any] | None:
        owned = regions_by_country.get(owner, ())
        if not owned:
            return None
        capital = regions_by_id.get(capitals.get(owner, 0))
        if capital is not None and self._tag(capital.get("owner")) == owner:
            return capital
        return min(owned, key=lambda row: self._integer(row.get("id")))

    def _distance_km(self, left: dict[str, Any], right: dict[str, Any]) -> float:
        lat1 = math.radians(self._number(left.get("latitude")))
        lon1 = math.radians(self._number(left.get("longitude")))
        lat2 = math.radians(self._number(right.get("latitude")))
        lon2 = math.radians(self._number(right.get("longitude")))
        delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
        value = math.sin(delta_lat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
        return 6371.0 * 2.0 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1.0 - value)))

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()

    def _integer(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return default

    def _number(self, value: Any, default: float = 0.0) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        return parsed if math.isfinite(parsed) else default
