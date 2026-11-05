"""Build persisted battle outcomes and their end events."""

from __future__ import annotations

from typing import Any

from modules.base.systems.military.battle_snapshot_builder import (
    BattleRowRequest,
    BattleSnapshotBuilder,
)
from modules.base.systems.military.battle_victory_finalizer import (
    BattleEndedEventRequest,
    ConcludedBattleRowRequest,
)
from modules.base.systems.military.war_index import WarIndex
from src.shared.events import EventBattleEnded


class BattleConclusionBuilder:
    """Project a resolved victory into the battle row and end event."""

    def __init__(self, snapshots: BattleSnapshotBuilder) -> None:
        self._snapshots = snapshots

    def build_concluded_battle_row(
        self,
        request: ConcludedBattleRowRequest,
    ) -> dict[str, Any]:
        if request.prior_row:
            row = dict(request.prior_row)
            if bool(request.metadata.get("round_resolved")):
                self._apply_resolved_round(row, request.metadata)
        else:
            row = self._new_concluded_battle_row(request)

        row["status"] = "concluded"
        row["updated_at_minute"] = request.now
        row["concluded_at_minute"] = request.now
        row["victor_side"] = request.victor_side
        return row

    def _new_concluded_battle_row(
        self,
        request: ConcludedBattleRowRequest,
    ) -> dict[str, Any]:
        metadata = request.metadata
        side_a_strength = int(metadata.get("side_a_strength", 0))
        side_b_strength = int(metadata.get("side_b_strength", 0))
        previous_a = int(metadata.get("previous_a", 0))
        previous_b = int(metadata.get("previous_b", 0))
        round_resolved = bool(metadata.get("round_resolved"))
        return self._snapshots.build_battle_row(
            BattleRowRequest(
                battle_id=request.battle_id,
                war_id=str(metadata.get("war_id") or ""),
                mode=str(metadata.get("mode") or "positional"),
                region_id=request.region_id,
                side_a_tags=frozenset(metadata.get("side_a_tags") or ()),
                side_b_tags=frozenset(metadata.get("side_b_tags") or ()),
                side_a_strength=side_a_strength,
                side_b_strength=side_b_strength,
                now=request.now,
                side_a_losses=(max(0, previous_a - side_a_strength) if round_resolved else 0),
                side_b_losses=(max(0, previous_b - side_b_strength) if round_resolved else 0),
                status="concluded",
                round_number=1 if round_resolved else 0,
                anchor=metadata.get("anchor"),
            )
        )

    @staticmethod
    def _apply_resolved_round(
        row: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        current_a = int(metadata.get("side_a_strength", row.get("side_a_strength") or 0))
        current_b = int(metadata.get("side_b_strength", row.get("side_b_strength") or 0))
        previous_a = int(metadata.get("previous_a", current_a))
        previous_b = int(metadata.get("previous_b", current_b))
        row["side_a_strength"] = float(current_a)
        row["side_b_strength"] = float(current_b)
        row["balance"] = float(current_a / max(1, current_a + current_b))
        row["side_a_losses"] = int(row.get("side_a_losses") or 0) + max(
            0,
            previous_a - current_a,
        )
        row["side_b_losses"] = int(row.get("side_b_losses") or 0) + max(
            0,
            previous_b - current_b,
        )
        row["round"] = int(row.get("round") or 0) + 1

    @staticmethod
    def build_battle_ended_event(
        request: BattleEndedEventRequest,
    ) -> EventBattleEnded:
        # The finalizer handles several victories after scanning all regions, so event data must come from this battle's concluded row.
        concluded_row = request.concluded_row
        side_a_countries = WarIndex._normalize_side(concluded_row.get("attacker_side"))
        side_b_countries = WarIndex._normalize_side(concluded_row.get("defender_side"))
        return EventBattleEnded(
            battle_id=request.battle_id,
            victor_tag=request.victor,
            victor_side=str(concluded_row.get("victor_side") or ""),
            region_id=request.region_id,
            concluded_at_minute=request.now,
            side_a_losses=int(concluded_row.get("side_a_losses") or 0),
            side_b_losses=int(concluded_row.get("side_b_losses") or 0),
            participant_countries=tuple(sorted(side_a_countries | side_b_countries)),
            side_a_country_ids=tuple(sorted(side_a_countries)),
            side_b_country_ids=tuple(sorted(side_b_countries)),
        )
