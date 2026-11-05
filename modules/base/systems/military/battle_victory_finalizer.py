"""Finalize battle outcomes after every region has been evaluated."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import polars as pl

from src.shared.events import EventBattleEnded
from src.shared.state import GameState


@dataclass(slots=True)
class VictoryResolutionBatch:
    victors: dict[str, str]
    victor_sides: dict[str, str]
    active_battle_ids: set[str]
    battle_regions: dict[str, int]
    battle_metadata: dict[str, dict[str, Any]]
    battle_rows: list[dict[str, Any]]
    unit_rows: list[dict[str, Any]]
    region_rows: list[dict[str, Any]]
    occupation_rows: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ConcludedBattleRowRequest:
    prior_row: dict[str, Any]
    battle_id: str
    region_id: int
    metadata: dict[str, Any]
    now: int
    victor_side: str


@dataclass(frozen=True, slots=True)
class BattleEndedEventRequest:
    battle_id: str
    victor: str
    region_id: int
    now: int
    concluded_row: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ConcludedOccupationUpdateRequest:
    region_id: int
    victor: str
    unit_rows: list[dict[str, Any]]
    region_rows: list[dict[str, Any]]
    occupation_rows: list[dict[str, Any]]
    now: int


class _BattleRowLookup(Protocol):
    def __call__(
        self,
        battles: pl.DataFrame | None,
        battle_id: str,
    ) -> dict[str, Any]: ...


class _ConcludedBattleRowBuilder(Protocol):
    def __call__(
        self,
        request: ConcludedBattleRowRequest,
    ) -> dict[str, Any]: ...


class _BattleEndedEventFactory(Protocol):
    def __call__(
        self,
        request: BattleEndedEventRequest,
    ) -> EventBattleEnded: ...


class _ConcludedOccupationUpdater(Protocol):
    def __call__(
        self,
        request: ConcludedOccupationUpdateRequest,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class VictoryFinalizationOperations:
    battle_row_lookup: _BattleRowLookup
    concluded_battle_row_builder: _ConcludedBattleRowBuilder
    battle_ended_event_factory: _BattleEndedEventFactory
    concluded_occupation_updater: _ConcludedOccupationUpdater


class BattleVictoryFinalizer:
    """Apply battle victory effects in their deterministic post-scan order."""

    def __init__(self, operations: VictoryFinalizationOperations) -> None:
        self._operations = operations

    def finalize(
        self,
        state: GameState,
        batch: VictoryResolutionBatch,
    ) -> list[dict[str, Any]]:
        occupation_rows = batch.occupation_rows
        for battle_id, victor in batch.victors.items():
            if battle_id in batch.active_battle_ids:
                batch.active_battle_ids.remove(battle_id)
            region_id = batch.battle_regions.get(
                battle_id,
                int(battle_id.split("-")[2]),
            )
            prior_row = self._operations.battle_row_lookup(
                state.tables.get("battles"),
                battle_id,
            )
            concluded_row = self._operations.concluded_battle_row_builder(
                ConcludedBattleRowRequest(
                    prior_row=prior_row,
                    battle_id=battle_id,
                    region_id=region_id,
                    metadata=batch.battle_metadata.get(battle_id, {}),
                    now=int(state.time.total_minutes),
                    victor_side=batch.victor_sides.get(battle_id, ""),
                )
            )
            batch.battle_rows.append(concluded_row)
            state.events.append(self._operations.battle_ended_event_factory(
                BattleEndedEventRequest(
                    battle_id=battle_id,
                    victor=victor,
                    region_id=region_id,
                    now=int(state.time.total_minutes),
                    concluded_row=concluded_row,
                )
            ))
            occupation_rows = self._operations.concluded_occupation_updater(
                ConcludedOccupationUpdateRequest(
                    region_id=region_id,
                    victor=victor,
                    unit_rows=batch.unit_rows,
                    region_rows=batch.region_rows,
                    occupation_rows=occupation_rows,
                    now=int(state.time.total_minutes),
                )
            )
        return occupation_rows
