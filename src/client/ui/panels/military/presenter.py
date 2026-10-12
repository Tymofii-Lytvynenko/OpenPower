from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import polars as pl
from src.core.map.geo import EquirectangularProjection, GeoCoordinate
from src.shared.strategic_profiles import DEFAULT_DEFENSE, PAYLOAD_PROFILES
from modules.base.systems.military.weapons_trade_policy import WeaponsTradePolicy

from src.client.ui.panels.shared.panel_data import (
    as_ratio,
    format_side_names,
    get_country_row,
    normalize_side,
    resolve_country_name,
    resolve_region_name,
    safe_float,
    safe_int,
    safe_text,
)


BATTLE_MODE_LABELS = {
    "positional": "Passive",
    "assault": "Active",
}
_STRATEGIC_GEOGRAPHY = EquirectangularProjection(1.0, 1.0)
BATTLE_STATUS_LABELS = {
    "active": "Active",
    "stalemate": "Stalemate",
    "concluded": "Concluded",
    "inactive": "Inactive",
}


def battle_mode_label(mode: object) -> str:
    """Map canonical simulation mode text to the shared display vocabulary."""

    normalized = str(mode or "").strip().lower()
    return BATTLE_MODE_LABELS.get(normalized, "Unknown")


def battle_status_label(status: object) -> str:
    normalized = str(status or "").strip().lower()
    return BATTLE_STATUS_LABELS.get(normalized, "Unknown")


def battle_balance_estimate_label(balance: object) -> str:
    return f"Balance estimate {safe_float(balance, 0.0) * 100.0:.0f}%"


@dataclass(frozen=True, slots=True)
class ForceBucket:
    label: str
    strength: int
    unit_count: int


@dataclass(frozen=True, slots=True)
class MilitarySummaryViewModel:
    branches: tuple[ForceBucket, ...]
    moving_units: int
    active_wars: int
    covert_cells: int
    strategic_ready: int
    strategic_total: int
    missile_defense_pct: float


@dataclass(frozen=True, slots=True)
class UnitListRow:
    unit_id: str
    owner_name: str
    unit_type: str
    strength: int
    quantity: int
    location: str
    status: str
    progress_pct: float
    route_summary: str = ""


@dataclass(frozen=True, slots=True)
class BattleParticipantView:
    country_id: str
    side: str
    role: str
    unit_count: int
    weighted_strength: float
    readiness: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BattleStatusView:
    battle_id: str
    region_id: int
    status: str
    mode: str
    side_a_countries: tuple[str, ...]
    side_b_countries: tuple[str, ...]
    side_a_strength: float
    side_b_strength: float
    balance: float
    side_a_losses: int
    side_b_losses: int
    round: int
    participants: tuple[BattleParticipantView, ...]
    occupation: dict
    readiness_distribution: dict[str, int] = field(default_factory=dict)
    region_name: str = ""
    started_at_minute: int = 0
    updated_at_minute: int = 0
    concluded_at_minute: int = 0
    victor_side: str = ""

    @property
    def mode_label(self) -> str:
        return battle_mode_label(self.mode)

    @property
    def status_label(self) -> str:
        return battle_status_label(self.status)

    @property
    def outcome_label(self) -> str:
        if str(self.status or "").strip().lower() != "concluded":
            return "Outcome pending"
        if self.victor_side == "SIDE_A":
            winners = ", ".join(self.side_a_countries)
        elif self.victor_side == "SIDE_B":
            winners = ", ".join(self.side_b_countries)
        else:
            return "Draw"
        return f"Victory: {winners}" if winners else "Victory recorded"


