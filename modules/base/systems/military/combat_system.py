from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import polars as pl

from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_HELPER
from src.shared.events import EventBattleEnded, EventBattleStarted, EventNewHour
from src.shared.actions import ActionAttackUnit, ActionMoveUnit
from src.shared.state import GameState


BATTLE_TABLE = "battles"
BATTLE_UNITS_TABLE = "battle_units"
COUNTRIES_WARS_TABLE = "countries_wars"
REGIONS_TABLE = "regions"
UNITS_TABLE = "units"
UNCLAIMED_TAGS = {"", "None"}

BATTLE_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "region_id": pl.Int32,
    "attacker_side": pl.Utf8,
    "mode": pl.Utf8,
    "defender_side": pl.Utf8,
    "balance": pl.Float64,
    "status": pl.Utf8,
}

BATTLE_UNITS_SCHEMA: dict[str, pl.DataType] = {
    "battle_id": pl.Utf8,
    "unit_id": pl.Utf8,
    "side": pl.Utf8,
    "strength_share": pl.Float64,
}

UNIT_REQUIRED_COLUMNS: dict[str, tuple[pl.DataType, Any]] = {
    "id": (pl.Utf8, ""),
    "owner": (pl.Utf8, ""),
    "strength": (pl.Int64, 0),
    "engagement_mode": (pl.Utf8, ""),
    "current_region_id": (pl.Int32, 0),
    "is_moving": (pl.Boolean, False),
}


@dataclass(frozen=True, slots=True)
class WarRecord:
    war_id: str
    side_a: frozenset[str]
    side_b: frozenset[str]
    status: str


@dataclass(frozen=True, slots=True)
class ConflictContext:
    war_id: str
    side_a_members: frozenset[str]
    side_b_members: frozenset[str]
    side_a_tags: frozenset[str]
    side_b_tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class CombatOutcome:
    attacker_losses: int
    defender_losses: int


class WarIndex:
    """Resolves active wartime relationships without coupling combat to table shape."""

    def __init__(self, active_wars: list[WarRecord]):
        self._active_wars = active_wars

    @classmethod
    def from_table(cls, wars: pl.DataFrame | None) -> "WarIndex":
        if wars is None or wars.is_empty():
            return cls([])

        records: list[WarRecord] = []
        for index, row in enumerate(wars.to_dicts(), start=1):
            status = str(row.get("status") or "active").lower()
            if status not in {"active", "ongoing", ""}:
                continue

            side_a = cls._normalize_side(row.get("side_a"))
            side_b = cls._normalize_side(row.get("side_b"))
            if not side_a or not side_b:
                continue

            records.append(
                WarRecord(
                    war_id=str(row.get("id") or f"war-{index:03d}"),
                    side_a=frozenset(side_a),
                    side_b=frozenset(side_b),
                    status=status or "active",
                )
            )

        return cls(records)

    def active_battle_for_region(self, owners: set[str]) -> ConflictContext | None:
        for war in self._active_wars:
            present_a = frozenset(tag for tag in owners if tag in war.side_a)
            present_b = frozenset(tag for tag in owners if tag in war.side_b)
            if present_a and present_b:
                return ConflictContext(
                    war_id=war.war_id,
                    side_a_members=war.side_a,
                    side_b_members=war.side_b,
                    side_a_tags=present_a,
                    side_b_tags=present_b,
                )
        return None

    def is_hostile(self, left: str | None, right: str | None) -> bool:
        if not left or not right or left == right:
            return False

        for war in self._active_wars:
            if (left in war.side_a and right in war.side_b) or (left in war.side_b and right in war.side_a):
                return True
        return False

    @staticmethod
    def _normalize_side(value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, list):
            return {str(tag).strip().upper() for tag in value if str(tag).strip()}
        if isinstance(value, tuple):
            return {str(tag).strip().upper() for tag in value if str(tag).strip()}
        if isinstance(value, str):
            return {tag.strip().upper() for tag in value.split(",") if tag.strip()}
        return set()


