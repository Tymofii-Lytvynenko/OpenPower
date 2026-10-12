"""Authoritative covert-cell lifecycle, mission preparation, and resolution."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

import polars as pl

from modules.base.schema import TABLE_KEYS
from modules.base.systems.military.capability_catalog import canonical_role
from modules.base.systems.military.region_travel_time import RegionTravelTime
from modules.base.systems.military.region_route_snapshot import RegionRouteSnapshot
from modules.base.systems.military.authority_policy import player_controls_country
from modules.base.systems.military.covert_policy import (
    SKILL_LEVELS,
    domestic_security_coverage,
    skill_profile,
)
from modules.base.systems.military.movement_access import MovementAccessPolicy
from modules.base.systems.military.route_policy import MilitaryRoutePlanner
from src.shared.actions import (
    ActionCreateCovertCell,
    ActionRetireCovertCell,
    ActionSetCovertCellAssignment,
    ActionStartCovertMission,
    ActionTrainCovertCell,
)
from src.shared.events import (
    DomainGameEvent,
    EventMessageCreated,
    EventNewDay,
    EventRealSecond,
    EventUnitReadinessStarted,
)
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


MISSION_PROFILES = {
    "civilian_espionage": (0.34, 0.22, "civilian"),
    "military_espionage": (0.40, 0.28, "military"),
    "civilian_sabotage": (0.42, 0.38, "civilian"),
    "military_sabotage": (0.46, 0.43, "military"),
    "assassination": (0.65, 0.58, "political"),
    "terrorism": (0.72, 0.72, "political"),
    "coup_attempt": (0.82, 0.68, "political"),
    "framing": (0.58, 0.48, "political"),
}


@dataclass
class EventCovertMissionResolved(DomainGameEvent):
    mission_id: str
    result: str
    discovered: bool
    at_minute: int


class CovertOperationsSystem(ISystem):
    access = SystemAccess(
        reads=frozenset({"countries", "regions", "region_adjacency", "countries_wars", "country_governments", "units", "treaty_effects", "covert_cells", "covert_cell_routes", "covert_missions", "covert_findings", "covert_incidents", "messages", "countries_relations"}),
        writes=frozenset({"countries", "country_governments", "units", "covert_cells", "covert_cell_routes", "covert_missions", "covert_findings", "covert_incidents", "messages", "countries_relations"}),
        handles=frozenset({ActionCreateCovertCell, ActionTrainCovertCell, ActionStartCovertMission, ActionRetireCovertCell, ActionSetCovertCellAssignment}),
        phase=SystemPhase.MILITARY + 3,
    )

    @property
    def id(self) -> str:
        return "base.covert_operations"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.diplomacy", "base.military_programs"]

    def update(self, state: GameState, delta_time: float) -> None:
        required = {"covert_cells", "covert_cell_routes", "covert_missions", "covert_findings", "covert_incidents"}
        if not required.issubset(state.tables):
            return
        cells_frame = state.get_table("covert_cells")
        missions_frame = state.get_table("covert_missions")
        now = int(state.time.total_minutes)
        elapsed_days = sum(
            max(0.0, self._finite(event.game_seconds_passed)) / 86400.0
            for event in state.events
            if isinstance(event, EventRealSecond) and not event.is_paused
        )
        upkeep_boundary = not state.time.is_paused and any(isinstance(event, EventNewDay) for event in state.events)
        has_actions = any(
            isinstance(action, (
                ActionCreateCovertCell,
                ActionTrainCovertCell,
                ActionStartCovertMission,
                ActionSetCovertCellAssignment,
                ActionRetireCovertCell,
            ))
            for action in state.current_actions
        )
        has_cell_motion = self._has_status(cells_frame, ["transit", "transit_blocked"])
        has_training = self._has_status(cells_frame, ["training"]) and (
            elapsed_days > 0.0 or self._has_due_training(cells_frame, now)
        )
        has_preparation = self._has_status(missions_frame, ["preparation"])
        has_due_mission = self._has_due_missions(missions_frame, now)
        has_mobilization = any(isinstance(event, EventUnitReadinessStarted) for event in state.events)
        has_active_upkeep = upkeep_boundary and self._has_status(cells_frame, ["active", "idle"])
        if not (has_actions or has_cell_motion or has_training or has_preparation or has_due_mission or has_mobilization or has_active_upkeep):
            return

        cells = state.get_table("covert_cells").to_dicts()
        routes = state.get_table("covert_cell_routes").to_dicts()
        missions = state.get_table("covert_missions").to_dicts()
        findings_frame = state.get_table("covert_findings")
        findings: list[dict[str, Any]] = []
        incidents = state.get_table("covert_incidents").to_dicts()
        countries = state.tables.get("countries")
        country_rows = [] if countries is None else countries.to_dicts()
        original_country_rows = [dict(row) for row in country_rows]
        governments_frame = state.tables.get("country_governments")
        governments = [] if governments_frame is None else governments_frame.to_dicts()
        original_governments = [dict(row) for row in governments]
        relations = state.tables.get("countries_relations")
        relation_rows = [] if relations is None else relations.to_dicts()
        original_relation_rows = [dict(row) for row in relation_rows]
        # Scope the lazy index to this update so later ticks see map changes and
        # idle updates do not scan regions merely to populate a cache.
        travel_time = RegionTravelTime(state.tables.get("regions"))
        routing = RegionRouteSnapshot(state.tables.get("regions"), state.tables.get("region_adjacency"))
        for action in state.current_actions:
            if isinstance(action, ActionCreateCovertCell):
                cells = self._create_cell(state, cells, country_rows, routes, action, travel_time, routing)
            elif isinstance(action, ActionTrainCovertCell):
                self._train_cell(state, cells, country_rows, action)
            elif isinstance(action, ActionStartCovertMission):
                missions = self._start_mission(state, cells, country_rows, missions, action)
            elif isinstance(action, ActionSetCovertCellAssignment):
                self._set_assignment(state, cells, action)
            elif isinstance(action, ActionRetireCovertCell):
                self._retire_cell(state, cells, action)

        changed_countries = False
        country_by_id = {self._tag(row.get("id")): row for row in country_rows}
        cell_by_id = {str(row.get("id")): row for row in cells}
        self._record_mobilization_signals(state, cells, country_by_id, findings, now)
        for cell in cells:
            if cell.get("status") in {"transit", "transit_blocked"}:
                self._advance_cell_transit(state, cell, routes, now, travel_time, routing)
            elif cell.get("status") == "training":
                self._advance_training(state, cell, elapsed_days)
            owner = self._tag(cell.get("country_id"))
            if upkeep_boundary and cell.get("status") in {"active", "idle"} and owner in country_by_id:
                upkeep = max(0.0, self._finite(cell.get("upkeep")))
                balance = self._finite(country_by_id[owner].get("money_reserves"))
                if upkeep and balance >= upkeep:
                    country_by_id[owner]["money_reserves"] = balance - upkeep
                    changed_countries = True
                elif upkeep:
                    cell["status"] = "dormant"
                    cell["last_known_status"] = "dormant: upkeep unpaid"

        security_cell_counts = None
        espionage_cell_counts = None
        population_by_country = None
        if any(
            mission.get("status") == "executing"
            and now >= int(mission.get("resolves_at_minute") or 0)
            for mission in missions
        ):
            # Build mission coverage counts once in Polars instead of rescanning
            # the complete covert-cell roster for every resolving mission.
            cell_frame = pl.DataFrame(cells, schema=state.get_table("covert_cells").schema)
            security_cell_counts, espionage_cell_counts = self._cell_metric_frames(cell_frame)
            population_by_country = self._population_metric_frame(state.tables.get("regions"))

        for mission in missions:
            if mission.get("status") == "cleanup":
                if now >= int(mission.get("cleanup_until_minute") or 0):
                    mission.update(status="resolved", updated_at_minute=now)
                    cleanup_cell = cell_by_id.get(str(mission.get("cell_id")))
                    if cleanup_cell is not None:
                        cleanup_cell["status"] = "captured" if mission.get("result") == "captured" else "active"
                        cleanup_cell["mission_type"] = ""
                continue
            if mission.get("status") not in {"preparation", "executing"}:
                continue
            if mission.get("status") == "preparation":
                cell = cell_by_id.get(str(mission.get("cell_id")))
                target = country_by_id.get(self._tag(mission.get("target_country_id")))
                if cell is None or target is None or cell.get("status") != "preparing":
                    discovered = bool(cell and cell.get("status") == "captured")
                    mission.update(
                        status="cancelled", result="captured" if discovered else "cancelled",
                        discovered_by_target=discovered, updated_at_minute=now,
                    )
                    if discovered:
                        self._publish_messages(state, mission, "captured", True, False)
                    continue
                required_minutes = max(1.0, self._finite(mission.get("preparation_required")))
                elapsed_minutes = max(0, now - int(mission.get("created_at_minute") or 0))
                mission["preparation_progress"] = min(1.0, elapsed_minutes / required_minutes)
                if now < int(mission.get("resolves_at_minute") or 0):
                    continue
                mission.update(
                    status="executing",
                    resolves_at_minute=now + max(1, int(self._finite(state.globals.get("covert_execution_minutes", 1)))),
                )
                continue
            if now < int(mission.get("resolves_at_minute") or 0):
                continue
            cell = cell_by_id.get(str(mission.get("cell_id")))
            target = country_by_id.get(self._tag(mission.get("target_country_id")))
            if cell is None or target is None or cell.get("status") not in {"active", "idle", "preparing"}:
                mission.update(status="cancelled", result="Mission conditions invalid at execution.", updated_at_minute=now)
                continue
            target_regions = state.tables.get("regions")
            target_id = self._tag(target.get("id"))
            if target_regions is not None and not self._has_target_region(target_regions, target_id):
                mission.update(status="cancelled", result="Target access or ownership is no longer valid.", updated_at_minute=now)
                continue
            result, discovered, attributed, confidence, output = self._resolve(
                state,
                cell,
                mission,
                target,
                cells,
                relation_rows,
                security_cell_counts,
                espionage_cell_counts,
                population_by_country,
            )
            mission.update(
                status="cleanup", result=result, discovered_by_target=discovered,
                attributed_to_owner=attributed, confidence=confidence,
                output_json=json.dumps(output, sort_keys=True, separators=(",", ":")), updated_at_minute=now,
                cleanup_until_minute=now + max(1, int(self._finite(state.globals.get("covert_cleanup_minutes", 60)))),
            )
            cell["status"] = "debriefing"
            cell["readiness"] = max(0.0, self._finite(cell.get("readiness")) - 0.2)
            if result in {"success", "partial_success"} or attributed:
                self._apply_mission_effect(
                    state, mission, target, output, governments, relation_rows, attributed,
                    partial=result == "partial_success", outcome=result,
                )
            if result == "success":
                changed_countries = changed_countries or str(mission.get("mission_type", "")).startswith("civilian_sabotage")
            audience = [self._tag(mission.get("owner_country_id"))]
            if discovered:
                audience.append(self._tag(mission.get("target_country_id")))
            incident_id = self._next_id("covert-incident", incidents)
            incidents.append({
                "id": incident_id, "mission_id": mission["id"],
                "audience_country_ids": sorted(set(filter(None, audience))),
                "incident_type": "discovery" if discovered else "operation_result",
                "summary": result if discovered or audience == [self._tag(mission.get("owner_country_id"))] else "Unattributed security incident",
                "created_at_minute": now,
            })
            state.events.append(EventCovertMissionResolved(str(mission["id"]), result, discovered, now))
            self._publish_messages(state, mission, result, discovered, attributed)
            if mission.get("mission_type", "").endswith("espionage") and output and result in {"success", "partial_success"}:
                findings.append({
                    "id": self._next_id("finding", findings_frame.height + len(findings)),
                    "owner_country_id": mission["owner_country_id"],
                    "target_country_id": mission["target_country_id"],
                    "category": "military" if "military" in mission["mission_type"] else "civilian",
                    "value_json": json.dumps(output, sort_keys=True, separators=(",", ":")),
                    "confidence": confidence,
                    "freshness": self._finite(output.get("information_freshness", 1.0)),
                    "discovered_at_minute": now, "expires_at_minute": now + 365 * 24 * 60,
                })

        self._write(state, "covert_cells", cells)
        self._write(state, "covert_cell_routes", routes)
        self._write(state, "covert_missions", missions)
        if findings:
            new_findings = pl.DataFrame(findings, schema=findings_frame.schema)
            combined_findings = pl.concat([findings_frame, new_findings], how="vertical")
            self._write_frame_if_changed(state, "covert_findings", combined_findings)
        self._write(state, "covert_incidents", incidents)
        if countries is not None and country_rows != original_country_rows:
            state.update_table("countries", pl.DataFrame(country_rows, schema=countries.schema))
        if governments_frame is not None and governments != original_governments:
            state.update_table("country_governments", pl.DataFrame(governments, schema=governments_frame.schema))
        if relations is not None and relation_rows != original_relation_rows:
            state.update_table("countries_relations", pl.DataFrame(relation_rows, schema=relations.schema))

    @staticmethod
    def _has_status(frame: pl.DataFrame, statuses: list[str]) -> bool:
        return "status" in frame.columns and not frame.filter(pl.col("status").is_in(statuses)).is_empty()

    @staticmethod
    def _has_due_missions(missions: pl.DataFrame, now: int) -> bool:
        if missions.is_empty() or not {
            "status",
            "cleanup_until_minute",
            "resolves_at_minute",
        }.issubset(missions.columns):
            return False
        status = pl.col("status").cast(pl.Utf8).fill_null("")
        cleanup_due = (status == "cleanup") & (pl.col("cleanup_until_minute").fill_null(0) <= now)
        execution_due = (status == "executing") & (pl.col("resolves_at_minute").fill_null(0) <= now)
        return not missions.filter(cleanup_due | execution_due).is_empty()

    @staticmethod
    def _has_due_training(cells: pl.DataFrame, now: int) -> bool:
        if cells.is_empty() or not {"status", "training_completes_at_minute"}.issubset(cells.columns):
            return False
        status = pl.col("status").cast(pl.Utf8).fill_null("")
        due = (status == "training") & (
            pl.col("training_completes_at_minute").cast(pl.Int64, strict=False).fill_null(0) <= now
        )
        return not cells.filter(due).is_empty()

    def _has_target_region(self, regions: pl.DataFrame, target_id: str) -> bool:
        columns = [column for column in ("owner", "controller") if column in regions.columns]
        if not columns:
            return False
        matches = [
            pl.col(column).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == target_id
            for column in columns
        ]
        return not regions.filter(pl.any_horizontal(matches)).is_empty()

    def _cell_metric_frames(self, cells: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
        normalized = cells.with_columns(
            pl.col("country_id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("_country"),
            pl.col("target_country_id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("_target"),
            pl.col("location_country_id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("_location"),
            pl.col("assignment").cast(pl.Utf8, strict=False).fill_null("").alias("_assignment"),
            pl.col("status").cast(pl.Utf8, strict=False).fill_null("").alias("_status"),
        )
        security = (
            normalized.filter(
                (pl.col("_assignment") == "domestic_security")
                & (pl.col("_status") == "active")
                & (pl.col("_country") == pl.col("_location"))
            )
            .group_by("_country")
            .agg(pl.len().cast(pl.Int64).alias("count"))
            .rename({"_country": "country_id"})
        )
        espionage = (
            normalized.filter(
                (pl.col("_assignment") == "espionage")
                & pl.col("_status").is_in(["active", "preparing"])
            )
            .group_by(["_country", "_target"])
            .agg(pl.len().cast(pl.Int64).alias("count"))
            .rename({"_country": "country_id", "_target": "target_country_id"})
        )
        return security, espionage

    def _metric_count(self, metrics: pl.DataFrame | None, **keys: str) -> int:
        value = self._metric_value(metrics, "count", **keys)
        return int(value or 0)

    def _metric_value(self, metrics: pl.DataFrame | None, value_column: str, **keys: str):
        if metrics is None or metrics.is_empty():
            return 0
        filters = [pl.col(column) == value for column, value in keys.items()]
        matches = metrics.filter(pl.all_horizontal(filters)).get_column(value_column)
        return matches[0] if len(matches) else 0

    def _population_metric_frame(self, regions: pl.DataFrame | None) -> pl.DataFrame:
        population_column = next(
            (column for column in ("population", "total_population") if regions is not None and column in regions.columns),
            None,
        )
        if regions is None or "owner" not in regions.columns or population_column is None:
            return pl.DataFrame(schema={"country_id": pl.Utf8, "population": pl.Float64})
        value = pl.col(population_column).cast(pl.Float64, strict=False)
        return (
            regions.select(
                pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("country_id"),
                pl.when(value.is_finite()).then(value).otherwise(0.0).alias("population"),
            )
            .group_by("country_id")
            .agg(pl.col("population").sum())
        )

    def _record_mobilization_signals(self, state, cells, countries_by_id, findings, now):
        readiness_rank = {"parked": 0, "ready": 1, "fortified": 2}
        readiness_events = [
            event for event in state.events
            if isinstance(event, EventUnitReadinessStarted)
            and readiness_rank.get(str(event.target_status or "").strip().lower(), -1)
            > readiness_rank.get(str(event.from_status or "").strip().lower(), -1)
        ]
        if not readiness_events:
            return

        units_table = state.tables.get("units")
        if units_table is None or units_table.is_empty() or "id" not in units_table.columns:
            return
        unit_ids = sorted({str(event.unit_id or "") for event in readiness_events if str(event.unit_id or "")})
        if not unit_ids:
            return
        matching_units = units_table.filter(pl.col("id").cast(pl.Utf8).is_in(unit_ids))
        units_by_id = {str(row.get("id") or ""): row for row in matching_units.to_dicts()}
        if not units_by_id:
            return

        designs_table = state.tables.get("unit_designs")
        design_ids = sorted({
            str(row.get("design_id") or "")
            for row in units_by_id.values()
            if str(row.get("design_id") or "")
        })
        if designs_table is None or not design_ids or "id" not in designs_table.columns:
            designs_by_id = {}
        else:
            matching_designs = designs_table.filter(pl.col("id").cast(pl.Utf8).is_in(design_ids))
            designs_by_id = {str(row.get("id") or ""): row for row in matching_designs.to_dicts()}

        findings_table = state.tables.get("covert_findings")
        if findings_table is None or findings_table.is_empty() or "id" not in findings_table.columns:
            existing_ids: set[str] = set()
        else:
            mobilization_ids = findings_table.filter(
                pl.col("id").cast(pl.Utf8).str.starts_with("mobilization-")
            ).get_column("id").cast(pl.Utf8).to_list()
            existing_ids = set(mobilization_ids)

        for event in readiness_events:
            from_status = str(event.from_status or "").strip().lower()
            target_status = str(event.target_status or "").strip().lower()
            unit = units_by_id.get(str(event.unit_id or ""))
            if unit is None:
                continue
            target_id = self._tag(unit.get("owner"))
            target = countries_by_id.get(target_id)
            if not target_id or target is None:
                continue
            eligible_cells = [
                cell for cell in cells
                if self._tag(cell.get("country_id")) != target_id
                and self._tag(cell.get("target_country_id")) == target_id
                and self._tag(cell.get("location_country_id")) == target_id
                and str(cell.get("assignment") or "").strip().lower() == "espionage"
                and str(cell.get("status") or "").strip().lower() in {"active", "idle", "preparing"}
                and bool(cell.get("communications_ready", True))
            ]
            if not eligible_cells:
                continue
            eligible_cells.sort(key=lambda cell: (
                -SKILL_LEVELS.index(str(cell.get("skill_level") or "Recruit"))
                if str(cell.get("skill_level") or "Recruit") in SKILL_LEVELS else 0,
                -self._finite(cell.get("readiness")),
                str(cell.get("id") or ""),
            ))
            best_cell = eligible_cells[0]
            observer_id = self._tag(best_cell.get("country_id"))
            observer = countries_by_id.get(observer_id)
            if observer is None:
                continue
            observer_telecom = min(1.0, max(0.0, self._finite(observer.get("budget_telecom_ratio", 0.5))))
            target_telecom = self._target_regional_telecom_capacity(state, best_cell, target)
            target_security = min(
                0.7,
                max(0.0, self._finite(target.get("security_upkeep")) / max(1.0, self._finite(target.get("gdp")) * 0.02)),
            )
            domestic_security_count = sum(
                1 for cell in cells
                if self._tag(cell.get("country_id")) == target_id
                and str(cell.get("assignment") or "") == "domestic_security"
                and str(cell.get("status") or "") == "active"
                and self._tag(cell.get("location_country_id")) == target_id
            )
            domestic_coverage = domestic_security_coverage(
                domestic_security_count,
                self._country_population(state, target_id),
                state.globals,
            )
            skill_index = SKILL_LEVELS.index(str(best_cell.get("skill_level") or "Recruit"))
            signal_coverage = 1.0 - (0.72 ** len(eligible_cells))
            detection_probability = min(0.92, max(
                0.02,
                0.18 + skill_index * 0.10
                + min(1.0, max(0.0, self._finite(best_cell.get("readiness")))) * 0.10
                + observer_telecom * 0.20
                + signal_coverage * 0.12
                + target_telecom * 0.05
                - target_security * 0.20
                - domestic_coverage * 0.20,
            ))
            transition_identity = f"{event.transition_id}:{observer_id}:{target_id}"
            deterministic_seed = f"{state.determinism.seed}:mobilization:{transition_identity}"
            digest = hashlib.sha256(deterministic_seed.encode("utf-8")).hexdigest()
            detection_roll = int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
            if detection_roll >= detection_probability:
                continue
            confidence = min(0.95, max(
                0.1,
                0.20 + skill_index * 0.12
                + min(1.0, max(0.0, self._finite(best_cell.get("readiness")))) * 0.15
                + observer_telecom * 0.20
                + signal_coverage * 0.15
                + target_telecom * 0.05
                - target_security * 0.10
                - domestic_coverage * 0.10,
            ))
            observation_id = "mobilization-" + hashlib.sha256(
                f"{deterministic_seed}:finding".encode("utf-8")
            ).hexdigest()[:24]
            if observation_id in existing_ids:
                continue
            design = designs_by_id.get(str(unit.get("design_id") or ""), {})
            domain = str(design.get("domain") or unit.get("unit_domain") or "land").strip().lower()
            confidence_factors = {
                "observer_telecom": observer_telecom,
                "target_telecom": target_telecom,
                "intelligence_coverage": (
                    "limited" if len(eligible_cells) == 1
                    else "sustained" if len(eligible_cells) <= 3 else "dense"
                ),
            }
            output = {
                "signal_type": "mobilization",
                "domain": domain,
                "from_readiness": from_status,
                "to_readiness": target_status,
                "confidence_factors": confidence_factors,
            }
            lifetime = min(
                365 * 24 * 60,
                max(24 * 60, int(self._finite(state.globals.get("covert_mobilization_signal_lifetime_minutes", 30 * 24 * 60)))),
            )
            findings.append({
                "id": observation_id,
                "owner_country_id": observer_id,
                "target_country_id": target_id,
                "category": "military_mobilization",
                "value_json": json.dumps(output, sort_keys=True, separators=(",", ":")),
                "confidence": confidence,
                "freshness": 1.0,
                "discovered_at_minute": now,
                "expires_at_minute": now + lifetime,
            })
            existing_ids.add(observation_id)

    def _create_cell(self, state, cells, countries, routes, action, travel_time: RegionTravelTime, routing: RegionRouteSnapshot):
        owner, target = self._tag(action.country_tag), self._tag(action.target_country_tag)
        if not owner or owner not in {self._tag(row.get("id")) for row in countries} or not self._authorized(state, action.player_id, owner):
            self._reject(state, action, "The issuer cannot create a cell for this country.")
            return cells
        if not target or target not in {self._tag(row.get("id")) for row in countries}:
            self._reject(state, action, "The target country does not exist.")
            return cells
        active_count = sum(1 for row in cells if self._tag(row.get("country_id")) == owner and row.get("status") not in {"retired", "lost"})
        limit = max(1, int(self._finite(state.globals.get("covert_cell_capacity", 8))))
        cost = max(0.0, self._finite(state.globals.get("covert_cell_creation_cost", 10.0)))
        country = next(row for row in countries if self._tag(row.get("id")) == owner)
        if active_count >= limit or self._finite(country.get("money_reserves")) < cost:
            self._reject(state, action, "Cell capacity is full or the country cannot fund recruitment.")
            return cells
        route = None
        origin = target_region = None
        travel_minutes = 0
        if owner != target:
            origin = self._country_home_region(state, owner, routing)
            target_region = self._country_home_region(state, target, routing)
            if origin is None or target_region is None:
                self._reject(state, action, "A valid origin or target deployment region is unavailable.")
                return cells
            route = self._plan_cell_route(state, owner, target, origin, target_region, travel_time, routing)
            if not route.is_valid:
                self._reject(state, action, route.rejection_reason or "No legal covert transit route is available.")
                return cells
            travel_minutes = sum(
                travel_time.estimate_minutes(left, right)
                for left, right in zip(route.region_ids, route.region_ids[1:])
            )
        country["money_reserves"] = self._finite(country.get("money_reserves")) - cost
        transit = owner != target
        base_upkeep = max(0.0, self._finite(state.globals.get("covert_cell_upkeep", 0.25)))
        recruit_profile = skill_profile("Recruit")
        new_id = self._next_id("cell", cells)
        now = int(state.time.total_minutes)
        cells.append({
            "id": new_id, "country_id": owner, "target_country_id": target,
            "cell_name": str(action.cell_name or f"Cell {active_count + 1}"),
            "readiness": 0.5 if not transit else 0.0, "mission_type": "",
            "status": "transit" if transit else "active", "origin_country_id": owner,
            "location_country_id": owner, "assignment": "unassigned", "skill_level": "Recruit",
            "training_target": "", "training_progress": 0.0, "training_required": 0.0,
            "training_completes_at_minute": 0,
            "concealment": recruit_profile.concealment,
            "base_upkeep": base_upkeep,
            "upkeep": base_upkeep * recruit_profile.upkeep_multiplier,
            "communications_ready": True, "available_at_minute": now + travel_minutes,
            "last_known_status": "in transit" if transit else "recruited",
        })
        if transit and route is not None and origin is not None and target_region is not None:
            first_leg_minutes = travel_time.estimate_minutes(route.region_ids[0], route.region_ids[1])
            routes.append({
                "cell_id": new_id, "owner_country_id": owner,
                "source_region_id": int(origin.get("id") or 0),
                "destination_region_id": int(target_region.get("id") or 0),
                "route_region_ids": list(route.region_ids), "route_index": 0,
                "arrival_at_minute": now + first_leg_minutes,
                "status": "in_transit", "rejection_reason": "", "updated_at_minute": now,
            })
        return cells

    def _advance_cell_transit(self, state, cell, routes, now, travel_time: RegionTravelTime, routing: RegionRouteSnapshot):
        cell_id = str(cell.get("id") or "")
        route = next((row for row in routes if str(row.get("cell_id") or "") == cell_id), None)
        if route is None:
            # Legacy saves used a single configured transit deadline and have no route record.
            if now >= int(cell.get("available_at_minute") or 0):
                self._arrive_cell(cell, now)
            return
        if now < int(route.get("arrival_at_minute") or 0):
            return
        regions = state.tables.get("regions")
        if regions is None:
            self._block_cell_transit(cell, route, "The region map is unavailable.", now)
            return
        route_ids = [int(value) for value in route.get("route_region_ids") or []]
        route_index = max(0, int(route.get("route_index") or 0))
        current_region_id = route_ids[route_index] if route_index < len(route_ids) else 0
        destination_id = int(route.get("destination_region_id") or 0)
        owner = self._tag(cell.get("country_id"))
        target = self._tag(cell.get("target_country_id"))
        planner = MilitaryRoutePlanner()
        access = MovementAccessPolicy()
        access_context = access.for_country(state, owner)
        if current_region_id <= 0 or destination_id <= 0:
            self._block_cell_transit(cell, route, "The current or destination region is invalid.", now)
            return
        if current_region_id == destination_id:
            route.update(status="arrived", rejection_reason="", updated_at_minute=now)
            self._arrive_cell(cell, now)
            return

        if str(route.get("status") or "") == "blocked":
            plan = self._plan_cell_route_from_region(state, planner, access, owner, target, current_region_id, destination_id, routing, travel_time)
            if not plan.is_valid or len(plan.region_ids) < 2:
                self._block_cell_transit(cell, route, plan.rejection_reason or "No legal route remains for the cell.", now)
                return
            route.update(
                route_region_ids=list(plan.region_ids), route_index=0,
                arrival_at_minute=now + travel_time.estimate_minutes(plan.region_ids[0], plan.region_ids[1]),
                status="in_transit", rejection_reason="", updated_at_minute=now,
            )
            cell.update(status="transit", communications_ready=True, last_known_status="in transit")
            return

        due_at = int(route.get("arrival_at_minute") or 0)
        while now >= due_at:
            next_index = route_index + 1
            if next_index >= len(route_ids):
                self._block_cell_transit(cell, route, "The remaining route is incomplete.", now)
                return
            next_region_id = route_ids[next_index]
            next_region = routing.region_by_id.get(next_region_id)
            final = next_region_id == destination_id
            if next_region is None or not self._cell_region_access(access_context, owner, target, next_region, final):
                plan = self._plan_cell_route_from_region(state, planner, access, owner, target, current_region_id, destination_id, routing, travel_time)
                if not plan.is_valid or len(plan.region_ids) < 2:
                    self._block_cell_transit(cell, route, plan.rejection_reason or "The next route segment lost access rights.", now)
                    return
                route.update(
                    route_region_ids=list(plan.region_ids), route_index=0,
                    arrival_at_minute=now + travel_time.estimate_minutes(plan.region_ids[0], plan.region_ids[1]),
                    status="in_transit", rejection_reason="", updated_at_minute=now,
                )
                return
            route_index = next_index
            current_region_id = next_region_id
            if final:
                route.update(route_index=route_index, status="arrived", rejection_reason="", updated_at_minute=now)
                self._arrive_cell(cell, now)
                return
            next_next_id = route_ids[route_index + 1] if route_index + 1 < len(route_ids) else destination_id
            due_at += travel_time.estimate_minutes(current_region_id, next_next_id)
            route.update(route_index=route_index, arrival_at_minute=due_at, updated_at_minute=now)

    def _plan_cell_route_from_region(self, state, planner, access, owner, target, source_id, destination_id, routing: RegionRouteSnapshot, travel_time: RegionTravelTime):
        access_context = access.for_country(state, owner)
        prepared_graph = routing.prepared_graph
        travel_time.use_edge_distance_index(prepared_graph.edge_distance_km)
        return planner.plan(
            source_id, destination_id, prepared_graph.region_by_id.values(), None,
            lambda region, final: self._cell_region_access(access_context, owner, target, region, final),
            segment_cost=lambda left, right: travel_time.estimate_minutes(int(left.get("id") or 0), int(right.get("id") or 0)),
            prepared_graph=prepared_graph,
        )

    def _plan_cell_route(self, state, owner, target, origin, destination, travel_time: RegionTravelTime, routing: RegionRouteSnapshot):
        return self._plan_cell_route_from_region(
            state, MilitaryRoutePlanner(), MovementAccessPolicy(), owner, target,
            int(origin.get("id") or 0), int(destination.get("id") or 0),
            routing, travel_time,
        )

    def _cell_region_access(self, access_context, owner, target, region, final):
        if final and self._tag(region.get("owner")) == target:
            return True
        return access_context.can_station(region) if final else access_context.can_transit(region)

    def _country_home_region(self, state, country, routing: RegionRouteSnapshot):
        regions = state.tables.get("regions")
        if regions is None or regions.is_empty() or "owner" not in regions.columns:
            return None
        governments = state.tables.get("country_governments")
        government = next((row for row in governments.to_dicts() if self._tag(row.get("country_id")) == country), None) if governments is not None else None
        capital = int(government.get("capital_region_id") or 0) if government else 0
        return routing.home_region(country, capital)

    def _block_cell_transit(self, cell, route, reason, now):
        route.update(status="blocked", rejection_reason=reason, updated_at_minute=now)
        cell.update(status="transit_blocked", communications_ready=False, last_known_status=f"transit blocked: {reason}")

    def _arrive_cell(self, cell, now):
        cell.update(
            location_country_id=str(cell.get("target_country_id") or ""),
            status="active", communications_ready=True, available_at_minute=now,
            last_known_status="active",
        )

    def _train_cell(self, state, cells, countries, action):
        cell = next((row for row in cells if str(row.get("id")) == str(action.cell_id)), None)
        if cell is None or cell.get("status") not in {"active", "idle"} or not self._authorized(state, action.player_id, self._tag(cell.get("country_id"))):
            self._reject(state, action, "The cell is missing, unavailable, or outside the issuer's authority.")
            return
        level = str(cell.get("skill_level") or "Recruit")
        if level not in SKILL_LEVELS or level == SKILL_LEVELS[-1]:
            self._reject(state, action, "The cell is already at maximum skill or has an invalid skill state.")
            return
        points = max(0.0, min(100.0, self._finite(action.training_points)))
        if points <= 0.0:
            self._reject(state, action, "Training must allocate a positive number of points.")
            return
        next_level = SKILL_LEVELS[SKILL_LEVELS.index(level) + 1]
        configured = state.globals.get("covert_training_points_per_level", 100.0)
        required = max(1.0, self._finite(configured))
        cost = points * max(0.0, self._finite(state.globals.get("covert_training_cost_per_point", 0.1)))
        owner = self._tag(cell.get("country_id"))
        country = next((row for row in countries if self._tag(row.get("id")) == owner), None)
        if country is None or self._finite(country.get("money_reserves")) < cost:
            self._reject(state, action, "The owner cannot fund this training allocation.")
            return
        country["money_reserves"] = self._finite(country.get("money_reserves")) - cost
        cell["status"] = "training"
        cell["training_target"] = next_level
        cell["training_required"] = required
        cell["training_progress"] = min(required, self._finite(cell.get("training_progress")) + points)
        duration = max(1, int(self._finite(state.globals.get("covert_training_minutes_per_level", 1440))))
        cell["training_completes_at_minute"] = int(state.time.total_minutes) + duration

    def _advance_training(self, state, cell, elapsed_days):
        daily_points = max(0.0, self._finite(state.globals.get("covert_training_points_per_day", 20.0)))
        cell["training_progress"] = min(
            self._finite(cell.get("training_required")),
            self._finite(cell.get("training_progress")) + daily_points * elapsed_days,
        )
        if (
            int(state.time.total_minutes) >= int(cell.get("training_completes_at_minute") or 0)
            and self._finite(cell.get("training_progress")) >= self._finite(cell.get("training_required"))
        ):
            self._complete_training(cell)

    def _complete_training(self, cell):
        target = str(cell.get("training_target") or "")
        previous_profile = skill_profile(cell.get("skill_level"))
        if target in SKILL_LEVELS:
            cell["skill_level"] = target
        cell.update(status="active", training_target="", training_required=0.0, training_progress=0.0, training_completes_at_minute=0)
        profile = skill_profile(cell.get("skill_level"))
        current_upkeep = max(0.0, self._finite(cell.get("upkeep")))
        base_upkeep = max(0.0, self._finite(cell.get("base_upkeep")))
        if base_upkeep == 0.0 and current_upkeep > 0.0:
            base_upkeep = current_upkeep / max(previous_profile.upkeep_multiplier, 1e-9)
        cell["base_upkeep"] = base_upkeep
        cell["upkeep"] = base_upkeep * profile.upkeep_multiplier
        cell["concealment"] = profile.concealment
        cell["readiness"] = min(1.0, 0.5 + SKILL_LEVELS.index(str(cell.get("skill_level") or "Recruit")) * 0.16)

    def _start_mission(self, state, cells, countries, missions, action):
        cell = next((row for row in cells if str(row.get("id")) == str(action.cell_id)), None)
        mission_type = str(action.mission_type or "").strip().lower()
        target_id = self._tag(action.target_country_tag)
        if cell is None or mission_type not in MISSION_PROFILES:
            self._reject(state, action, "The cell or mission type is invalid.")
            return missions
        owner = self._tag(cell.get("country_id"))
        if not self._authorized(state, action.player_id, owner) or cell.get("status") not in {"active", "idle"}:
            self._reject(state, action, "The issuer cannot command this cell or the cell is unavailable.")
            return missions
        if not bool(cell.get("communications_ready", True)) or self._tag(cell.get("location_country_id")) != target_id:
            self._reject(state, action, "The cell has not reached the target or lacks communications.")
            return missions
        if self._tag(cell.get("target_country_id")) != target_id or any(row.get("cell_id") == cell.get("id") and row.get("status") in {"preparation", "executing", "cleanup"} for row in missions):
            self._reject(state, action, "The target does not match the assignment or this cell already has an active mission.")
            return missions
        assignment = str(cell.get("assignment") or "unassigned").strip().lower()
        mission_assignment = "espionage" if mission_type.endswith("espionage") else "sabotage" if mission_type.endswith("sabotage") else "political"
        if assignment not in {"unassigned", mission_assignment}:
            self._reject(state, action, "The cell's active assignment does not support this mission.")
            return missions
        risk = MISSION_PROFILES[mission_type][0]
        profile = skill_profile(cell.get("skill_level"))
        if risk > profile.max_mission_risk:
            self._reject(state, action, "This mission exceeds the cell's current skill capability.")
            return missions
        cost = max(0.0, self._finite(state.globals.get("covert_mission_cost", 2.0)))
        owner_row = next((row for row in countries if self._tag(row.get("id")) == owner), None)
        if owner_row is None or self._finite(owner_row.get("money_reserves")) < cost:
            self._reject(state, action, "The owner cannot fund mission preparation.")
            return missions
        owner_row["money_reserves"] = self._finite(owner_row.get("money_reserves")) - cost
        configured_prep = max(1.0, self._finite(state.globals.get(f"covert_{mission_type}_preparation_minutes", 1440)))
        prep_minutes = max(1, int(math.ceil(configured_prep * profile.preparation_multiplier)))
        new_id = self._next_id("mission", missions)
        cell["status"] = "preparing"
        cell["mission_type"] = mission_type
        cell["assignment"] = mission_assignment
        missions.append({
            "id": new_id, "cell_id": cell["id"], "owner_country_id": owner,
            "target_country_id": target_id, "mission_type": mission_type,
            "status": "preparation", "preparation_progress": 0.0,
            "preparation_required": float(prep_minutes), "created_at_minute": int(state.time.total_minutes),
            "resolves_at_minute": int(state.time.total_minutes) + prep_minutes,
            "cleanup_until_minute": 0,
            "execution_cost": cost, "risk": risk, "result": "", "discovered_by_target": False,
            "attributed_to_owner": False, "confidence": 0.0, "output_json": "{}",
            "updated_at_minute": int(state.time.total_minutes),
        })
        return missions

    def _resolve(
        self,
        state,
        cell,
        mission,
        target,
        all_cells,
        relation_rows,
        security_cell_counts: pl.DataFrame | None = None,
        espionage_cell_counts: pl.DataFrame | None = None,
        population_by_country: pl.DataFrame | None = None,
    ):
        base_risk, base_detection, _ = MISSION_PROFILES[str(mission.get("mission_type"))]
        profile = skill_profile(cell.get("skill_level"))
        skill_index = SKILL_LEVELS.index(str(cell.get("skill_level") or "Recruit"))
        target_security = min(0.7, max(0.0, self._finite(target.get("security_upkeep")) / max(1.0, self._finite(target.get("gdp")) * 0.02)))
        target_id = self._tag(target.get("id"))
        security_cell_count = (
            self._metric_count(security_cell_counts, country_id=target_id)
            if security_cell_counts is not None
            else sum(
                1
                for row in all_cells
                if self._tag(row.get("country_id")) == target_id
                and row.get("assignment") == "domestic_security"
                and row.get("status") == "active"
                and self._tag(row.get("location_country_id")) == target_id
            )
        )
        population = (
            self._metric_value(population_by_country, "population", country_id=target_id)
            if population_by_country is not None
            else self._country_population(state, target_id)
        )
        coverage = domestic_security_coverage(security_cell_count, population, state.globals)
        concealment = min(0.9, max(0.0, self._finite(cell.get("concealment"))))
        relation = self._relation_value(relation_rows, self._tag(mission.get("owner_country_id")), self._tag(target.get("id")))
        scrutiny = max(0.0, -relation) / 100.0 * 0.12
        detection_probability = min(0.92, max(0.02, base_detection + target_security + coverage + scrutiny - concealment * 0.55))
        preparation_quality = min(0.2, self._finite(mission.get("preparation_required")) / 10080.0)
        communications_factor = 1.0 if bool(cell.get("communications_ready", True)) else 0.55
        success_probability = min(0.92, max(0.05, (1.0 - base_risk + profile.success_bonus + concealment * 0.15 + preparation_quality - target_security * 0.4) * communications_factor))
        seed = f"{state.determinism.seed}:{mission['id']}:{mission['resolves_at_minute']}"
        roll = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
        detect_roll = int(hashlib.sha256((seed + ":detection").encode("utf-8")).hexdigest()[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
        discovered = detect_roll < detection_probability
        partial_threshold = min(0.98, success_probability + 0.12)
        result = (
            "captured" if discovered and not roll < partial_threshold and detect_roll < detection_probability * 0.35
            else "success" if roll < success_probability
            else "partial_success" if roll < partial_threshold
            else "failure"
        )
        target_telecom = self._target_regional_telecom_capacity(state, cell, target)
        confidence = min(0.95, max(0.1, (0.35 + skill_index * 0.16 + self._finite(cell.get("readiness")) * 0.15) * communications_factor))
        confidence *= 0.75 + 0.25 * target_telecom
        confidence_factors: dict[str, float] = {}
        if str(mission.get("mission_type") or "") == "military_espionage":
            owner = self._tag(mission.get("owner_country_id"))
            target_id = self._tag(target.get("id"))
            countries = state.tables.get("countries")
            observer_budget = self._table_value_by_key(
                countries, "id", owner, "budget_telecom_ratio", 0.5
            )
            telecom_budget = min(1.0, max(0.0, self._finite(observer_budget)))
            active_coverage = (
                self._metric_count(
                    espionage_cell_counts,
                    country_id=owner,
                    target_country_id=target_id,
                )
                if espionage_cell_counts is not None
                else sum(
                    1 for row in all_cells
                    if self._tag(row.get("country_id")) == owner
                    and self._tag(row.get("target_country_id")) == target_id
                    and str(row.get("assignment") or "") == "espionage"
                    and str(row.get("status") or "") in {"active", "preparing"}
                )
            )
            diminishing_coverage = 1.0 - (0.72 ** active_coverage)
            confidence *= 0.7 + 0.2 * telecom_budget + 0.1 * diminishing_coverage
            confidence = min(0.95, max(0.1, confidence))
            coverage_band = (
                "none" if active_coverage == 0 else "limited" if active_coverage == 1
                else "sustained" if active_coverage <= 3 else "dense"
            )
            confidence_factors = {
                "observer_telecom": telecom_budget,
                "target_telecom": target_telecom,
                "intelligence_coverage": coverage_band,
            }
        output = self._intelligence_snapshot(
            state, target, mission, confidence, confidence_factors, population_by_country,
        ) if result in {"success", "partial_success"} and "espionage" in str(mission.get("mission_type")) else {}
        if output:
            output["information_freshness"] = 0.5 + 0.5 * target_telecom
        return result, discovered, discovered and detect_roll < detection_probability * 0.65, confidence, output

    def _target_regional_telecom_capacity(self, state, cell, target):
        """Use the cell's exact deployed region, falling back to its target capital."""

        region_id = 0
        route_frame = state.tables.get("covert_cell_routes")
        if route_frame is not None and {"cell_id", "destination_region_id", "status"}.issubset(route_frame.columns):
            route_match = route_frame.filter(
                (pl.col("cell_id").cast(pl.Utf8, strict=False).fill_null("") == str(cell.get("id") or ""))
                & pl.col("status").cast(pl.Utf8, strict=False).fill_null("").is_in(["arrived", "in_transit"])
            ).select(pl.col("destination_region_id").cast(pl.Int64, strict=False)).head(1)
            if not route_match.is_empty():
                region_id = int(route_match.item() or 0)
        if region_id <= 0:
            governments = state.tables.get("country_governments")
            if governments is not None and {"country_id", "capital_region_id"}.issubset(governments.columns):
                capital = self._table_value_by_key(
                    governments,
                    "country_id",
                    self._tag(target.get("id")),
                    "capital_region_id",
                    0,
                )
                region_id = int(capital or 0)
        regions = state.tables.get("regions")
        if regions is None or "id" not in regions.columns:
            return 1.0
        column = "telecom_capacity" if "telecom_capacity" in regions.columns else "communications"
        if column not in regions.columns:
            return 1.0
        region_value = None
        if region_id > 0:
            match = regions.filter(
                pl.col("id").cast(pl.Int64, strict=False) == region_id
            ).select(pl.col(column).cast(pl.Float64, strict=False)).head(1)
            if not match.is_empty():
                region_value = match.item()
        if region_value is None:
            target_id = self._tag(target.get("id"))
            ownership_filters = [
                pl.col(name).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == target_id
                for name in ("owner", "controller")
                if name in regions.columns
            ]
            if ownership_filters:
                match = (
                    regions.with_columns(pl.col("id").cast(pl.Int64, strict=False).alias("_region_sort"))
                    .filter(pl.any_horizontal(ownership_filters))
                    .sort("_region_sort")
                    .select(pl.col(column).cast(pl.Float64, strict=False))
                    .head(1)
                )
                if not match.is_empty():
                    region_value = match.item()
        return 1.0 if region_value is None else max(0.0, min(1.0, self._finite(region_value)))

    def _table_value_by_key(self, frame, key_column, key, value_column, default=None):
        if frame is None or not {key_column, value_column}.issubset(frame.columns):
            return default
        matches = frame.filter(
            pl.col(key_column).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase()
            == str(key or "").strip().upper()
        ).select(value_column).head(1)
        return matches.item() if not matches.is_empty() else default

    def _intelligence_snapshot(
        self,
        state,
        target,
        mission,
        confidence,
        confidence_factors=None,
        population_by_country: pl.DataFrame | None = None,
    ):
        category = str(mission.get("mission_type"))
        country = self._tag(target.get("id"))
        if category == "military_espionage":
            units = state.tables.get("units")
            owned = pl.DataFrame()
            if units is not None and "owner" in units.columns:
                owned = units.filter(
                    pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == country
                )
            unit_count = owned.height
            if "readiness_status" in owned.columns:
                ready_count = owned.filter(
                    pl.col("readiness_status").cast(pl.Utf8, strict=False).fill_null("").is_in(["", "ready"])
                ).height
            else:
                ready_count = unit_count

            role_counts: dict[str, int] = {}
            design_table = state.tables.get("unit_designs")
            if unit_count and "design_id" in owned.columns:
                role_units = owned.select(
                    pl.col("design_id").cast(pl.Utf8, strict=False).fill_null("").alias("_design_id"),
                    pl.col("unit_type").cast(pl.Utf8, strict=False).fill_null("").alias("_unit_type")
                    if "unit_type" in owned.columns else pl.lit("").alias("_unit_type"),
                )
                if design_table is not None and {"id", "class_name"}.issubset(design_table.columns):
                    design_roles = (
                        design_table.select(
                            pl.col("id").cast(pl.Utf8, strict=False).fill_null("").alias("_design_id"),
                            pl.col("class_name").cast(pl.Utf8, strict=False).fill_null("").alias("_class_name"),
                        )
                        .unique(subset=["_design_id"], keep="last", maintain_order=True)
                    )
                    role_units = role_units.join(design_roles, on="_design_id", how="left", maintain_order="left")
                    class_name = pl.col("_class_name")
                else:
                    role_units = role_units.with_columns(pl.lit("").alias("_class_name"))
                    class_name = pl.col("_class_name")
                role_units = role_units.with_columns(
                    pl.when(class_name != "")
                    .then(class_name)
                    .when(pl.col("_unit_type") != "")
                    .then(pl.col("_unit_type"))
                    .otherwise(pl.lit("generic_unit"))
                    .alias("_role_name")
                )
                # Canonicalize only the small distinct role vocabulary, then aggregate all units in Polars.
                distinct_roles = role_units.get_column("_role_name").unique().to_list()
                role_lookup = pl.DataFrame({
                    "_role_name": distinct_roles,
                    "_role": [canonical_role(role) for role in distinct_roles],
                })
                grouped_roles = (
                    role_units.join(role_lookup, on="_role_name", how="left")
                    .group_by("_role")
                    .agg(pl.len().alias("count"))
                )
                role_counts = {
                    role: int(count)
                    for role, count in grouped_roles.select("_role", "count").iter_rows()
                }
            tracks = state.tables.get("research_tracks")
            production = state.tables.get("production_orders")
            weapons = state.tables.get("strategic_weapons")
            weapon_quantity = 0
            if weapons is not None and {"country_id", "quantity"}.issubset(weapons.columns):
                quantity = weapons.filter(
                    pl.col("country_id").cast(pl.Utf8, strict=False).fill_null("") == country
                ).select(pl.col("quantity").cast(pl.Int64, strict=False).fill_null(0).sum())
                weapon_quantity = int(quantity.item() or 0)
            return {
                "unit_count_estimate": unit_count,
                "ready_count_estimate": ready_count,
                "unit_role_count_estimates": dict(sorted(role_counts.items())),
                "research_track_count": 0 if tracks is None else tracks.filter(pl.col("country_id") == country).height,
                "active_production_orders": 0 if production is None else production.filter((pl.col("country_id") == country) & pl.col("status").is_in(["queued", "paused"])).height,
                "strategic_weapon_quantity_estimate": weapon_quantity,
                "confidence": confidence,
                "confidence_factors": dict(sorted((confidence_factors or {}).items())),
            }
        governments = state.tables.get("country_governments")
        government_type = self._table_value_by_key(
            governments, "country_id", country, "government_type", "unknown"
        )
        laws = state.tables.get("country_laws")
        law_ids = []
        if laws is not None and {"country_id", "law_id"}.issubset(laws.columns):
            law_ids = [
                str(value or "")
                for value in laws.filter(pl.col("country_id") == country).get_column("law_id").head(10).to_list()
            ]
        regions = state.tables.get("regions")
        population = (
            self._metric_value(population_by_country, "population", country_id=country)
            if population_by_country is not None
            else self._country_population(state, country)
        )
        return {
            "government_estimate": str(government_type or "unknown"),
            "economic_output_estimate": max(0.0, self._finite(target.get("gdp"))),
            "population_estimate": max(0.0, population),
            "budget_research_ratio_estimate": min(1.0, max(0.0, self._finite(target.get("budget_research_ratio")))),
            "law_ids": law_ids,
            "confidence": confidence,
        }

    def _apply_mission_effect(self, state, mission, target, output, governments, relations, attributed, partial=False, outcome="success"):
        kind = str(mission.get("mission_type"))
        scale = 0.5 if partial else 1.0
        if outcome in {"success", "partial_success"} and kind in {"civilian_sabotage", "military_sabotage"}:
            if kind == "civilian_sabotage" and "economic_health" in target:
                target["economic_health"] = max(0.0, min(1.0, self._finite(target.get("economic_health")) - 0.02 * scale))
            if kind == "military_sabotage" and "units" in state.tables:
                units = state.get_table("units")
                if {"id", "owner", "strength"}.issubset(units.columns):
                    target_units = (
                        units.filter(
                            (pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == self._tag(target.get("id")))
                            & (pl.col("strength").cast(pl.Int64, strict=False).fill_null(0) > 0)
                        )
                        .with_columns(pl.col("id").cast(pl.Utf8, strict=False).fill_null("").alias("_sort_id"))
                        .sort("_sort_id")
                        .select("id", pl.col("strength").cast(pl.Int64, strict=False).fill_null(0))
                        .head(1)
                    )
                    if not target_units.is_empty():
                        unit_id = target_units.item(0, "id")
                        strength = int(target_units.item(0, "strength") or 0)
                        loss = max(1, int(round(strength * 0.05 * scale)))
                        updated = units.with_columns(
                            pl.when(pl.col("id") == unit_id)
                            .then(pl.lit(max(0, strength - loss)).cast(units.schema["strength"]))
                            .otherwise(pl.col("strength"))
                            .alias("strength")
                        )
                        self._write_frame_if_changed(state, "units", updated)
        elif outcome in {"success", "partial_success"} and kind in {"assassination", "terrorism", "coup_attempt", "framing"}:
            government = next((row for row in governments if self._tag(row.get("country_id")) == self._tag(target.get("id"))), None)
            if government is not None:
                impact = {"assassination": 0.025, "terrorism": 0.05, "coup_attempt": 0.08, "framing": 0.035}[kind] * scale
                government["election_risk"] = min(1.0, max(0.0, self._finite(government.get("election_risk")) + impact))
                if kind == "coup_attempt":
                    balance = self._finite(government.get("ideology_balance"))
                    government["ideology_balance"] = min(1.0, max(0.0, balance + (0.025 if attributed else -0.015) * scale))
            if kind == "terrorism" and "security_upkeep" in target:
                target["security_upkeep"] = max(0.0, self._finite(target.get("security_upkeep")) + self._finite(target.get("gdp")) * 0.0001 * scale)
        if attributed:
            penalty = {"assassination": 8.0, "terrorism": 12.0, "coup_attempt": 10.0, "framing": 6.0}.get(kind, 3.0)
            self._adjust_relations(relations, self._tag(mission.get("owner_country_id")), self._tag(target.get("id")), -penalty)

    def _publish_messages(self, state, mission, result, discovered, attributed):
        table = state.tables.get("messages")
        if table is None:
            return
        owner = self._tag(mission.get("owner_country_id"))
        target = self._tag(mission.get("target_country_id"))
        title = str(mission.get("mission_type") or "Covert operation").replace("_", " ").title()
        owner_body = f"{title} against {target}: {result}. Attribution: {'confirmed' if attributed else 'unconfirmed'}."
        recipients = [(owner, owner_body)]
        if discovered:
            target_body = f"A covert incident was detected. Attribution: {owner if attributed else 'unknown'}. Details: {title}; outcome: {result}."
            recipients.append((target, target_body))
        additions = []
        for index, (recipient, body) in enumerate(recipients, start=1):
            message_id = self._next_id("covert-message", table.height + index - 1)
            additions.append({
                "id": message_id, "country_id": recipient, "category": "covert",
                "subject": f"{title} {result.replace('_', ' ')}", "body": body,
                "is_read": False, "created_at": str(int(state.time.total_minutes)),
            })
            state.events.append(EventMessageCreated(message_id, recipient, "covert"))
        state.update_table("messages", pl.concat([table, pl.DataFrame(additions, schema=table.schema)], how="vertical"))

    def _country_population(self, state, country):
        regions = state.tables.get("regions")
        if regions is None or not {"owner"}.issubset(regions.columns):
            return 0.0
        population_column = next((name for name in ("population", "total_population") if name in regions.columns), None)
        if population_column is None:
            return 0.0
        value = regions.filter(
            pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == country
        ).select(pl.col(population_column).cast(pl.Float64, strict=False).fill_null(0.0).sum())
        return self._finite(value.item() if not value.is_empty() else 0.0)

    def _relation_value(self, rows, left, right):
        values = [
            self._finite(row.get("value")) for row in rows
            if (self._tag(row.get("source")), self._tag(row.get("target"))) in {(left, right), (right, left)}
        ]
        return sum(values) / len(values) if values else 0.0

    def _adjust_relations(self, rows, left, right, delta):
        if not left or not right:
            return
        pairs = {(left, right), (right, left)}
        touched = set()
        for row in rows:
            pair = (self._tag(row.get("source")), self._tag(row.get("target")))
            if pair in pairs:
                row["value"] = min(100.0, max(-100.0, self._finite(row.get("value")) + delta))
                touched.add(pair)
        template = rows[0] if rows else {"source": "", "target": "", "value": 0.0}
        for source, target in sorted(pairs - touched):
            rows.append({**template, "source": source, "target": target, "value": min(100.0, max(-100.0, delta))})

    def _set_assignment(self, state, cells, action):
        cell = next((row for row in cells if str(row.get("id")) == str(action.cell_id)), None)
        if cell is None or cell.get("status") not in {"active", "idle"} or not self._authorized(state, action.player_id, self._tag(cell.get("country_id"))):
            self._reject(state, action, "The cell is missing, unavailable, or outside the issuer's authority.")
            return
        assignment = str(action.assignment or "unassigned").strip().lower()
        allowed = {"unassigned", "domestic_security", "espionage", "sabotage", "dormant"}
        if assignment not in allowed:
            self._reject(state, action, "The requested cell assignment is not supported.")
            return
        cell["assignment"] = assignment
        if assignment == "dormant":
            cell["status"] = "dormant"
        elif cell.get("status") == "dormant":
            cell["status"] = "active"

    def _retire_cell(self, state, cells, action):
        cell = next((row for row in cells if str(row.get("id")) == str(action.cell_id)), None)
        if cell is None or not self._authorized(state, action.player_id, self._tag(cell.get("country_id"))) or cell.get("status") in {"captured", "lost"}:
            self._reject(state, action, "The cell cannot be retired by this issuer.")
            return
        cell.update(status="retired", assignment="unassigned", mission_type="", last_known_status="retired")

    def _reject(self, state, action, reason):
        state.journal.append_command_result({
            "tick": int(state.globals.get("tick", 0)),
            "player_id": str(action.player_id),
            "action_type": type(action).__name__,
            "status": "rejected",
            "reason": reason,
        })

    def _authorized(self, state, player_id, country):
        return player_controls_country(state, player_id, country)

    def _write(self, state, name, rows):
        frame = state.get_table(name)
        result = pl.DataFrame(rows, schema=frame.schema) if rows else pl.DataFrame(schema=frame.schema)
        self._write_frame_if_changed(state, name, result)

    def _write_frame_if_changed(self, state, name, result):
        current = state.get_table(name)
        if current.equals(result):
            # Unchanged idle-tick snapshots must not look like new state to IPC consumers.
            return
        state.update_table(name, result)

    def _next_id(self, prefix, rows):
        count = rows if isinstance(rows, int) else len(rows)
        return f"{prefix}-{count + 1:08d}"

    def _tag(self, value):
        return str(value or "").strip().upper()

    def _finite(self, value):
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return result if result == result and abs(result) != float("inf") else 0.0
