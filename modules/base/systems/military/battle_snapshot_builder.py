"""Build the persisted battle views from the current combat state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from modules.base.systems.military.battle_anchor_policy import BattleAnchor
from modules.base.systems.military.battle_change_detection import battle_snapshot_changed
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


@dataclass(frozen=True, slots=True)
class ActiveBattleSnapshotRequest:
    battle_units_table: pl.DataFrame | None
    region_id: int
    local_units: list[dict[str, Any]]
    conflict: ConflictContext
    battle_id: str
    battle_mode: str
    now: int
    prior_row: dict[str, Any]
    anchor: BattleAnchor | None
    previous_a: int
    previous_b: int
    side_a_strength: int
    side_b_strength: int
    resolve_this_tick: bool


@dataclass(slots=True)
class ActiveBattleSnapshot:
    battle_row: dict[str, Any]
    battle_unit_rows: list[dict[str, Any]]
    participant_rows: list[dict[str, Any]]
    updated_event: EventBattleUpdated | None


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

    def build_active_battle_snapshot(
        self,
        request: ActiveBattleSnapshotRequest,
    ) -> ActiveBattleSnapshot:
        conflict = request.conflict
        prior_row = request.prior_row
        status = self.lifecycle_status(
            prior_row,
            BattleStrengthDelta(
                round_resolved=request.resolve_this_tick,
                previous_a=request.previous_a,
                previous_b=request.previous_b,
                current_a=request.side_a_strength,
                current_b=request.side_b_strength,
            ),
        )
        round_number = int(prior_row.get("round") or 0) + (1 if request.resolve_this_tick else 0)
        current_balance = float(
            request.side_a_strength
            / max(1, request.side_a_strength + request.side_b_strength)
        )
        battle_changed = self._active_battle_changed(
            request,
            status,
            current_balance,
        )
        battle_row = (
            self._build_active_battle_row(request, status, round_number)
            if battle_changed
            else prior_row
        )
        event = None
        if battle_changed or float(prior_row.get("balance") or -1.0) != current_balance:
            event = self.build_updated_event(
                battle_row,
                conflict,
                request.now,
            )
        return ActiveBattleSnapshot(
            battle_row=battle_row,
            battle_unit_rows=self.build_battle_units(
                request.battle_id,
                request.local_units,
                conflict,
                request.side_a_strength + request.side_b_strength,
            ),
            participant_rows=self.build_participants(
                request.battle_id,
                request.local_units,
                conflict,
            ),
            updated_event=event,
        )

    def _active_battle_changed(
        self,
        request: ActiveBattleSnapshotRequest,
        status: str,
        balance: float,
    ) -> bool:
        if not request.prior_row or request.resolve_this_tick:
            return True
        if battle_snapshot_changed(
            request.prior_row,
            status=status,
            mode=request.battle_mode,
            side_a_tags=request.conflict.side_a_tags,
            side_b_tags=request.conflict.side_b_tags,
            side_a_strength=request.side_a_strength,
            side_b_strength=request.side_b_strength,
            balance=balance,
        ):
            return True
        return self.battle_units_changed(
            request.battle_units_table,
            request.battle_id,
            request.local_units,
            request.conflict,
        )

    def _build_active_battle_row(
        self,
        request: ActiveBattleSnapshotRequest,
        status: str,
        round_number: int,
    ) -> dict[str, Any]:
        conflict = request.conflict
        prior_row = request.prior_row
        return self.build_battle_row(
            BattleRowRequest(
                battle_id=request.battle_id,
                war_id=conflict.war_id,
                mode=request.battle_mode,
                region_id=request.region_id,
                side_a_tags=conflict.side_a_tags,
                side_b_tags=conflict.side_b_tags,
                side_a_strength=request.side_a_strength,
                side_b_strength=request.side_b_strength,
                now=request.now,
                side_a_losses=int(prior_row.get("side_a_losses") or 0)
                + (
                    max(0, request.previous_a - request.side_a_strength)
                    if request.resolve_this_tick
                    else 0
                ),
                side_b_losses=int(prior_row.get("side_b_losses") or 0)
                + (
                    max(0, request.previous_b - request.side_b_strength)
                    if request.resolve_this_tick
                    else 0
                ),
                status=status,
                round_number=round_number,
                prior_row=prior_row,
                anchor=request.anchor,
            )
        )

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
