"""Build the persisted battle views from the current combat state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from modules.base.systems.military.battle_anchor_policy import BattleAnchor
from modules.base.systems.military.combat_round_resolver import normalize_country_tag
from modules.base.systems.military.readiness_policy import ReadinessPolicy
from modules.base.systems.military.war_index import ConflictContext
from src.shared.events import EventBattleUpdated


@dataclass(frozen=True, slots=True)
class BattleStrengthDelta:
    round_resolved: bool
    previous_a: int
    previous_b: int
    current_a: int
    current_b: int


@dataclass(frozen=True, slots=True)
class BattleRowRequest:
    battle_id: str
    war_id: str
    mode: str
    region_id: int
    side_a_tags: frozenset[str]
    side_b_tags: frozenset[str]
    side_a_strength: int
    side_b_strength: int
    now: int
    side_a_losses: int = 0
    side_b_losses: int = 0
    status: str = "active"
    round_number: int | None = None
    prior_row: dict[str, Any] | None = None
    anchor: BattleAnchor | None = None


class BattleSnapshotBuilder:
    """Build battle, unit, and participant snapshots from domain state."""

    def __init__(self, readiness: ReadinessPolicy) -> None:
        self._readiness = readiness

    def lifecycle_status(
        self,
        prior_row: dict[str, Any],
        strength_delta: BattleStrengthDelta,
    ) -> str:
        """Classify a still-contested battle without inventing extra outcomes."""
        prior_status = str(prior_row.get("status") or "active").lower()
        if not strength_delta.round_resolved:
            return prior_status if prior_status in {"active", "stalemate"} else "active"
        if (
            strength_delta.current_a == strength_delta.previous_a
            and strength_delta.current_b == strength_delta.previous_b
        ):
            return "stalemate"
        return "active"

    def battle_units_changed(
        self,
        battle_units: pl.DataFrame | None,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
    ) -> bool:
        """Detect readiness or participant changes that require a status update."""
        if battle_units is None or battle_units.is_empty() or "battle_id" not in battle_units.columns:
            return bool(local_units)
        existing = self._stored_battle_units(battle_units, battle_id)
        current = self._current_battle_units(local_units, conflict)
        return existing != current

    @staticmethod
    def _stored_battle_units(
        battle_units: pl.DataFrame,
        battle_id: str,
    ) -> dict[str, tuple[str, str, str, float, float]]:
        return {
            str(row.get("unit_id") or ""): (
                str(row.get("country_id") or ""),
                str(row.get("side") or ""),
                str(row.get("readiness_status") or ""),
                float(row.get("contribution_weight") or 0.0),
                float(row.get("effective_strength") or 0.0),
            )
            for row in battle_units.filter(pl.col("battle_id") == battle_id).to_dicts()
        }

    def _current_battle_units(
        self,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
    ) -> dict[str, tuple[str, str, str, float, float]]:
        current: dict[str, tuple[str, str, str, float, float]] = {}
        for row in sorted(local_units, key=lambda unit: str(unit.get("id") or "")):
            owner = normalize_country_tag(row.get("owner"))
            side = self._unit_side(owner, conflict)
            if side is None:
                continue
            weight = self._readiness.combat_weight(row.get("readiness_status"))
            unit_id = str(row.get("id") or "")
            current[unit_id] = (
                owner,
                side,
                self._readiness.normalize(row.get("readiness_status")),
                float(weight),
                float(max(0, int(row.get("strength") or 0)) * weight),
            )
        return current

    @staticmethod
    def _unit_side(owner: str, conflict: ConflictContext) -> str | None:
        if owner in conflict.side_a_members:
            return "SIDE_A"
        if owner in conflict.side_b_members:
            return "SIDE_B"
        return None

    def build_battle_row(self, request: BattleRowRequest) -> dict[str, Any]:
        prior = request.prior_row or {}
        total_strength = max(1, request.side_a_strength + request.side_b_strength)
        current_round = (
            int(prior.get("round") or 0)
            if request.round_number is None
            else int(request.round_number)
        )
        anchor_fields = request.anchor.as_row_fields() if request.anchor is not None else {
            "anchor_latitude": prior.get("anchor_latitude"),
            "anchor_longitude": prior.get("anchor_longitude"),
            "anchor_source": str(prior.get("anchor_source") or ""),
        }
        return {
            "id": request.battle_id,
            "war_id": request.war_id,
            "region_id": request.region_id,
            **anchor_fields,
            "attacker_side": ",".join(sorted(request.side_a_tags)),
            "defender_side": ",".join(sorted(request.side_b_tags)),
            "mode": request.mode,
            "balance": float(request.side_a_strength / total_strength),
            "side_a_strength": float(request.side_a_strength),
            "side_b_strength": float(request.side_b_strength),
            "side_a_losses": int(request.side_a_losses),
            "side_b_losses": int(request.side_b_losses),
            "round": current_round,
            "started_at_minute": int(
                prior.get("started_at_minute")
                if prior.get("started_at_minute") is not None
                else request.now
            ),
            "updated_at_minute": request.now,
            "concluded_at_minute": 0,
            "victor_side": "",
            "status": request.status,
        }

    def build_battle_units(
        self,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
        total_strength: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        safe_total = max(1, total_strength)
        for row in sorted(local_units, key=lambda unit: str(unit.get("id") or "")):
            owner = normalize_country_tag(row.get("owner"))
            side = self._unit_side(owner, conflict)
            if side is None:
                continue

            rows.append(
                {
                    "battle_id": battle_id,
                    "unit_id": str(row.get("id") or ""),
                    "country_id": owner,
                    "side": side,
                    "role": (conflict.roles or {}).get(owner, "principal"),
                    "readiness_status": self._readiness.normalize(row.get("readiness_status")),
                    "contribution_weight": self._readiness.combat_weight(row.get("readiness_status")),
                    "effective_strength": float(
                        max(0, int(row.get("strength") or 0))
                        * self._readiness.combat_weight(row.get("readiness_status"))
                    ),
                    "strength_share": float(int(row.get("strength") or 0) / safe_total),
                }
            )
        return rows

    def build_participants(
        self,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for unit in local_units:
            owner = normalize_country_tag(unit.get("owner"))
            side = self._unit_side(owner, conflict)
            if side is None:
                continue
            key = (owner, side)
            row = grouped.setdefault(key, {
                "battle_id": battle_id,
                "country_id": owner,
                "side": side,
                "role": (conflict.roles or {}).get(owner, "principal"),
                "eligibility_basis": (conflict.bases or {}).get(owner, "war_side"),
                "unit_count": 0,
                "weighted_strength": 0.0,
            })
            row["unit_count"] += 1
            row["weighted_strength"] += max(0, int(unit.get("strength") or 0)) * self._readiness.combat_weight(
                unit.get("readiness_status")
            )
        return [grouped[key] for key in sorted(grouped)]

    @staticmethod
    def build_updated_event(
        row: dict[str, Any],
        conflict: ConflictContext,
        now: int,
    ) -> EventBattleUpdated:
        return EventBattleUpdated(
            battle_id=row['id'],
            region_id=row['region_id'],
            status=row['status'],
            round=int(row['round']),
            side_a_countries=tuple(sorted(conflict.side_a_members)),
            side_b_countries=tuple(sorted(conflict.side_b_members)),
            side_a_strength=float(row['side_a_strength']),
            side_b_strength=float(row['side_b_strength']),
            balance=float(row['balance']),
            updated_at_minute=now,
            side_a_losses=int(row.get('side_a_losses') or 0),
            side_b_losses=int(row.get('side_b_losses') or 0),
        )