class MilitaryPresenter:
    def __init__(self) -> None:
        self._battle_view_cache_key: tuple | None = None
        self._battle_view_cache: dict[str, object] = {}

    def build_summary(self, state, country_tag: str) -> MilitarySummaryViewModel:
        units = self._country_units(state, country_tag)
        buckets = {
            "LAND": {"strength": 0, "unit_count": 0},
            "AIR": {"strength": 0, "unit_count": 0},
            "NAVAL": {"strength": 0, "unit_count": 0},
            "STRATEGIC": {"strength": 0, "unit_count": 0},
        }

        moving_units = 0
        for row in units:
            branch = self._classify_branch(str(row.get("unit_type") or ""))
            buckets[branch]["strength"] += safe_int(row.get("strength"), 0)
            buckets[branch]["unit_count"] += 1
            moving_units += 1 if bool(row.get("is_moving", False)) else 0

        strategic_rows = self.strategic_inventory_for_country(state, country_tag)
        active_wars = len(self.wars_for_country(state, country_tag))
        covert_cells = len(self.covert_cells_for_country(state, country_tag))
        defense_scores = [safe_float(row.get("defense_rating"), 0.0) for row in strategic_rows]
        missile_defense_pct = 100.0 * (sum(defense_scores) / len(defense_scores)) if defense_scores else 0.0

        return MilitarySummaryViewModel(
            branches=tuple(
                ForceBucket(label=label, strength=data["strength"], unit_count=data["unit_count"])
                for label, data in buckets.items()
            ),
            moving_units=moving_units,
            active_wars=active_wars,
            covert_cells=covert_cells,
            strategic_ready=sum(safe_int(row.get("ready"), 0) for row in strategic_rows),
            strategic_total=sum(safe_int(row.get("quantity"), 0) for row in strategic_rows),
            missile_defense_pct=missile_defense_pct,
        )

    def unit_rows(
        self,
        state,
        country_tag: str,
        presentation_total_minutes: float | None = None,
    ) -> list[UnitListRow]:
        rows: list[UnitListRow] = []
        routes = state.tables.get("unit_movement_routes")
        route_by_unit = {
            safe_text(row.get("unit_id"), ""): row
            for row in ([] if routes is None else routes.to_dicts())
        }
        for row in self._country_units(state, country_tag):
            owner_tag = safe_text(row.get("owner"), country_tag)
            lifecycle = safe_text(row.get("unit_lifecycle"), "available").lower()
            readiness = safe_text(row.get("readiness_status"), "ready").lower()
            transitioning = safe_text(row.get("readiness_transition_id"), "") != ""
            if lifecycle == "deployment_queued":
                status, progress_pct = "Deployment queued", 0.0
                location = "Deployment queue"
            elif lifecycle in {"deployment_transit", "in_transit"}:
                status = "Deployment transit"
                progress_pct = max(0.0, min(100.0, safe_float(row.get("movement_progress"), 0.0) * 100.0))
                location = "Off map · in transit"
            elif lifecycle in {"deployment_blocked", "route_blocked"}:
                status, progress_pct = "Deployment blocked", 0.0
                location = "Route requires review"
            elif lifecycle == "training":
                status = "Training"
                progress_pct = max(0.0, min(100.0, safe_float(row.get("training_progress"), 0.0) * 100.0))
                location = "Training facility"
            elif transitioning:
                status = readiness.title()
                progress_pct = max(0.0, min(100.0, safe_float(row.get("readiness_progress"), 0.0) * 100.0))
                location = resolve_region_name(state, safe_int(row.get("current_region_id"), 0))
            elif bool(row.get("is_moving", False)):
                status = "Moving"
                progress = self._movement_progress(row, presentation_total_minutes)
                progress_pct = max(0.0, min(100.0, progress * 100.0))
                location = resolve_region_name(state, safe_int(row.get("current_region_id"), 0))
            else:
                status = readiness.title()
                progress_pct = 100.0 if readiness in {"ready", "fortified"} else 0.0
                location = resolve_region_name(state, safe_int(row.get("current_region_id"), 0))
            rows.append(
                UnitListRow(
                    unit_id=safe_text(row.get("id"), ""),
                    owner_name=resolve_country_name(state, owner_tag),
                    unit_type=self._humanize_unit_type(safe_text(row.get("unit_type"), "army")),
                    strength=safe_int(row.get("strength"), 0),
                    quantity=safe_int(row.get("equipment_quantity"), safe_int(row.get("strength"), 0)),
                    location=location,
                    status=status,
                    progress_pct=progress_pct,
                    route_summary=self._route_summary(
                        state,
                        route_by_unit.get(safe_text(row.get("id"), "")),
                        lifecycle,
                    ),
                )
            )

        return sorted(rows, key=lambda item: (item.status != "Moving", item.location, item.unit_id))

    def _route_summary(self, state, route: dict | None, lifecycle: str = "") -> str:
        if route is None:
            return ""
        status = safe_text(route.get("status"), "").lower()
        if status == "blocked":
            return f"Blocked: {safe_text(route.get('rejection_reason'), 'route needs review')}"
        route_ids = route.get("route_region_ids") or []
        names = [resolve_region_name(state, safe_int(region_id, 0)) for region_id in route_ids]
        destination = resolve_region_name(state, safe_int(route.get("destination_region_id"), 0))
        action = "Landing" if bool(route.get("is_naval_invasion")) else "Move"
        path = " → ".join(names) if names else destination
        if destination and destination not in names:
            path = f"{path} → {destination}" if path else destination
        if lifecycle == "battle_retreating":
            return f"Retreat to battle rear · {destination or path}"
        if lifecycle == "battle_returning":
            action = "Return to capital"
        return f"{action}: {path}" if path else f"{action}: {status or 'route assigned'}"

    def _movement_progress(self, row: dict, presentation_total_minutes: float | None) -> float:
        if presentation_total_minutes is None:
            return safe_float(row.get("movement_progress"), 0.0)

        departed = safe_float(row.get("departed_at_minute"), 0.0)
        arrival = safe_float(row.get("arrival_at_minute"), departed)
        if arrival <= departed:
            return safe_float(row.get("movement_progress"), 0.0)
        return max(
            0.0,
            min(1.0, (presentation_total_minutes - departed) / (arrival - departed)),
        )

    def production_orders_for_country(self, state, country_tag: str) -> list[dict]:
        orders = state.tables.get("production_orders")
        if orders is None or orders.is_empty():
            return []
        if "country_id" not in orders.columns:
            return orders.to_dicts()
        return orders.filter(pl.col("country_id") == country_tag).sort("priority").to_dicts()

    def deployment_orders_for_country(self, state, country_tag: str) -> list[dict]:
        orders = state.tables.get("unit_deployment_orders")
        if orders is None or orders.is_empty():
            return []
        if "country_id" not in orders.columns:
            return orders.to_dicts()
        units = state.tables.get("units")
        units_by_id = {} if units is None else {
            str(row.get("id") or ""): row for row in units.to_dicts()
        }
        rows = orders.filter(pl.col("country_id") == country_tag).to_dicts()
        for row in rows:
            unit = units_by_id.get(str(row.get("unit_id") or ""), {})
            row["unit_type"] = safe_text(unit.get("unit_type"), "unit")
            row["quantity"] = safe_int(unit.get("strength"), safe_int(row.get("quantity"), 0))
            row["origin_name"] = resolve_region_name(state, safe_int(row.get("source_region_id"), 0))
            row["destination_name"] = resolve_region_name(state, safe_int(row.get("destination_region_id"), 0))
        return sorted(rows, key=lambda item: (str(item.get("status") or ""), str(item.get("id") or "")))

    def covert_missions_for_country(self, state, country_tag: str) -> list[dict]:
        table = state.tables.get("covert_missions")
        if table is None or table.is_empty():
            return []
        country = str(country_tag or "").strip().upper()
        rows = []
        for source in table.to_dicts():
            owner = safe_text(source.get("owner_country_id"), "").upper()
            target = safe_text(source.get("target_country_id"), "").upper()
            mine = owner == country
            discovered_target = target == country and bool(source.get("discovered_by_target"))
            if not mine and not discovered_target:
                continue
            row = dict(source)
            if discovered_target and not mine:
                row["cell_id"] = ""
                row["owner_country_id"] = safe_text(source.get("owner_country_id"), "Unknown") if bool(source.get("attributed_to_owner")) else "Unknown"
                row["output_json"] = "{}"
                row["confidence"] = 0.0
            rows.append(row)
        return sorted(rows, key=lambda row: (safe_int(row.get("created_at_minute"), 0), safe_text(row.get("id"), "")), reverse=True)

    def covert_findings_for_country(self, state, country_tag: str) -> list[dict]:
        table = state.tables.get("covert_findings")
        if table is None or table.is_empty():
            return []
        country = str(country_tag or "").strip().upper()
        now = safe_float(state.time.total_minutes, 0.0)
        share_sources = self._military_intelligence_sources(state, country)
        countries = state.tables.get("countries")
        receiver = None if countries is None else next((
            row for row in countries.to_dicts()
            if str(row.get("id") or "").strip().upper() == country
        ), None)
        receiver_telecom = safe_float((receiver or {}).get("budget_telecom_ratio"), 0.5)
        receiver_confidence_limit = min(0.9, max(0.1, 0.35 + 0.55 * receiver_telecom))
        rows = []
        for source in table.to_dicts():
            source_country = safe_text(source.get("owner_country_id"), "").upper()
            owned = source_country == country
            shared = (
                not owned
                and source_country in share_sources
                and safe_text(source.get("category"), "").lower() in {"military", "military_mobilization"}
            )
            if not owned and not shared:
                continue
            row = dict(source)
            row["source_country_id"] = source_country
            if shared:
                row["confidence"] = min(safe_float(source.get("confidence"), 0.0), receiver_confidence_limit)
            discovered = safe_float(row.get("discovered_at_minute"), 0.0)
            expires = safe_float(row.get("expires_at_minute"), discovered)
            row["freshness"] = 0.0 if expires <= discovered else max(0.0, min(1.0, (expires - now) / (expires - discovered)))
            row["information_status"] = "outdated" if now >= expires else "confirmed" if safe_float(row.get("confidence"), 0.0) >= 0.8 else "estimated"
            rows.append(row)
        return sorted(rows, key=lambda row: (safe_int(row.get("discovered_at_minute"), 0), safe_text(row.get("id"), "")), reverse=True)

    def foreign_force_estimates_for_country(self, state, country_tag: str) -> list[dict]:
        """Return the strongest authorized current military observation per target."""

        country = safe_text(country_tag, "").strip().upper()
        if not country:
            return []
        candidates_by_target: dict[str, list[dict]] = {}
        for finding in self.covert_findings_for_country(state, country):
            if safe_text(finding.get("category"), "").strip().lower() != "military":
                continue
            target = safe_text(finding.get("target_country_id"), "").strip().upper()
            if not target:
                continue
            confidence = max(0.0, min(1.0, safe_float(finding.get("confidence"), 0.0)))
            freshness = max(0.0, min(1.0, safe_float(finding.get("freshness"), 0.0)))
            observation_status = safe_text(finding.get("information_status"), "unknown").lower()
            try:
                observation = json.loads(str(finding.get("value_json") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                observation = {}
            if not isinstance(observation, dict):
                observation = {}

            total_range = None
            role_ranges: tuple[tuple[str, int, int], ...] = ()
            if observation_status != "outdated" and "unit_count_estimate" in observation:
                # A captured espionage count is evidence, not an exact live inventory; widen it by the observation's uncertainty.
                total_range = self._estimate_count_range(observation.get("unit_count_estimate"), confidence)
                role_counts = observation.get("unit_role_count_estimates")
                if isinstance(role_counts, dict):
                    role_ranges = tuple(
                        (role, *self._estimate_count_range(role_counts[role], confidence))
                        for role in sorted(role_counts)
                    )
                status = "estimated"
            elif observation_status == "outdated":
                status = "outdated"
            else:
                status = "unknown"

            source_country = safe_text(finding.get("source_country_id"), "").strip().upper()
            observed_at = safe_int(finding.get("discovered_at_minute"), 0)
            candidates_by_target.setdefault(target, []).append({
                "target_country_id": target,
                "target_country_name": resolve_country_name(state, target),
                "source_country_id": source_country,
                "source_type": "owned" if source_country == country else "allied",
                "source_finding_id": safe_text(finding.get("id"), ""),
                "observed_at_minute": observed_at,
                "confidence": confidence,
                "freshness": freshness,
                "source_factors": self._public_intelligence_factors(observation.get("confidence_factors")),
                "status": status,
                "total_count_range": total_range,
                "role_count_ranges": role_ranges,
                "selection_score": confidence * freshness,
            })

        estimates = []
        for target in self._active_war_opponents(state, country) - set(candidates_by_target):
            candidates_by_target[target] = [{
                "target_country_id": target,
                "target_country_name": resolve_country_name(state, target),
                "source_country_id": "",
                "source_type": "none",
                "source_finding_id": "",
                "observed_at_minute": 0,
                "confidence": 0.0,
                "freshness": 0.0,
                "source_factors": {},
                "status": "unknown",
                "total_count_range": None,
                "role_count_ranges": (),
                "selection_score": 0.0,
            }]
        for target in sorted(candidates_by_target):
            candidates = candidates_by_target[target]
            candidates.sort(key=lambda row: (
                -row["selection_score"],
                -row["confidence"],
                -row["observed_at_minute"],
                row["source_country_id"],
                row["source_finding_id"],
            ))
            selected = dict(candidates[0])
            selected.pop("selection_score", None)
            estimates.append(selected)
        return estimates

    def mobilization_signals_for_country(self, state, country_tag: str) -> list[dict]:
        """Return current authorized readiness signals without identifying the observed unit or source cell."""

        country = safe_text(country_tag, "").strip().upper()
        if not country:
            return []
        candidates_by_target_domain: dict[tuple[str, str], list[dict]] = {}
        for finding in self.covert_findings_for_country(state, country):
            if safe_text(finding.get("category"), "").strip().lower() != "military_mobilization":
                continue
            try:
                signal = json.loads(str(finding.get("value_json") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(signal, dict) or signal.get("signal_type") != "mobilization":
                continue
            target = safe_text(finding.get("target_country_id"), "").strip().upper()
            domain = safe_text(signal.get("domain"), "land").strip().lower()
            from_status = safe_text(signal.get("from_readiness"), "").strip().lower()
            to_status = safe_text(signal.get("to_readiness"), "").strip().lower()
            if not target or domain not in {"land", "air", "naval", "strategic"}:
                continue
            if from_status not in {"parked", "ready", "fortified"} or to_status not in {"parked", "ready", "fortified"}:
                continue
            confidence = max(0.0, min(1.0, safe_float(finding.get("confidence"), 0.0)))
            freshness = max(0.0, min(1.0, safe_float(finding.get("freshness"), 0.0)))
            source_country = safe_text(finding.get("source_country_id"), "").strip().upper()
            candidates_by_target_domain.setdefault((target, domain), []).append({
                "target_country_id": target,
                "target_country_name": resolve_country_name(state, target),
                "domain": domain,
                "from_readiness": from_status,
                "to_readiness": to_status,
                "source_country_id": source_country,
                "source_type": "owned" if source_country == country else "allied",
                "observed_at_minute": safe_int(finding.get("discovered_at_minute"), 0),
                "confidence": confidence,
                "freshness": freshness,
                "status": safe_text(finding.get("information_status"), "unknown").lower(),
                "source_factors": self._public_intelligence_factors(signal.get("confidence_factors")),
                "selection_score": confidence * freshness,
                "source_finding_id": safe_text(finding.get("id"), ""),
            })
        results = []
        for key in sorted(candidates_by_target_domain):
            candidates = candidates_by_target_domain[key]
            candidates.sort(key=lambda row: (
                -row["selection_score"],
                -row["confidence"],
                -row["observed_at_minute"],
                row["source_country_id"],
                row["source_finding_id"],
            ))
            selected = dict(candidates[0])
            selected.pop("selection_score", None)
            selected.pop("source_finding_id", None)
            results.append(selected)
        return results

    def _active_war_opponents(self, state, country: str) -> set[str]:
        wars = state.tables.get("countries_wars")
        if wars is None or wars.is_empty():
            return set()
        opponents: set[str] = set()
        for row in wars.to_dicts():
            status = safe_text(row.get("status"), "active").strip().lower()
            if status not in {"", "active", "ongoing"}:
                continue
            side_a = self._country_tag_set(row.get("side_a"))
            side_b = self._country_tag_set(row.get("side_b"))
            if country in side_a:
                opponents.update(side_b)
            if country in side_b:
                opponents.update(side_a)
        opponents.discard(country)
        return opponents

    def _country_tag_set(self, value) -> set[str]:
        if isinstance(value, (list, tuple, set)):
            raw_tags = value
        else:
            try:
                parsed = json.loads(str(value or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = str(value or "").split(",")
            raw_tags = parsed if isinstance(parsed, (list, tuple, set)) else [parsed]
        return {safe_text(tag, "").strip().upper() for tag in raw_tags if safe_text(tag, "").strip()}

    def _public_intelligence_factors(self, factors) -> dict[str, object]:
        if not isinstance(factors, dict):
            return {}
        result: dict[str, object] = {}
        for key in ("observer_telecom", "target_telecom"):
            if key in factors:
                result[key] = max(0.0, min(1.0, safe_float(factors.get(key), 0.0)))
        if "intelligence_coverage" in factors:
            coverage = safe_text(factors.get("intelligence_coverage"), "").lower()
            if coverage in {"none", "limited", "sustained", "dense"}:
                result["intelligence_coverage"] = coverage
        elif "active_target_coverage" in factors:
            coverage = max(0, safe_int(factors.get("active_target_coverage"), 0))
            # Exact deployed cell counts would expose the source network, so share only a coarse confidence factor.
            result["intelligence_coverage"] = (
                "none" if coverage == 0 else "limited" if coverage == 1
                else "sustained" if coverage <= 3 else "dense"
            )
        return result

    def _estimate_count_range(self, value, confidence: float) -> tuple[int, int]:
        count = max(0, safe_int(value, 0))
        uncertainty = max(1, int(math.ceil(count * (1.0 - max(0.0, min(1.0, confidence))))))
        return max(0, count - uncertainty), count + uncertainty

    def _military_intelligence_sources(self, state, receiving_country: str) -> set[str]:
        effects = state.tables.get("treaty_effects")
        if effects is None or effects.is_empty():
            return set()
        sources = set()
        for row in effects.to_dicts():
            if safe_text(row.get("effect"), "") != "military_intelligence_sharing":
                continue
            try:
                peers = json.loads(str(row.get("detail") or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(peers, list) or receiving_country not in {str(peer).strip().upper() for peer in peers}:
                continue
            source = safe_text(row.get("country_id"), "").upper()
            if source and source != receiving_country:
                sources.add(source)
        return sources

    def strategic_orders_for_country(self, state, country_tag: str) -> list[dict]:
        table = state.tables.get("strategic_launch_orders")
        if table is None or table.is_empty():
            return []
        country = str(country_tag or "").strip().upper()
        result = []
        for source in table.to_dicts():
            owner = safe_text(source.get("country_id"), "").upper()
            target = safe_text(source.get("target_country_id"), "").upper()
            mine = owner == country
            target_knows = target == country and (bool(source.get("launch_detected")) or str(source.get("status")) in {"impact", "intercepted", "missed"})
            if not mine and not target_knows:
                continue
            row = dict(source)
            if target_knows and not mine:
                row["country_id"] = owner if bool(source.get("launch_attributed")) else "Unknown"
                row["weapon_id"] = ""
                row["yield_kt"] = 0.0
                row["blast_radius_km"] = 0.0
                row["payload_level"] = 0 if not bool(source.get("launch_attributed")) else row.get("payload_level", 0)
            result.append(row)
        return sorted(result, key=lambda row: (safe_int(row.get("launched_at_minute"), 0), safe_text(row.get("id"), "")), reverse=True)

    def strategic_impacts_for_country(self, state, country_tag: str) -> list[dict]:
        impacts = state.tables.get("strategic_impacts")
        if impacts is None or impacts.is_empty():
            return []
        visible_order_ids = {
            safe_text(row.get("id"), "") for row in self.strategic_orders_for_country(state, country_tag)
        }
        rows = [
            row for row in impacts.to_dicts()
            if safe_text(row.get("launch_order_id"), "") in visible_order_ids
        ]
        return sorted(
            rows,
            key=lambda row: (safe_int(row.get("created_at_minute"), 0), safe_text(row.get("id"), "")),
            reverse=True,
        )

    def missile_defense_for_country(self, state, country_tag: str) -> list[dict]:
        table = state.tables.get("missile_defense_layers")
        if table is None or table.is_empty():
            return []
        return table.filter(pl.col("country_id") == str(country_tag or "").strip().upper()).sort("layer").to_dicts()

    def strategic_authorization_contexts(self, state) -> list[str]:
        contexts = state.globals.get("strategic_authorization_contexts", [])
        if not isinstance(contexts, (list, tuple, set)):
            return []
        return sorted({str(context).strip() for context in contexts if str(context).strip()})

    def strategic_launch_preview(
        self,
        state,
        country_tag: str,
        weapon: dict,
        target_region_id: int | None,
        authorization_context: str = "",
    ) -> dict:
        owner = str(country_tag or "").strip().upper()
        regions = state.tables.get("regions")
        target = None
        if target_region_id is not None and regions is not None and "id" in regions.columns:
            matches = regions.filter(pl.col("id") == int(target_region_id))
            target = None if matches.is_empty() else matches.to_dicts()[0]

        reasons: list[str] = []
        target_country = str((target or {}).get("owner") or "").strip().upper()
        if target is None:
            reasons.append("Select a valid target region.")
        elif not target_country or target_country == owner:
            reasons.append("Select a region owned by another country.")
        if (
            not bool(weapon.get("operational", True))
            or safe_int(weapon.get("ready"), 0) < 1
            or safe_int(weapon.get("quantity"), 0) < 1
        ):
            reasons.append("This weapon is unavailable or not ready.")
        if not bool(weapon.get("research_permitted")):
            reasons.append("Required strategic program and weapon research are incomplete.")
        if safe_text(weapon.get("pending_order_status"), "") == "pending":
            reasons.append("This weapon already has a pending launch order.")

        distance_km = None
        if target is not None and target_country and target_country != owner:
            origin = self._strategic_weapon_origin(state, owner, weapon)
            if origin is None:
                reasons.append("This weapon has no valid controlled origin region.")
            else:
                distance_km = self._strategic_distance_km(origin, target)
                if distance_km > max(0.0, safe_float(weapon.get("range_km"), 0.0)):
                    reasons.append("The target is outside this weapon's operational range.")

        country = get_country_row(state, owner)
        cost = max(0.0, safe_float(weapon.get("launch_cost"), 0.0))
        if safe_float(country.get("money_reserves"), 0.0) < cost:
            reasons.append("The country cannot fund this launch cost.")

        authorization = self._strategic_authorization_preview(
            state, owner, target_country, authorization_context,
        )
        if not authorization["authorized"]:
            reasons.append(authorization["reason"])
        flight_minutes = safe_int(weapon.get("flight_minutes"), 0)
        if flight_minutes <= 0:
            flight_minutes = safe_int(state.globals.get("strategic_flight_minutes"), 60)
        return {
            "can_launch": not reasons,
            "reasons": reasons,
            "target_country_id": target_country,
            "distance_km": distance_km,
            "authorization": authorization["label"],
            "flight_minutes": max(1, flight_minutes),
        }

    def strategic_defense_estimate_for_region(self, state, country_tag: str, region_id: int) -> dict:
        regions = state.tables.get("regions")
        if regions is None or "id" not in regions.columns:
            return {"target_region_id": int(region_id), "covered_layers": [], "interception_probability": 0.0}
        target_frame = regions.filter(pl.col("id") == int(region_id))
        if target_frame.is_empty():
            return {"target_region_id": int(region_id), "covered_layers": [], "interception_probability": 0.0}
        target = target_frame.to_dicts()[0]
        country = str(country_tag or "").strip().upper()
        tracks = state.tables.get("research_tracks")
        levels = {} if tracks is None else {
            str(row.get("branch") or "").strip().lower(): safe_int(row.get("research_level"), 0)
            for row in tracks.filter(pl.col("country_id") == country).to_dicts()
        }
        required = max(1, safe_int(state.globals.get("strategic_defense_research_level"), 1))
        configured_order = state.globals.get("missile_defense_layer_order", ["long_range", "short_range"])
        layer_order = {str(layer): index for index, layer in enumerate(configured_order)} if isinstance(configured_order, (list, tuple)) else {}
        estimates = []
        for defense in self.missile_defense_for_country(state, country):
            layer = str(defense.get("layer") or "")
            defaults = DEFAULT_DEFENSE.get(layer)
            if defaults is None:
                continue
            researched = (
                bool(defense.get("researched"))
                and tracks is not None
                and levels.get("strategic_program", 0) >= required
                and levels.get("strategic_defense", 0) >= required
            )
            operational = bool(defense.get("operational"))
            readiness = min(1.0, max(0.0, safe_float(defense.get("readiness"), 0.0)))
            covered = self._strategic_defense_covers_region(state, defense, target)
            active = researched and operational and readiness > 0.0 and covered
            first = min(1.0, max(0.0, safe_float(defense.get("first_attempt_probability"), defaults[0]))) * readiness if active else 0.0
            second_default = defaults[1]
            second = min(1.0, max(0.0, safe_float(defense.get("second_attempt_probability"), second_default))) * readiness if active else 0.0
            layer_probability = first + (1.0 - first) * second
            estimates.append({
                **defense,
                "covered": covered,
                "researched_and_operational": active,
                "effective_first_attempt_probability": first,
                "effective_second_attempt_probability": second,
                "layer_interception_probability": layer_probability,
            })
        estimates.sort(key=lambda row: (layer_order.get(str(row.get("layer") or ""), 99), safe_text(row.get("id"), "")))
        surviving_probability = 1.0
        for row in estimates:
            surviving_probability *= 1.0 - safe_float(row.get("layer_interception_probability"), 0.0)
        return {
            "target_region_id": int(region_id),
            "covered_layers": estimates,
            "interception_probability": 1.0 - surviving_probability,
        }

    def _strategic_authorization_preview(self, state, owner: str, target: str, context: str) -> dict:
        policy = safe_text(state.globals.get("strategic_authorization_policy"), "war_or_explicit")
        if policy == "open":
            return {"authorized": True, "label": "authorized by open policy", "reason": ""}
        approved = state.globals.get("strategic_authorized_countries", [])
        if isinstance(approved, (list, tuple, set)) and owner in {str(item).strip().upper() for item in approved}:
            return {"authorized": True, "label": "authorized by scenario policy", "reason": ""}
        contexts = self.strategic_authorization_contexts(state)
        if context and context in contexts:
            return {"authorized": True, "label": f"authorized by {context}", "reason": ""}
        if context and policy in {"explicit", "war_or_explicit"}:
            return {"authorized": False, "label": "not authorized", "reason": "The selected authorization context is not permitted."}
        if self._strategic_countries_at_war(state, owner, target):
            return {"authorized": True, "label": "authorized by active war", "reason": ""}
        if contexts:
            return {"authorized": False, "label": "authorization context required", "reason": "Select a configured launch authorization context."}
        return {"authorized": False, "label": "not authorized", "reason": "Political launch authorization is missing."}

    def _strategic_countries_at_war(self, state, owner: str, target: str) -> bool:
        wars = state.tables.get("countries_wars")
        if wars is None:
            return False
        for row in wars.to_dicts():
            if safe_text(row.get("status"), "active").lower() in {"ended", "inactive", "peace"}:
                continue
            participants = set()
            for key in ("side_a", "side_b"):
                side = row.get(key) or []
                participants.update(str(item).strip().upper() for item in side)
            participants.update(
                str(row.get(key) or "").strip().upper()
                for key in ("attacker", "defender", "source_country", "target_country", "country_a", "country_b")
            )
            if owner in participants and target in participants:
                return True
        return False

    def _strategic_weapon_origin(self, state, owner: str, weapon: dict) -> dict | None:
        regions = state.tables.get("regions")
        if regions is None or not {"id", "owner"}.issubset(regions.columns):
            return None
        by_id = {safe_int(row.get("id"), 0): row for row in regions.to_dicts()}
        origin_id = safe_int(weapon.get("origin_region_id"), 0)
        origin = by_id.get(origin_id)
        if origin is not None:
            return origin if safe_text(origin.get("owner"), "").upper() == owner else None
        governments = state.tables.get("country_governments")
        if governments is not None:
            for government in governments.to_dicts():
                if safe_text(government.get("country_id"), "").upper() != owner:
                    continue
                capital = by_id.get(safe_int(government.get("capital_region_id"), 0))
                if capital is not None and safe_text(capital.get("owner"), "").upper() == owner:
                    return capital
        candidates = [row for row in by_id.values() if safe_text(row.get("owner"), "").upper() == owner]
        return min(candidates, key=lambda row: safe_int(row.get("id"), 0)) if candidates else None

    def _strategic_defense_covers_region(self, state, defense: dict, target: dict) -> bool:
        target_id = safe_int(target.get("id"), 0)
        listed = defense.get("coverage_region_ids") or []
        explicit_match = target_id in {safe_int(item, 0) for item in listed}
        center_latitude = defense.get("center_latitude")
        center_longitude = defense.get("center_longitude")
        if center_latitude is None or center_longitude is None:
            origin = self._strategic_weapon_origin(state, safe_text(defense.get("country_id"), "").upper(), {"origin_region_id": 0})
            center_latitude = None if origin is None else origin.get("latitude")
            center_longitude = None if origin is None else origin.get("longitude")
        if center_latitude is None or center_longitude is None:
            return explicit_match
        distance = self._strategic_distance_km(
            {"latitude": center_latitude, "longitude": center_longitude}, target,
        )
        range_km = max(0.0, safe_float(defense.get("range_km"), 0.0))
        if range_km > 0.0 and distance > range_km:
            return False
        radius = max(0.0, safe_float(defense.get("coverage_radius_km"), 0.0))
        if radius > 0.0 and distance > radius:
            return explicit_match and (range_km <= 0.0 or distance <= range_km)
        return explicit_match or radius > 0.0 or range_km > 0.0

    def _strategic_distance_km(self, left: dict, right: dict) -> float:
        return _STRATEGIC_GEOGRAPHY.geo_distance_km(
            GeoCoordinate(safe_float(left.get("latitude"), 0.0), safe_float(left.get("longitude"), 0.0)),
            GeoCoordinate(safe_float(right.get("latitude"), 0.0), safe_float(right.get("longitude"), 0.0)),
        )

    def strategic_payload_profiles(self, state) -> dict[int, tuple[float, float]]:
        result = dict(PAYLOAD_PROFILES)
        overrides = state.globals.get("strategic_payload_profiles", {})
        if not isinstance(overrides, dict):
            return result
        for key, profile in overrides.items():
            if not isinstance(profile, dict):
                continue
            try:
                level = int(key)
                yield_kt = max(0.0, float(profile.get("yield_kt", result[level][0])))
                radius = max(0.0, float(profile.get("blast_radius_km", result[level][1])))
            except (TypeError, ValueError, OverflowError, KeyError):
                continue
            if level in result:
                result[level] = (yield_kt, radius)
        return result

    def battle_force_summary(self, state, battle_id: str, viewer_country_tag: str) -> list[dict]:
        if not self._battle_visible_to_country(state, battle_id, viewer_country_tag):
            return []
        participants = state.tables.get("battle_units")
        units = state.tables.get("units")
        if participants is None or units is None or participants.is_empty() or units.is_empty():
            return []
        unit_by_id = {safe_text(row.get("id"), ""): row for row in units.to_dicts()}
        grouped: dict[tuple[str, str, str], dict] = {}
        for participant in participants.filter(pl.col("battle_id") == str(battle_id)).to_dicts():
            unit = unit_by_id.get(safe_text(participant.get("unit_id"), ""))
            if unit is None:
                continue
            key = (
                safe_text(participant.get("side"), "unknown").upper(),
                safe_text(participant.get("country_id"), "").upper(),
                safe_text(unit.get("unit_type"), "unit").lower().replace(" ", "_"),
            )
            row = grouped.setdefault(key, {
                "side": key[0], "country_id": key[1], "unit_type": key[2],
                "unit_count": 0, "strength": 0, "relative_positions": [],
            })
            row["unit_count"] += 1
            row["strength"] += max(0, safe_int(unit.get("strength"), 0))
            row["relative_positions"].append((safe_float(unit.get("latitude"), 0.0), safe_float(unit.get("longitude"), 0.0)))
        return [grouped[key] for key in sorted(grouped)]

    def battle_postures_for_country(self, state, battle_id: str, country_tag: str) -> list[dict]:
        if not self._battle_visible_to_country(state, battle_id, country_tag):
            return []
        postures = state.tables.get("battle_force_postures")
        units = state.tables.get("units")
        if postures is None or units is None or postures.is_empty() or units.is_empty():
            return []
        country = str(country_tag or "").strip().upper()
        unit_by_id = {safe_text(row.get("id"), ""): row for row in units.to_dicts()}
        routes = state.tables.get("unit_movement_routes")
        route_by_unit = {} if routes is None else {
            safe_text(row.get("unit_id"), ""): row for row in routes.to_dicts()
        }
        regions = state.tables.get("regions")
        region_names = {} if regions is None else {
            safe_int(row.get("id"), 0): safe_text(row.get("name"), f"Region {safe_int(row.get('id'), 0)}")
            for row in regions.to_dicts()
        }
        rows = []
        for posture in postures.to_dicts():
            if str(posture.get("battle_id") or "") != str(battle_id) or str(posture.get("country_id") or "").strip().upper() != country:
                continue
            unit_id = safe_text(posture.get("unit_id"), "")
            unit = unit_by_id.get(unit_id)
            next_action, next_action_at = self._battle_posture_next_action(
                posture, unit or {}, route_by_unit.get(unit_id, {}), region_names,
            )
            rows.append({
                **posture,
                "unit_type": safe_text((unit or {}).get("unit_type"), "unit"),
                "strength": safe_int((unit or {}).get("strength"), 0),
                "next_action": next_action,
                "next_action_at_minute": next_action_at,
            })
        return sorted(rows, key=lambda row: (safe_int(row.get("effective_at_minute"), 0), safe_text(row.get("unit_id"), "")))

    def _battle_posture_next_action(self, posture, unit, route, region_names):
        strategy = safe_text(posture.get("strategy"), "hold").strip().lower()
        status = safe_text(posture.get("status"), "active").strip().lower()
        if status in {"retreating", "disengaging"}:
            return "Continue withdrawal to the rear position", safe_int(unit.get("arrival_at_minute"), 0)
        if status == "reorganizing":
            if strategy == "retreat":
                return "Finish regrouping, then return toward the capital", safe_int(posture.get("expires_at_minute"), 0)
            return "Finish reorganization and rejoin the battle", safe_int(posture.get("expires_at_minute"), 0)
        if status == "returning":
            destination = safe_int(route.get("destination_region_id"), 0)
            target = region_names.get(destination, "capital route destination")
            return f"Continue return route toward {target}", safe_int(unit.get("arrival_at_minute"), 0)
        if status == "blocked":
            return "Review the blocked route; the force remains out of assault", 0
        if status in {"completed", "cancelled"}:
            return "No pending transition", 0
        if strategy == "attack":
            return "Continue attack posture at the next battle resolution", 0
        if strategy == "defend":
            return "Hold position and counterattack when eligible", 0
        if strategy == "back_off":
            return "Hold at the rear without initiating an assault", 0
        if strategy == "reorganize":
            return "Finish reorganization and rejoin the battle", safe_int(posture.get("expires_at_minute"), 0)
        return "Hold current position", 0

    def battle_command_history(self, state, battle_id: str, country_tag: str) -> list[dict]:
        if not self._battle_visible_to_country(state, battle_id, country_tag):
            return []
        orders = state.tables.get("battle_command_orders")
        units = state.tables.get("units")
        postures = state.tables.get("battle_force_postures")
        if orders is None or orders.is_empty():
            return []
        country = str(country_tag or "").strip().upper()
        unit_by_id = {} if units is None else {safe_text(row.get("id"), ""): row for row in units.to_dicts()}
        posture_by_id = {} if postures is None else {
            safe_text(row.get("unit_id"), ""): row
            for row in postures.to_dicts()
            if str(row.get("battle_id") or "") == str(battle_id)
            and str(row.get("country_id") or "").strip().upper() == country
        }
        history = []
        for order in orders.to_dicts():
            if str(order.get("battle_id") or "") != str(battle_id) or str(order.get("country_id") or "").strip().upper() != country:
                continue
            affected = []
            expected = []
            for unit_id in order.get("affected_unit_ids") or []:
                unit_id = str(unit_id)
                unit = unit_by_id.get(unit_id, {})
                if str(unit.get("owner") or "").strip().upper() != country:
                    continue
                affected.append({"unit_id": unit_id, "unit_type": safe_text(unit.get("unit_type"), "unit")})
                posture = posture_by_id.get(unit_id)
                if posture is not None:
                    expected.append({
                        "unit_id": unit_id,
                        "attack_modifier": safe_float(posture.get("attack_modifier"), 1.0),
                        "defense_modifier": safe_float(posture.get("defense_modifier"), 1.0),
                        "casualty_modifier": safe_float(posture.get("casualty_modifier"), 1.0),
                        "attack_risk_modifier": safe_float(posture.get("attack_risk_modifier"), 1.0),
                        "readiness_modifier": safe_float(posture.get("readiness_modifier"), 1.0),
                        "holding_modifier": safe_float(posture.get("holding_modifier"), 1.0),
                        "counterattack_modifier": safe_float(posture.get("counterattack_modifier"), 1.0),
                    })
            history.append({**order, "affected_forces": affected, "expected_effects": expected})
        return sorted(
            history,
            key=lambda row: (safe_int(row.get("created_at_minute"), 0), safe_text(row.get("id"), "")),
            reverse=True,
        )[:10]

    def battle_loss_summary(self, state, battle_id: str, viewer_country_tag: str) -> list[dict]:
        if not self._battle_visible_to_country(state, battle_id, viewer_country_tag):
            return []
        records = state.tables.get("battle_casualty_records")
        if records is None or records.is_empty():
            return []
        grouped: dict[tuple[str, str, str], int] = {}
        for row in records.filter(pl.col("battle_id") == str(battle_id)).to_dicts():
            key = (
                safe_text(row.get("side"), "unknown").upper(),
                safe_text(row.get("country_id"), "").upper(),
                safe_text(row.get("unit_type"), "unit").lower().replace(" ", "_"),
            )
            grouped[key] = grouped.get(key, 0) + max(0, safe_int(row.get("losses"), 0))
        return [
            {"side": key[0], "country_id": key[1], "unit_type": key[2], "losses": grouped[key]}
            for key in sorted(grouped)
        ]

    def designs_for_country(self, state, country_tag: str) -> list[dict]:
        designs = state.tables.get("unit_designs")
        if designs is None or designs.is_empty():
            return []
        if "country_id" not in designs.columns:
            return designs.to_dicts()
        return designs.filter(pl.col("country_id") == country_tag).sort(["branch", "display_name"]).to_dicts()

    def foreign_designs_for_country(self, state, buyer_country_tag: str) -> list[dict]:
        designs = state.tables.get("unit_designs")
        if designs is None or designs.is_empty():
            return []
        buyer = str(buyer_country_tag or "").strip().upper()
        effects = state.tables.get("treaty_effects")
        permissions = state.globals.get("foreign_order_permissions", [])
        permitted_pairs = {
            (str(pair[0]).strip().upper(), str(pair[1]).strip().upper())
            for pair in permissions
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        } if isinstance(permissions, list) else set()
        profiles = state.tables.get("seller_acceptance_profiles")
        accepting = set() if profiles is None else {
            str(row.get("country_id") or "").strip().upper()
            for row in profiles.to_dicts() if bool(row.get("accepts_foreign_orders"))
        }
        trade = WeaponsTradePolicy()
        result = []
        for row in designs.to_dicts():
            seller = str(row.get("country_id") or "").strip().upper()
            if not seller or seller == buyer or not trade.can_order(effects, buyer, seller, "open"):
                continue
            if (buyer, seller) not in permitted_pairs and not trade.can_order(effects, buyer, seller, "treaty"):
                continue
            item = dict(row)
            item["seller_accepts_orders"] = seller in accepting
            item["seller_name"] = resolve_country_name(state, seller)
            result.append(item)
        return sorted(result, key=lambda item: (str(item.get("seller_name") or ""), str(item.get("display_name") or ""), str(item.get("id") or "")))

    def foreign_orders_for_country(self, state, country_tag: str) -> list[dict]:
        orders = state.tables.get("foreign_unit_orders")
        if orders is None or orders.is_empty():
            return []
        country = str(country_tag or "").strip().upper()
        designs = state.tables.get("unit_designs")
        design_names = {} if designs is None else {
            str(row.get("id") or ""): safe_text(row.get("display_name"), str(row.get("id") or "Design"))
            for row in designs.to_dicts()
        }
        rows = [
            dict(row, design_name=design_names.get(str(row.get("design_id") or ""), str(row.get("design_id") or "Design")))
            for row in orders.to_dicts()
            if country in {
                str(row.get("buyer_country_id") or "").strip().upper(),
                str(row.get("seller_country_id") or "").strip().upper(),
            }
        ]
        return sorted(rows, key=lambda row: (safe_int(row.get("created_at_minute"), 0), safe_text(row.get("id"), "")), reverse=True)

    def research_tracks_for_country(self, state, country_tag: str) -> list[dict]:
        tracks = state.tables.get("research_tracks")
        if tracks is None or tracks.is_empty():
            return []
        if "country_id" not in tracks.columns:
            return tracks.to_dicts()
        return tracks.filter(pl.col("country_id") == country_tag).sort("priority").to_dicts()

    def market_listings_for_country(self, state, country_tag: str) -> list[dict]:
        listings = state.tables.get("unit_market_listings")
        if listings is None or listings.is_empty():
            return []
        buyer = str(country_tag or "").strip().upper()
        effects = state.tables.get("treaty_effects")
        permissions = state.globals.get("foreign_order_permissions", [])
        designs_table = state.tables.get("unit_designs")
        designs = {} if designs_table is None else {
            str(row.get("id") or ""): row for row in designs_table.to_dicts()
        }
        trade = WeaponsTradePolicy()
        visible = []
        for source in listings.to_dicts():
            if str(source.get("status") or "listed").lower() != "listed" or safe_int(source.get("quantity"), 0) <= 0:
                continue
            seller = str(source.get("seller_country_id") or "").strip().upper()
            if seller != buyer:
                eligible = trade.can_order(effects, buyer, seller, "open") and (
                    [buyer, seller] in permissions if isinstance(permissions, list)
                    else False
                )
                eligible = eligible or trade.can_order(effects, buyer, seller, "treaty")
                if not eligible:
                    continue
            row = dict(source)
            design = designs.get(row.get("design_id"))
            row["design_name"] = safe_text(
                (design or {}).get("display_name"),
                safe_text(row.get("design_id"), "Unspecified"),
            )
            row["seller_name"] = resolve_country_name(state, seller)
            visible.append(row)
        return sorted(visible, key=lambda row: (safe_int(row.get("created_at_minute"), 0), safe_text(row.get("id"), "")))

    def marketable_units_for_country(self, state, country_tag: str) -> list[dict]:
        units = state.tables.get("units")
        if units is None or units.is_empty() or not {"id", "owner"}.issubset(units.columns):
            return []
        owner = str(country_tag or "").strip().upper()
        listings = state.tables.get("unit_market_listings")
        listed_ids = set() if listings is None else {
            safe_text(row.get("unit_id"), "") for row in listings.to_dicts()
            if str(row.get("status") or "listed").lower() == "listed" and safe_int(row.get("quantity"), 0) > 0
        }
        participants = state.tables.get("battle_units")
        engaged_ids = set() if participants is None else {
            safe_text(row.get("unit_id"), "") for row in participants.to_dicts()
        }
        designs = state.tables.get("unit_designs")
        design_names = {} if designs is None else {
            safe_text(row.get("id"), ""): safe_text(row.get("display_name"), "Unit design")
            for row in designs.to_dicts()
        }
        result = []
        for row in units.to_dicts():
            unit_id = safe_text(row.get("id"), "")
            if (
                str(row.get("owner") or "").strip().upper() != owner
                or safe_int(row.get("strength"), 0) <= 0
                or bool(row.get("is_moving"))
                or safe_text(row.get("unit_lifecycle"), "available") != "available"
                or safe_text(row.get("training_state"), "") == "training"
                or unit_id in listed_ids or unit_id in engaged_ids
            ):
                continue
            item = dict(row)
            item["design_name"] = design_names.get(safe_text(row.get("design_id"), ""), safe_text(row.get("unit_type"), "Unit"))
            result.append(item)
        return sorted(result, key=lambda row: safe_text(row.get("id"), ""))

    def covert_cells_for_country(self, state, country_tag: str) -> list[dict]:
        cells = state.tables.get("covert_cells")
        if cells is None or cells.is_empty():
            return []
        if "country_id" not in cells.columns:
            return cells.to_dicts()
        return cells.filter(pl.col("country_id") == country_tag).to_dicts()

    def all_wars(self, state) -> list[dict]:
        wars = state.tables.get("countries_wars")
        if wars is None or wars.is_empty():
            return []

        rows: list[dict] = []
        for index, row in enumerate(wars.to_dicts(), start=1):
            side_a = normalize_side(row.get("side_a"))
            side_b = normalize_side(row.get("side_b"))
            rows.append(
                {
                    "id": safe_text(row.get("id"), f"war-{index:03d}"),
                    "side_a": side_a,
                    "side_b": side_b,
                    "status": safe_text(row.get("status"), "Active"),
                    "front": f"{format_side_names(state, side_a)} vs {format_side_names(state, side_b)}",
                    "leader_a": safe_text(row.get("leader_a"), side_a[0] if side_a else "UNK"),
                    "leader_b": safe_text(row.get("leader_b"), side_b[0] if side_b else "UNK"),
                    "intent_a": safe_text(row.get("intent_a"), "war"),
                    "intent_b": safe_text(row.get("intent_b"), "war"),
                }
            )

        return rows

    def wars_for_country(self, state, country_tag: str) -> list[dict]:
        wars = state.tables.get("countries_wars")
        if wars is None or wars.is_empty():
            return []

        rows: list[dict] = []
        for index, row in enumerate(wars.to_dicts(), start=1):
            side_a = normalize_side(row.get("side_a"))
            side_b = normalize_side(row.get("side_b"))
            if country_tag not in side_a and country_tag not in side_b:
                continue
            rows.append(
                {
                    "id": safe_text(row.get("id"), f"war-{index:03d}"),
                    "side_a": side_a,
                    "side_b": side_b,
                    "status": safe_text(row.get("status"), "Active"),
                    "front": f"{format_side_names(state, side_a)} vs {format_side_names(state, side_b)}",
                }
            )

        return rows

    def preferred_war_targets(self, state, country_tag: str, limit: int = 12) -> list[dict]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return []

        active_enemies = set()
        for war in self.wars_for_country(state, country_tag):
            active_enemies.update(tag for tag in war["side_a"] if tag != country_tag)
            active_enemies.update(tag for tag in war["side_b"] if tag != country_tag)

        allies = self._allied_countries(state, country_tag)
        rows: list[dict] = []
        relations = state.tables.get("countries_relations")
        if relations is not None and not relations.is_empty() and {"source", "target", "value"}.issubset(set(relations.columns)):
            ranked_rows = (
                relations.filter(pl.col("source") == country_tag)
                .sort("value")
                .to_dicts()
            )
            for row in ranked_rows:
                target_tag = safe_text(row.get("target"))
                if not target_tag or target_tag == country_tag or target_tag in active_enemies or target_tag in allies:
                    continue
                rows.append(
                    {
                        "country_tag": target_tag,
                        "country_name": resolve_country_name(state, target_tag),
                        "relation_score": safe_float(row.get("value")),
                    }
                )
                if len(rows) >= limit:
                    break
            return rows

        for row in countries.to_dicts():
            target_tag = safe_text(row.get("id"))
            if not target_tag or target_tag == country_tag or target_tag in active_enemies or target_tag in allies:
                continue
            rows.append(
                {
                    "country_tag": target_tag,
                    "country_name": resolve_country_name(state, target_tag),
                    "relation_score": 0.0,
                }
            )
        return rows[:limit]

    def battles_for_country(self, state, country_tag: str) -> list[dict]:
        viewer = str(country_tag or "").strip().upper()
        if not viewer:
            return []
        index = self._battle_view_index(state)
        return [
            dict(row) for battle_id, row in index["battles"].items()
            if viewer in index["battle_viewers"].get(battle_id, set())
        ]

    def battle_status(self, state, battle_id: str, viewer_country_tag: str) -> BattleStatusView | None:
        battles = state.tables.get("battles")
        if battles is None or battles.is_empty() or "id" not in battles.columns:
            return None
        index = self._battle_view_index(state)
        row = index["battles"].get(str(battle_id))
        viewer = str(viewer_country_tag or "").strip().upper()
        if row is None or not viewer or viewer not in index["battle_viewers"].get(str(battle_id), set()):
            return None
        readiness_by_country: dict[str, set[str]] = {}
        readiness_distribution = {"parked": 0, "ready": 0, "fortified": 0}
        for unit in index["battle_units"].get(str(battle_id), ()):
            readiness = safe_text(unit.get("readiness_status"), "ready").strip().lower()
            readiness_by_country.setdefault(safe_text(unit.get("country_id")), set()).add(readiness)
            if readiness in readiness_distribution:
                readiness_distribution[readiness] += 1
        participants: list[BattleParticipantView] = []
        for participant in index["participants"].get(str(battle_id), ()):
            country_id = safe_text(participant.get("country_id"))
            participants.append(BattleParticipantView(
                country_id=country_id,
                side=safe_text(participant.get("side")),
                role=safe_text(participant.get("role"), "principal"),
                unit_count=safe_int(participant.get("unit_count"), 0),
                weighted_strength=safe_float(participant.get("weighted_strength"), 0.0),
                readiness=tuple(sorted(readiness_by_country.get(country_id, {"ready"}))),
            ))
        occupation = index["occupations"].get(int(row.get("region_id") or 0), {})
        region_name = index["regions"].get(int(row.get("region_id") or 0), f"Region {int(row.get('region_id') or 0)}")
        return BattleStatusView(
            battle_id=safe_text(row.get("id"), battle_id),
            region_id=safe_int(row.get("region_id"), 0),
            status=safe_text(row.get("status"), "inactive"),
            mode=safe_text(row.get("mode"), "positional").strip().lower(),
            side_a_countries=tuple(normalize_side(row.get("attacker_side"))),
            side_b_countries=tuple(normalize_side(row.get("defender_side"))),
            side_a_strength=safe_float(row.get("side_a_strength"), 0.0),
            side_b_strength=safe_float(row.get("side_b_strength"), 0.0),
            balance=safe_float(row.get("balance"), 0.0),
            side_a_losses=safe_int(row.get("side_a_losses"), 0),
            side_b_losses=safe_int(row.get("side_b_losses"), 0),
            round=safe_int(row.get("round"), 0),
            participants=tuple(participants),
            occupation=occupation,
            readiness_distribution=readiness_distribution,
            region_name=region_name,
            started_at_minute=safe_int(row.get("started_at_minute"), 0),
            updated_at_minute=safe_int(row.get("updated_at_minute"), 0),
            concluded_at_minute=safe_int(row.get("concluded_at_minute"), 0),
            victor_side=safe_text(row.get("victor_side"), ""),
        )

    def _battle_view_index(self, state) -> dict[str, object]:
        revisions = getattr(state, "table_revisions", {})
        key = (
            id(state),
            tuple(
                (name, int(revisions.get(name, 0)))
                for name in ("battles", "battle_units", "battle_participants", "occupations", "regions")
            ),
        )
        if key == self._battle_view_cache_key:
            return self._battle_view_cache

        battles = state.tables.get("battles")
        battle_rows = battles.to_dicts() if battles is not None and not battles.is_empty() else []
        battle_units = state.tables.get("battle_units")
        participant_table = state.tables.get("battle_participants")
        occupations = state.tables.get("occupations")
        regions = state.tables.get("regions")
        units_by_battle: dict[str, list[dict]] = {}
        for row in (battle_units.to_dicts() if battle_units is not None and not battle_units.is_empty() else []):
            units_by_battle.setdefault(str(row.get("battle_id") or ""), []).append(row)
        participants_by_battle: dict[str, list[dict]] = {}
        participant_rows = participant_table.to_dicts() if participant_table is not None and not participant_table.is_empty() else []
        for row in participant_rows:
            participants_by_battle.setdefault(str(row.get("battle_id") or ""), []).append(row)
        for rows in participants_by_battle.values():
            rows.sort(key=lambda row: safe_text(row.get("country_id")))
        battle_viewers: dict[str, set[str]] = {
            battle_id: set(normalize_side(row.get("attacker_side"))) | set(normalize_side(row.get("defender_side")))
            for battle_id, row in ((str(row.get("id") or ""), row) for row in battle_rows)
        }
        for participant in (
            battle_units.to_dicts() if battle_units is not None and not battle_units.is_empty() else []
        ) + participant_rows:
            battle_id = str(participant.get("battle_id") or "")
            country = safe_text(participant.get("country_id"), "").strip().upper()
            if battle_id and country:
                battle_viewers.setdefault(battle_id, set()).add(country)
        occupation_by_region = {
            int(row.get("region_id") or 0): row
            for row in (occupations.to_dicts() if occupations is not None and not occupations.is_empty() else [])
        }
        region_names = {
            int(row.get("id") or 0): safe_text(row.get("name"), f"Region {int(row.get('id') or 0)}")
            for row in (regions.to_dicts() if regions is not None and not regions.is_empty() else [])
        }
        self._battle_view_cache = {
            "battles": {str(row.get("id") or ""): row for row in battle_rows},
            "battle_units": units_by_battle,
            "participants": participants_by_battle,
            "battle_viewers": battle_viewers,
            "occupations": occupation_by_region,
            "regions": region_names,
        }
        self._battle_view_cache_key = key
        return self._battle_view_cache

    def _battle_visible_to_country(self, state, battle_id: str, country_tag: str) -> bool:
        country = str(country_tag or "").strip().upper()
        if not country:
            return False
        index = self._battle_view_index(state)
        return country in index["battle_viewers"].get(str(battle_id), set())

    def strategic_inventory_for_country(self, state, country_tag: str) -> list[dict]:
        inventory = state.tables.get("strategic_weapons")
        if inventory is None or inventory.is_empty():
            return []
        country = str(country_tag or "").strip().upper()
        rows = inventory.filter(pl.col("country_id") == country).to_dicts() if "country_id" in inventory.columns else inventory.to_dicts()
        research = state.tables.get("research_tracks")
        levels = {} if research is None else {
            str(row.get("branch") or "").strip().lower(): safe_int(row.get("research_level"), 0)
            for row in research.filter(pl.col("country_id") == country).to_dicts()
        }
        pending_table = state.tables.get("strategic_launch_orders")
        pending = {} if pending_table is None else {
            str(row.get("weapon_id") or ""): row for row in pending_table.to_dicts()
            if str(row.get("status") or "") == "pending"
        }
        for row in rows:
            required_program_level = max(1, safe_int(state.globals.get("strategic_program_research_level"), 1))
            required_weapon_level = max(
                1,
                safe_int(state.globals.get("strategic_weapon_research_level"), 1),
                safe_int(row.get("required_research_level"), 1),
            )
            row["research_permitted"] = (
                levels.get("strategic_program", 0) >= required_program_level
                and levels.get("strategic_weapons", 0) >= required_weapon_level
            )
            row["payload_cap"] = min(
                10,
                max(0, safe_int(row.get("max_payload_level"), 1)),
                levels.get("strategic_weapons", 0),
            )
            order = pending.get(str(row.get("id") or ""))
            row["pending_target_region_id"] = 0 if order is None else safe_int(order.get("target_region_id"), 0)
            row["pending_order_status"] = "" if order is None else safe_text(order.get("status"), "")
        return rows

    def strategic_production_preview(self, state, country_tag: str, weapon: dict, quantity: int = 1) -> dict:
        owner = str(country_tag or "").strip().upper()
        reasons: list[str] = []
        if not bool(weapon.get("research_permitted")):
            reasons.append("Required strategic program and weapon research are incomplete.")
        authorized_countries = state.globals.get("strategic_production_authorized_countries")
        if isinstance(authorized_countries, (list, tuple, set)) and owner not in {
            str(country).strip().upper() for country in authorized_countries
        }:
            reasons.append("This country lacks policy authority to produce strategic weapons.")
        cost_per_weapon = max(0.0, safe_float(weapon.get("production_cost"), 0.0))
        production_minutes = safe_int(weapon.get("production_minutes"), 0)
        if cost_per_weapon <= 0.0 or production_minutes <= 0:
            reasons.append("This weapon design has no configured production cost and duration.")
        total_cost = cost_per_weapon * max(1, int(quantity))
        country = get_country_row(state, owner)
        if safe_float(country.get("money_reserves"), 0.0) < total_cost:
            reasons.append("The country cannot fund this production order.")
        return {
            "can_produce": not reasons,
            "reasons": reasons,
            "cost_per_weapon": cost_per_weapon,
            "total_cost": total_cost,
            "production_minutes": max(0, production_minutes),
        }

    def strategic_production_orders_for_country(self, state, country_tag: str) -> list[dict]:
        table = state.tables.get("strategic_production_orders")
        if table is None or table.is_empty():
            return []
        country = str(country_tag or "").strip().upper()
        rows = [
            row for row in table.to_dicts()
            if safe_text(row.get("country_id"), "").upper() == country
        ]
        return sorted(rows, key=lambda row: (safe_int(row.get("ordered_at_minute"), 0), safe_text(row.get("id"), "")), reverse=True)

    def force_posture_text(self, state, country_tag: str) -> str:
        country_row = get_country_row(state, country_tag)
        military_count = safe_int(country_row.get("military_count"), 0)
        reserves = safe_float(country_row.get("money_reserves"), 0.0)
        research = as_ratio(country_row.get("budget_research_ratio"), 0.0)
        return (
            f"Field strength {military_count:,}".replace(",", " ")
            + f" | Reserves ${reserves:,.0f}".replace(",", " ")
            + f" | Research {research * 100:.1f}%"
        )

    def _country_units(self, state, country_tag: str) -> list[dict]:
        units = state.tables.get("units")
        if units is None or units.is_empty() or "owner" not in units.columns:
            return []
        return units.filter(pl.col("owner") == country_tag).to_dicts()

    def _allied_countries(self, state, country_tag: str) -> set[str]:
        treaties = state.tables.get("countries_treaties")
        if treaties is None or treaties.is_empty():
            return set()

        allied_types = {"alliance", "defensive_alliance", "military_alliance", "defensive_pact", "military_pact"}
        allies: set[str] = set()
        for row in treaties.to_dicts():
            treaty_type = safe_text(row.get("type")).lower()
            if treaty_type not in allied_types:
                continue

            members = set(normalize_side(row.get("members")))
            if not members:
                members = set(normalize_side(row.get("side_a"))) | set(normalize_side(row.get("side_b")))
            if country_tag not in members:
                continue
            allies.update(members)

        allies.discard(country_tag)
        return allies

    def _classify_branch(self, unit_type: str) -> str:
        lower = unit_type.lower()
        if any(token in lower for token in ("fighter", "air", "wing", "jet", "bomber")):
            return "AIR"
        if any(token in lower for token in ("ship", "nav", "fleet", "submarine", "carrier")):
            return "NAVAL"
        if any(token in lower for token in ("strategic", "missile", "rocket", "nuclear")):
            return "STRATEGIC"
        return "LAND"

    def _humanize_unit_type(self, unit_type: str) -> str:
        return unit_type.replace("_", " ").title()