class CombatResolutionPolicy:
    """Keeps combat deterministic and easy to tune independently from system flow."""

    def resolve(self, attacker_strength: int, defender_strength: int, mode: str = "positional") -> CombatOutcome:
        if attacker_strength <= 0 or defender_strength <= 0:
            return CombatOutcome(0, 0)

        intensity = 1.35 if mode == "assault" else 1.0
        stronger = max(attacker_strength, defender_strength)
        weaker = min(attacker_strength, defender_strength)
        if weaker > 0 and stronger / weaker >= 2.5:
            if attacker_strength >= defender_strength:
                return CombatOutcome(
                    attacker_losses=max(1, int(round(attacker_strength * 0.08 * intensity))),
                    defender_losses=defender_strength,
                )
            return CombatOutcome(
                attacker_losses=attacker_strength,
                defender_losses=max(1, int(round(defender_strength * 0.08 * intensity))),
            )

        total = attacker_strength + defender_strength
        attacker_share = attacker_strength / total
        defender_share = defender_strength / total

        attacker_losses = max(1, int(round(attacker_strength * (0.10 + (defender_share * 0.18)) * intensity)))
        defender_losses = max(1, int(round(defender_strength * (0.12 + (attacker_share * 0.22)) * intensity)))
        return CombatOutcome(attacker_losses=attacker_losses, defender_losses=defender_losses)


