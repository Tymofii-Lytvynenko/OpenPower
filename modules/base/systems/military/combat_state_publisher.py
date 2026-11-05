"""Persist the outputs of one combat tick into shared game state."""

from __future__ import annotations

from typing import Any

import polars as pl

from modules.base.systems.military.battle_public_counts import public_battle_counts
from modules.base.systems.military.battle_region_processor import BattleRegionScanResult
from modules.base.systems.military.combat_round_resolver import normalize_country_tag
from src.shared.events import EventOccupationChanged
from src.shared.state import GameState


BATTLE_TABLE = "battles"
BATTLE_UNITS_TABLE = "battle_units"
COUNTRIES_WARS_TABLE = "countries_wars"
REGIONS_TABLE = "regions"
UNITS_TABLE = "units"
BATTLE_PARTICIPANTS_TABLE = "battle_participants"
CASUALTY_RECORDS_TABLE = "battle_casualty_records"
PUBLIC_COUNTS_TABLE = "battle_public_counts"
OCCUPATIONS_TABLE = "occupations"
COUNTRIES_TABLE = "countries"


class CombatStatePublisher:
    """Commit combat projections and related events to shared state."""

    def __init__(
        self,
        battle_schema: dict[str, pl.DataType],
        battle_units_schema: dict[str, pl.DataType],
        participants_schema: dict[str, pl.DataType],
        occupation_schema: dict[str, pl.DataType],
    ) -> None:
        self._battle_schema = battle_schema
        self._battle_units_schema = battle_units_schema
        self._participants_schema = participants_schema
        self._occupation_schema = occupation_schema

    def reset_battle_tables(self, state: GameState) -> None:
        self._update_table_if_changed(
            state,
            BATTLE_TABLE,
            pl.DataFrame(schema=self._battle_schema),
        )
        self._update_table_if_changed(
            state,
            BATTLE_UNITS_TABLE,
            pl.DataFrame(schema=self._battle_units_schema),
        )
        self._update_table_if_changed(
            state,
            BATTLE_PARTICIPANTS_TABLE,
            pl.DataFrame(schema=self._participants_schema),
        )
        self._update_table_if_changed(
            state,
            OCCUPATIONS_TABLE,
            pl.DataFrame(schema=self._occupation_schema),
        )

    def publish_tick(
        self,
        state: GameState,
        regions: pl.DataFrame,
        unit_schema: dict[str, pl.DataType],
        casualty_table: pl.DataFrame | None,
        result: BattleRegionScanResult,
    ) -> None:
        result.unit_rows = [
            row for row in result.unit_rows if int(row.get("strength") or 0) > 0
        ]
        self._update_table_if_changed(
            state,
            UNITS_TABLE,
            self._frame_from_rows(unit_schema, result.unit_rows),
        )
        self._publish_controller_changes(
            state,
            regions,
            result.region_rows,
            result.original_controllers,
        )
        self._update_table_if_changed(
            state,
            BATTLE_TABLE,
            self._frame_from_rows(self._battle_schema, result.battle_rows),
        )
        self._update_table_if_changed(
            state,
            BATTLE_UNITS_TABLE,
            self._frame_from_rows(self._battle_units_schema, result.battle_unit_rows),
        )
        self._publish_public_counts(state, result)
        self._update_table_if_changed(
            state,
            BATTLE_PARTICIPANTS_TABLE,
            self._frame_from_rows(self._participants_schema, result.participant_rows),
        )
        self._publish_casualties(state, result.casualty_rows, casualty_table)
        self._update_table_if_changed(
            state,
            OCCUPATIONS_TABLE,
            self._frame_from_rows(self._occupation_schema, result.occupation_rows),
        )
        if COUNTRIES_TABLE in state.tables:
            self._update_table_if_changed(
                state,
                COUNTRIES_TABLE,
                self._sync_country_strengths(
                    state.get_table(COUNTRIES_TABLE),
                    result.unit_rows,
                ),
            )

    def _publish_public_counts(
        self,
        state: GameState,
        result: BattleRegionScanResult,
    ) -> None:
        alive_ids = {str(row.get("id")) for row in result.unit_rows}
        visible_units = [
            row
            for row in result.battle_unit_rows
            if str(row.get("unit_id")) in alive_ids
        ]
        self._update_table_if_changed(
            state,
            PUBLIC_COUNTS_TABLE,
            public_battle_counts(result.battle_rows, visible_units, result.unit_rows),
        )

    def _publish_controller_changes(
        self,
        state: GameState,
        regions: pl.DataFrame,
        region_rows: list[dict[str, Any]],
        original_controllers: dict[int, str],
    ) -> None:
        controller_updates = {
            int(row.get("id") or 0): str(row.get("controller") or "")
            for row in region_rows
            if str(row.get("controller") or "")
            != original_controllers.get(int(row.get("id") or 0), "")
        }
        updated_regions = regions
        if controller_updates:
            all_region_rows = regions.to_dicts()
            for region_id, controller in controller_updates.items():
                state.events.append(
                    EventOccupationChanged(
                        region_id=region_id,
                        previous_controller=str(original_controllers.get(region_id) or ""),
                        controller=controller,
                        source="battle_resolution",
                        at_minute=int(state.time.total_minutes),
                    )
                )
                self._set_region_controller(all_region_rows, region_id, controller)
            updated_regions = self._frame_from_rows(regions.schema, all_region_rows)
        self._update_table_if_changed(state, REGIONS_TABLE, updated_regions)

    @staticmethod
    def _set_region_controller(
        region_rows: list[dict[str, Any]],
        region_id: int,
        controller_tag: str,
    ) -> None:
        for row in region_rows:
            if int(row.get("id") or 0) == region_id:
                row["controller"] = controller_tag
                return

    def _publish_casualties(
        self,
        state: GameState,
        casualty_rows: list[dict[str, Any]],
        casualty_table: pl.DataFrame | None,
    ) -> None:
        current_rows = [] if casualty_table is None else casualty_table.to_dicts()
        if casualty_rows == current_rows:
            return
        casualty_schema = {
            "id": pl.Utf8,
            "battle_id": pl.Utf8,
            "unit_id": pl.Utf8,
            "country_id": pl.Utf8,
            "side": pl.Utf8,
            "unit_type": pl.Utf8,
            "losses": pl.Int64,
            "round": pl.Int32,
            "created_at_minute": pl.Int64,
        }
        sorted_rows = sorted(casualty_rows, key=lambda row: str(row.get("id") or ""))
        updated_casualties = self._frame_from_rows(casualty_schema, sorted_rows)
        self._update_table_if_changed(state, CASUALTY_RECORDS_TABLE, updated_casualties)

    @staticmethod
    def _sync_country_strengths(
        countries: pl.DataFrame,
        unit_rows: list[dict[str, Any]],
    ) -> pl.DataFrame:
        if "id" not in countries.columns:
            return countries
        if "military_count" not in countries.columns:
            countries = countries.with_columns(pl.lit(0).alias("military_count"))

        strength_by_owner: dict[str, int] = {}
        for row in unit_rows:
            owner = normalize_country_tag(row.get("owner"))
            if owner:
                strength_by_owner[owner] = strength_by_owner.get(owner, 0) + max(
                    0,
                    int(row.get("strength") or 0),
                )

        return countries.with_columns(
            pl.col("id")
            .map_elements(
                lambda country_id: int(strength_by_owner.get(str(country_id), 0)),
                return_dtype=pl.Int64,
            )
            .alias("military_count")
        )

    @staticmethod
    def _update_table_if_changed(
        state: GameState,
        name: str,
        frame: pl.DataFrame,
    ) -> bool:
        current = state.tables.get(name)
        if current is not None and current.equals(frame):
            return False
        state.update_table(name, frame)
        return True

    @staticmethod
    def _frame_from_rows(
        schema: dict[str, pl.DataType],
        rows: list[dict[str, Any]],
    ) -> pl.DataFrame:
        if not rows:
            return pl.DataFrame(schema=schema)
        return pl.DataFrame(rows, schema=schema)
