"""Resolve region control and occupation updates after combat."""

from __future__ import annotations

from typing import Any

from modules.base.systems.military.battle_victory_finalizer import (
    ConcludedOccupationUpdateRequest,
)
from modules.base.systems.military.combat_round_resolver import (
    CombatRoundResolver,
    normalize_country_tag,
)
from modules.base.systems.military.war_index import WarIndex


UNCLAIMED_TAGS = {"", "None"}


class BattleOccupationPolicy:
    """Apply occupation rules using combat strength and active war context."""

    def __init__(self, combat_resolver: CombatRoundResolver) -> None:
        self._combat_resolver = combat_resolver

    def replace_occupation(
        self,
        occupation_rows: list[dict[str, Any]],
        region_id: int,
        controller: str,
        local_units: list[dict[str, Any]],
        now: int,
    ) -> list[dict[str, Any]]:
        previous = next(
            (row for row in occupation_rows if int(row.get("region_id") or 0) == region_id),
            None,
        )
        updated = self.occupation_row(region_id, controller, local_units, now, previous)
        retained = [row for row in occupation_rows if int(row.get("region_id") or 0) != region_id]
        retained.append(updated)
        return retained

    def update_uncontested_region(
        self,
        region_id: int,
        region_row: dict[str, Any],
        local_units: list[dict[str, Any]],
        wars: WarIndex,
        occupation_rows: list[dict[str, Any]],
        now: int,
    ) -> list[dict[str, Any]]:
        for unit in local_units:
            unit["engagement_mode"] = ""
        occupier = self.occupation_candidate(
            local_units=local_units,
            current_controller=normalize_country_tag(region_row.get("controller")),
            wars=wars,
        )
        if occupier is not None:
            region_row["controller"] = occupier
            occupation_rows = self.replace_occupation(
                occupation_rows,
                region_id,
                occupier,
                local_units,
                now,
            )
        return occupation_rows

    def update_concluded_occupation(
        self,
        request: ConcludedOccupationUpdateRequest,
    ) -> list[dict[str, Any]]:
        region_id = request.region_id
        victor = request.victor
        unit_rows = request.unit_rows
        region_rows = request.region_rows
        occupation_rows = request.occupation_rows
        now = request.now
        if victor:
            self.set_region_controller(region_rows, region_id, victor)
            victor_tag = normalize_country_tag(victor)
            garrison_units = [
                row
                for row in unit_rows
                if self._is_victor_garrison(row, region_id, victor_tag)
            ]
            occupation_rows = self.replace_occupation(
                occupation_rows,
                region_id,
                victor_tag,
                garrison_units,
                now,
            )
        else:
            for occupation in occupation_rows:
                if int(occupation.get("region_id") or 0) == region_id:
                    occupation["contested"] = True
                    occupation["occupation_status"] = "contested"
                    occupation["updated_at_minute"] = now
        return occupation_rows

    @staticmethod
    def _is_victor_garrison(
        row: dict[str, Any],
        region_id: int,
        victor_tag: str,
    ) -> bool:
        if int(row.get("current_region_id") or 0) != region_id:
            return False
        if normalize_country_tag(row.get("owner")) != victor_tag:
            return False
        if int(row.get("strength") or 0) <= 0:
            return False
        return not bool(row.get("is_moving"))

    def occupation_row(
        self,
        region_id: int,
        occupier: str,
        local_units: list[dict[str, Any]],
        now: int,
        previous: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        prior = previous or {}
        row = {
            "region_id": region_id,
            "controller_country_id": occupier,
            "garrison_strength": int(self._combat_resolver.raw_strength(local_units, {occupier})),
            "resistance": 0.0,
            "occupation_status": "active",
            "started_at_minute": int(
                prior.get("started_at_minute")
                if prior.get("started_at_minute") is not None
                else now
            ),
            "updated_at_minute": now,
            "contested": False,
        }
        stable_fields = (
            "region_id",
            "controller_country_id",
            "garrison_strength",
            "resistance",
            "occupation_status",
            "contested",
        )
        if prior and all(prior.get(field) == row.get(field) for field in stable_fields):
            return prior
        return row

    def occupation_candidate(
        self,
        local_units: list[dict[str, Any]],
        current_controller: str,
        wars: WarIndex,
    ) -> str | None:
        if not local_units or current_controller in UNCLAIMED_TAGS:
            return None

        owners = {
            normalize_country_tag(row.get("owner"))
            for row in local_units
            if normalize_country_tag(row.get("owner"))
        }
        sorted_strengths = sorted(
            (
                (owner, self._combat_resolver.total_strength(local_units, {owner}))
                for owner in owners
            ),
            key=lambda item: (-item[1], item[0]),
        )
        if not sorted_strengths:
            return None

        occupier = sorted_strengths[0][0]
        if occupier == current_controller:
            return None
        if not wars.is_hostile(occupier, current_controller):
            return None

        if self._has_hostile_opposition(sorted_strengths[1:], occupier, wars):
            return None
        return occupier

    @staticmethod
    def _has_hostile_opposition(
        ranked_owners: list[tuple[str, int]],
        occupier: str,
        wars: WarIndex,
    ) -> bool:
        return any(wars.is_hostile(owner, occupier) for owner, _ in ranked_owners)

    @staticmethod
    def set_region_controller(
        region_rows: list[dict[str, Any]],
        region_id: int,
        controller_tag: str,
    ) -> None:
        for row in region_rows:
            if int(row.get("id") or 0) == region_id:
                row["controller"] = controller_tag
                return