class CombatSystem(ISystem):
    access = SystemAccess(
        reads=frozenset({'countries', 'regions', 'units', 'countries_wars', 'battles'}),
        writes=frozenset({'regions', 'units', 'battles'}),
        handles=frozenset({ActionAttackUnit, ActionMoveUnit}),
        phase=SystemPhase.COMBAT,
    )
    runtime_state_contract = {
        "_policy": SYSTEM_STATE_HELPER,
    }

    def __init__(self):
        self._policy = CombatResolutionPolicy()

    @property
    def id(self) -> str:
        return "base.combat"

    @property
    def dependencies(self) -> list[str]:
        return ["base.military", "base.diplomacy"]

    def update(self, state: GameState, delta_time: float) -> None:
        if REGIONS_TABLE not in state.tables or UNITS_TABLE not in state.tables:
            self._reset_battle_tables(state)
            return

        regions = self._ensure_regions_table(state.get_table(REGIONS_TABLE))
        units = self._ensure_units_table(state.get_table(UNITS_TABLE))
        wars = WarIndex.from_table(state.tables.get(COUNTRIES_WARS_TABLE))
        existing_battles = self._existing_active_battle_ids(state.tables.get(BATTLE_TABLE))
        should_resolve = (not state.time.is_paused) and any(isinstance(event, EventNewHour) for event in state.events)
        assaulting_unit_ids = {
            action.attacker_unit_id if isinstance(action, ActionAttackUnit) else action.unit_id
            for action in state.current_actions
            if isinstance(action, (ActionAttackUnit, ActionMoveUnit))
        }

        region_rows = regions.to_dicts()
        unit_rows = units.to_dicts()
        stationary_units = self._stationary_units_by_region(unit_rows)

        battle_rows: list[dict[str, Any]] = []
        battle_unit_rows: list[dict[str, Any]] = []
        active_battle_ids: set[str] = set()
        victorious_battles: dict[str, str] = {}

        for region_row in region_rows:
            region_id = int(region_row.get("id") or 0)
            if region_id <= 0:
                continue

            local_units = stationary_units.get(region_id, [])
            if not local_units:
                continue

            present_owners = {self._clean_tag(row.get("owner")) for row in local_units if self._clean_tag(row.get("owner"))}
            if not present_owners:
                continue

            conflict = wars.active_battle_for_region(present_owners)
            if conflict is not None:
                battle_mode = self._battle_mode(local_units)
                battle_id = self._battle_id(region_id, conflict.war_id)
                active_battle_ids.add(battle_id)
                if battle_id not in existing_battles:
                    state.events.append(EventBattleStarted(battle_id=battle_id, region_id=region_id))

                if should_resolve or (
                    battle_mode == "assault"
                    and any(str(row.get("id") or "") in assaulting_unit_ids for row in local_units)
                ):
                    victor = self._apply_combat_round(local_units, conflict, battle_mode)
                    if victor is not None:
                        victorious_battles[battle_id] = victor

                side_a_strength = self._total_strength(local_units, conflict.side_a_members)
                side_b_strength = self._total_strength(local_units, conflict.side_b_members)
                if side_a_strength > 0 and side_b_strength > 0:
                    battle_rows.append(
                        self._build_battle_row(
                            battle_id=battle_id,
                            mode=battle_mode,
                            region_id=region_id,
                            side_a_tags=conflict.side_a_tags,
                            side_b_tags=conflict.side_b_tags,
                            side_a_strength=side_a_strength,
                            side_b_strength=side_b_strength,
                        )
                    )
                    battle_unit_rows.extend(
                        self._build_battle_units(
                            battle_id=battle_id,
                            local_units=local_units,
                            conflict=conflict,
                            total_strength=side_a_strength + side_b_strength,
                        )
                    )
                else:
                    winner = self._winning_country(local_units, conflict)
                    if winner:
                        victorious_battles[battle_id] = winner
            else:
                for unit in local_units:
                    unit["engagement_mode"] = ""
                occupier = self._occupation_candidate(
                    local_units=local_units,
                    current_controller=self._clean_tag(region_row.get("controller")),
                    wars=wars,
                )
                if occupier is not None:
                    region_row["controller"] = occupier

        # Apply battle outcomes after the scan so a resolved battle does not emit both
        # an active row and an end event for the same tick.
        for battle_id, victor in victorious_battles.items():
            if battle_id in active_battle_ids:
                active_battle_ids.remove(battle_id)
            region_id = int(battle_id.split("-")[2])
            state.events.append(EventBattleEnded(battle_id=battle_id, victor_tag=victor))
            self._set_region_controller(region_rows, region_id, victor)

        unit_rows = [row for row in unit_rows if int(row.get("strength") or 0) > 0]
        state.update_table(UNITS_TABLE, self._frame_from_rows(units.schema, unit_rows))
        state.update_table(REGIONS_TABLE, self._frame_from_rows(regions.schema, region_rows))
        state.update_table(BATTLE_TABLE, self._frame_from_rows(BATTLE_SCHEMA, battle_rows))
        state.update_table(BATTLE_UNITS_TABLE, self._frame_from_rows(BATTLE_UNITS_SCHEMA, battle_unit_rows))

        if "countries" in state.tables:
            state.update_table("countries", self._sync_country_strengths(state.get_table("countries"), unit_rows))

    def _ensure_regions_table(self, regions: pl.DataFrame) -> pl.DataFrame:
        if "controller" not in regions.columns:
            return regions.with_columns(pl.col("owner").alias("controller"))
        return regions

    def _ensure_units_table(self, units: pl.DataFrame) -> pl.DataFrame:
        for column, (_, default_value) in UNIT_REQUIRED_COLUMNS.items():
            if column not in units.columns:
                units = units.with_columns(pl.lit(default_value).alias(column))

        casted_columns = []
        for column, (dtype, _) in UNIT_REQUIRED_COLUMNS.items():
            casted_columns.append(pl.col(column).cast(dtype).alias(column))

        return units.with_columns(casted_columns)

    def _stationary_units_by_region(self, unit_rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in unit_rows:
            if bool(row.get("is_moving", False)):
                continue
            region_id = int(row.get("current_region_id") or 0)
            if region_id <= 0:
                continue
            grouped.setdefault(region_id, []).append(row)
        return grouped
    def _battle_mode(self, local_units: list[dict[str, Any]]) -> str:
        return "assault" if any(str(row.get("engagement_mode") or "").lower() == "assault" for row in local_units) else "positional"


    def _apply_combat_round(
        self,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
        mode: str,
    ) -> str | None:
        side_a_strength = self._total_strength(local_units, conflict.side_a_members)
        side_b_strength = self._total_strength(local_units, conflict.side_b_members)
        outcome = self._policy.resolve(side_a_strength, side_b_strength, mode)
        self._distribute_losses(local_units, conflict.side_a_members, outcome.attacker_losses)
        self._distribute_losses(local_units, conflict.side_b_members, outcome.defender_losses)

        remaining_a = self._total_strength(local_units, conflict.side_a_members)
        remaining_b = self._total_strength(local_units, conflict.side_b_members)
        if remaining_a > 0 and remaining_b > 0:
            return None
        if remaining_a <= 0 and remaining_b <= 0:
            return None
        if remaining_a > 0:
            return self._dominant_country(local_units, conflict.side_a_members)
        return self._dominant_country(local_units, conflict.side_b_members)

    def _build_battle_row(
        self,
        battle_id: str,
        mode: str,
        region_id: int,
        side_a_tags: frozenset[str],
        side_b_tags: frozenset[str],
        side_a_strength: int,
        side_b_strength: int,
    ) -> dict[str, Any]:
        total_strength = max(1, side_a_strength + side_b_strength)
        return {
            "id": battle_id,
            "region_id": region_id,
            "attacker_side": ",".join(sorted(side_a_tags)),
            "defender_side": ",".join(sorted(side_b_tags)),
            "mode": mode,
            "balance": float(side_a_strength / total_strength),
            "status": "active",
        }

    def _build_battle_units(
        self,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
        total_strength: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        safe_total = max(1, total_strength)
        for row in sorted(local_units, key=lambda unit: str(unit.get("id") or "")):
            owner = self._clean_tag(row.get("owner"))
            if owner in conflict.side_a_members:
                side = "attacker"
            elif owner in conflict.side_b_members:
                side = "defender"
            else:
                continue

            rows.append(
                {
                    "battle_id": battle_id,
                    "unit_id": str(row.get("id") or ""),
                    "side": side,
                    "strength_share": float(int(row.get("strength") or 0) / safe_total),
                }
            )
        return rows

    def _occupation_candidate(
        self,
        local_units: list[dict[str, Any]],
        current_controller: str,
        wars: WarIndex,
    ) -> str | None:
        if not local_units or current_controller in UNCLAIMED_TAGS:
            return None

        sorted_strengths = sorted(
            (
                (owner, self._total_strength(local_units, {owner}))
                for owner in {self._clean_tag(row.get("owner")) for row in local_units if self._clean_tag(row.get("owner"))}
            ),
            key=lambda item: (-item[1], item[0]),
        )
        if not sorted_strengths:
            return None

        occupier = sorted_strengths[0][0]
        if occupier == current_controller or not wars.is_hostile(occupier, current_controller):
            return None

        for owner, _ in sorted_strengths[1:]:
            if wars.is_hostile(owner, occupier):
                return None

        return occupier

    def _dominant_country(self, local_units: list[dict[str, Any]], eligible_tags: Iterable[str]) -> str:
        best_tag = ""
        best_strength = -1
        eligible = set(eligible_tags)
        for tag in sorted(eligible):
            strength = self._total_strength(local_units, {tag})
            if strength > best_strength:
                best_strength = strength
                best_tag = tag
        return best_tag

    def _winning_country(self, local_units: list[dict[str, Any]], conflict: ConflictContext) -> str:
        remaining_a = self._total_strength(local_units, conflict.side_a_members)
        remaining_b = self._total_strength(local_units, conflict.side_b_members)
        if remaining_a > remaining_b:
            return self._dominant_country(local_units, conflict.side_a_members)
        if remaining_b > remaining_a:
            return self._dominant_country(local_units, conflict.side_b_members)
        return ""

    def _total_strength(self, local_units: list[dict[str, Any]], eligible_tags: Iterable[str]) -> int:
        eligible = set(eligible_tags)
        return sum(
            max(0, int(row.get("strength") or 0))
            for row in local_units
            if self._clean_tag(row.get("owner")) in eligible
        )

    def _distribute_losses(self, local_units: list[dict[str, Any]], eligible_tags: Iterable[str], total_losses: int) -> None:
        remaining_losses = max(0, total_losses)
        if remaining_losses <= 0:
            return

        eligible_rows = [
            row
            for row in sorted(local_units, key=lambda unit: str(unit.get("id") or ""))
            if self._clean_tag(row.get("owner")) in set(eligible_tags) and int(row.get("strength") or 0) > 0
        ]
        if not eligible_rows:
            return

        remaining_strength = sum(int(row.get("strength") or 0) for row in eligible_rows)
        for index, row in enumerate(eligible_rows):
            if remaining_losses <= 0:
                break

            strength = max(0, int(row.get("strength") or 0))
            if strength <= 0 or remaining_strength <= 0:
                continue

            if index == len(eligible_rows) - 1:
                row_losses = remaining_losses
            else:
                row_share = strength / remaining_strength
                row_losses = max(1, int(round(total_losses * row_share)))
                row_losses = min(row_losses, remaining_losses)

            applied_losses = min(strength, row_losses)
            row["strength"] = strength - applied_losses
            remaining_losses -= applied_losses
            remaining_strength -= strength

    def _existing_active_battle_ids(self, battles: pl.DataFrame | None) -> set[str]:
        if battles is None or battles.is_empty() or "id" not in battles.columns:
            return set()
        if "status" not in battles.columns:
            return {str(value) for value in battles["id"].to_list()}
        return {
            str(row["id"])
            for row in battles.select(["id", "status"]).iter_rows(named=True)
            if str(row.get("status") or "").lower() == "active"
        }

    def _sync_country_strengths(self, countries: pl.DataFrame, unit_rows: list[dict[str, Any]]) -> pl.DataFrame:
        if "id" not in countries.columns:
            return countries

        if "military_count" not in countries.columns:
            countries = countries.with_columns(pl.lit(0).alias("military_count"))

        strength_by_owner: dict[str, int] = {}
        for row in unit_rows:
            owner = self._clean_tag(row.get("owner"))
            if not owner:
                continue
            strength_by_owner[owner] = strength_by_owner.get(owner, 0) + max(0, int(row.get("strength") or 0))

        return countries.with_columns(
            pl.col("id").map_elements(
                lambda country_id: int(strength_by_owner.get(str(country_id), 0)),
                return_dtype=pl.Int64,
            ).alias("military_count")
        )

    def _set_region_controller(self, region_rows: list[dict[str, Any]], region_id: int, controller_tag: str) -> None:
        for row in region_rows:
            if int(row.get("id") or 0) == region_id:
                row["controller"] = controller_tag
                return

    def _battle_id(self, region_id: int, war_id: str) -> str:
        return f"battle-region-{region_id}-{war_id}"

    def _clean_tag(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().upper()

    def _reset_battle_tables(self, state: GameState) -> None:
        state.update_table(BATTLE_TABLE, pl.DataFrame(schema=BATTLE_SCHEMA))
        state.update_table(BATTLE_UNITS_TABLE, pl.DataFrame(schema=BATTLE_UNITS_SCHEMA))

    def _frame_from_rows(self, schema: dict[str, pl.DataType], rows: list[dict[str, Any]]) -> pl.DataFrame:
        if not rows:
            return pl.DataFrame(schema=schema)
        return pl.DataFrame(rows, schema=schema)

