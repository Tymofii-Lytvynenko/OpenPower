from __future__ import annotations

from collections.abc import Mapping
import json
import math
from typing import Any

import polars as pl

from modules.base.systems.world.ai.common import country_frame
from modules.base.systems.military.covert_operations_system import MISSION_PROFILES
from modules.base.systems.military.covert_policy import skill_profile
from src.core.ai_framework import AITableContext, empty_candidates
from src.shared.actions import (
    ActionCreateCovertCell,
    ActionStartCovertMission,
    ActionTrainCovertCell,
    GameAction,
)


_ACTIVE_MISSION_STATES = frozenset({"preparation", "executing", "cleanup"})
_MISSION_TYPE = "civilian_espionage"
_CANDIDATE_SCHEMA = {
    "target_country_id": pl.Utf8,
    "cell_id": pl.Utf8,
    "cell_name": pl.Utf8,
    "training_points": pl.Float64,
    "mission_type": pl.Utf8,
}


class CovertOperationsPolicy:
    """Submit ordinary covert actions through the shared validated action path."""

    id = "covert_operations"
    required_tables = frozenset(
        {"countries", "regions", "covert_cells", "covert_missions"}
    )
    cadence_days = 7

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        scheduled = country_frame(context, self.cadence_days).collect().to_dicts()
        country_table = context.table("countries")
        regions_table = context.table("regions")
        cells_table = context.table("covert_cells")
        missions_table = context.table("covert_missions")
        if any(table is None for table in (country_table, regions_table, cells_table, missions_table)):
            return empty_candidates(_CANDIDATE_SCHEMA)

        countries = country_table.collect().to_dicts()
        regions = regions_table.collect().to_dicts()
        cells = cells_table.collect().to_dicts()
        missions = missions_table.collect().to_dicts()
        relations_table = context.table("countries_relations")
        relations = [] if relations_table is None else relations_table.collect().to_dicts()
        treaties_table = context.table("countries_treaties")
        treaties = [] if treaties_table is None else treaties_table.collect().to_dicts()
        allied_pairs = self._allied_pairs(treaties)
        country_by_id = {self._tag(row.get("id")): row for row in countries}
        owned_regions = {
            self._tag(row.get("owner"))
            for row in regions
            if self._tag(row.get("owner"))
        }
        active_cells_by_owner: dict[str, list[dict[str, Any]]] = {}
        for cell in cells:
            owner = self._tag(cell.get("country_id"))
            if owner and str(cell.get("status") or "").lower() not in {"retired", "lost", "captured"}:
                active_cells_by_owner.setdefault(owner, []).append(cell)
        active_missions = {
            str(row.get("cell_id") or "")
            for row in missions
            if str(row.get("status") or "").lower() in _ACTIVE_MISSION_STATES
        }

        candidates: list[dict[str, Any]] = []
        creation_cost = max(0.0, self._finite(context.globals.get("covert_cell_creation_cost", 10.0)))
        training_points = max(1.0, self._finite(context.globals.get("covert_training_points_per_level", 100.0)))
        training_cost = training_points * max(0.0, self._finite(context.globals.get("covert_training_cost_per_point", 0.1)))
        mission_cost = max(0.0, self._finite(context.globals.get("covert_mission_cost", 2.0)))
        mission_risk = MISSION_PROFILES[_MISSION_TYPE][0]

        for scheduled_country in sorted(scheduled, key=lambda row: self._tag(row.get("country_id"))):
            owner = self._tag(scheduled_country.get("country_id"))
            country = country_by_id.get(owner)
            if not owner or country is None:
                continue
            funds = self._finite(country.get("money_reserves"))
            owned_cells = sorted(
                active_cells_by_owner.get(owner, ()),
                key=lambda row: str(row.get("id") or ""),
            )
            candidate = self._cell_action(
                owner,
                funds,
                owned_cells,
                active_missions,
                training_points,
                training_cost,
                mission_cost,
                mission_risk,
            )
            if candidate is None and not owned_cells and funds >= creation_cost and owner in owned_regions:
                target = self._choose_target(owner, countries, relations, allied_pairs, owned_regions)
                if target:
                    candidate = self._candidate(
                        owner,
                        "create_cell",
                        "establish_covert_capability",
                        0.45,
                        target_country_id=target,
                        cell_name="Government Intelligence Cell",
                    )
            if candidate is not None:
                candidates.append(candidate)

        if not candidates:
            return empty_candidates(_CANDIDATE_SCHEMA)
        return pl.DataFrame(candidates).lazy()

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        owner = str(row.get("country_id") or "")
        kind = str(row.get("action_kind") or "")
        if kind == "create_cell":
            return ActionCreateCovertCell(
                "ai_system",
                owner,
                str(row.get("target_country_id") or ""),
                str(row.get("cell_name") or "Government Intelligence Cell"),
            )
        if kind == "train_cell":
            return ActionTrainCovertCell(
                "ai_system",
                str(row.get("cell_id") or ""),
                max(1.0, self._finite(row.get("training_points"), 100.0)),
            )
        if kind == "start_mission":
            return ActionStartCovertMission(
                "ai_system",
                str(row.get("cell_id") or ""),
                str(row.get("mission_type") or _MISSION_TYPE),
                str(row.get("target_country_id") or ""),
            )
        return None

    def _cell_action(
        self,
        owner: str,
        funds: float,
        cells: list[dict[str, Any]],
        active_missions: set[str],
        training_points: float,
        training_cost: float,
        mission_cost: float,
        mission_risk: float,
    ) -> dict[str, Any] | None:
        for cell in cells:
            cell_id = str(cell.get("id") or "")
            status = str(cell.get("status") or "").lower()
            if not cell_id or status not in {"active", "idle"} or cell_id in active_missions:
                continue
            skill = str(cell.get("skill_level") or "Recruit")
            if skill == "Recruit":
                if funds < training_cost:
                    continue
                return self._candidate(
                    owner, "train_cell", "prepare_cell", 0.7,
                    cell_id=cell_id, training_points=training_points,
                )
            if skill_profile(skill).max_mission_risk < mission_risk or funds < mission_cost:
                continue
            target = self._tag(cell.get("target_country_id"))
            if (
                not target
                or self._tag(cell.get("location_country_id")) != target
                or not bool(cell.get("communications_ready", True))
                or str(cell.get("assignment") or "unassigned") not in {"unassigned", "espionage"}
            ):
                continue
            return self._candidate(
                owner, "start_mission", "collect_bounded_intelligence", 0.65,
                cell_id=cell_id, target_country_id=target, mission_type=_MISSION_TYPE,
            )
        return None

    def _choose_target(
        self,
        owner: str,
        countries: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        allied_pairs: set[tuple[str, str]],
        owned_regions: set[str],
    ) -> str:
        relation_by_pair: dict[tuple[str, str], list[float]] = {}
        for row in relations:
            left, right = self._tag(row.get("source")), self._tag(row.get("target"))
            if left and right:
                relation_by_pair.setdefault((left, right), []).append(self._finite(row.get("value")))
        eligible = []
        for country in countries:
            target = self._tag(country.get("id"))
            if not target or target == owner or target not in owned_regions or (owner, target) in allied_pairs:
                continue
            values = relation_by_pair.get((owner, target), []) + relation_by_pair.get((target, owner), [])
            relation = sum(values) / len(values) if values else 0.0
            eligible.append((relation, target))
        return min(eligible)[1] if eligible else ""

    @staticmethod
    def _allied_pairs(treaties: list[dict[str, Any]]) -> set[tuple[str, str]]:
        pairs: set[tuple[str, str]] = set()
        for row in treaties:
            if (
                str(row.get("status") or "active").lower() != "active"
                or str(row.get("treaty_type") or "").lower() != "alliance"
            ):
                continue
            members = row.get("members") or []
            if isinstance(members, str):
                try:
                    members = json.loads(members)
                except (TypeError, ValueError):
                    members = []
            if not isinstance(members, (list, tuple, set)):
                continue
            normalized = sorted({str(item).strip().upper() for item in members if str(item).strip()})
            for index, left in enumerate(normalized):
                for right in normalized[index + 1 :]:
                    pairs.add((left, right))
                    pairs.add((right, left))
        return pairs

    @staticmethod
    def _candidate(
        country: str,
        kind: str,
        reason: str,
        utility: float,
        **payload: Any,
    ) -> dict[str, Any]:
        row = {
            "country_id": country,
            "policy_id": CovertOperationsPolicy.id,
            "domain": "covert",
            "utility": utility,
            "conflict_key": f"covert:{country}",
            "action_kind": kind,
            "reason_code": reason,
            "quota": 1,
        }
        row.update(
            {
                name: "" if dtype == pl.Utf8 else 0.0
                for name, dtype in _CANDIDATE_SCHEMA.items()
            }
        )
        row.update(payload)
        return row

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _finite(value: Any, default: float = 0.0) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        return result if math.isfinite(result) else default
