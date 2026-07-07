from __future__ import annotations

from dataclasses import dataclass

import polars as pl

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
    location: str
    status: str
    progress_pct: float


class MilitaryPresenter:
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

    def unit_rows(self, state, country_tag: str) -> list[UnitListRow]:
        rows: list[UnitListRow] = []
        for row in self._country_units(state, country_tag):
            owner_tag = safe_text(row.get("owner"), country_tag)
            status = "Moving" if bool(row.get("is_moving", False)) else "Ready"
            progress_pct = max(0.0, min(100.0, safe_float(row.get("movement_progress"), 0.0) * 100.0))
            rows.append(
                UnitListRow(
                    unit_id=safe_text(row.get("id"), ""),
                    owner_name=resolve_country_name(state, owner_tag),
                    unit_type=self._humanize_unit_type(safe_text(row.get("unit_type"), "army")),
                    strength=safe_int(row.get("strength"), 0),
                    location=resolve_region_name(state, safe_int(row.get("current_region_id"), 0)),
                    status=status,
                    progress_pct=progress_pct,
                )
            )

        return sorted(rows, key=lambda item: (item.status != "Moving", item.location, item.unit_id))

    def production_orders_for_country(self, state, country_tag: str) -> list[dict]:
        orders = state.tables.get("production_orders")
        if orders is None or orders.is_empty():
            return []
        if "country_id" not in orders.columns:
            return orders.to_dicts()
        return orders.filter(pl.col("country_id") == country_tag).sort("priority").to_dicts()

    def designs_for_country(self, state, country_tag: str) -> list[dict]:
        designs = state.tables.get("unit_designs")
        if designs is None or designs.is_empty():
            return []
        if "country_id" not in designs.columns:
            return designs.to_dicts()
        return designs.filter(pl.col("country_id") == country_tag).sort(["branch", "display_name"]).to_dicts()

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

        rows = listings.to_dicts()
        designs = {row.get("id"): row for row in self.designs_for_country(state, country_tag)}
        for row in rows:
            design = designs.get(row.get("design_id"))
            row["design_name"] = safe_text(
                (design or {}).get("display_name"),
                safe_text(row.get("design_id"), "Unspecified"),
            )
        return rows

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
        battles = state.tables.get("battles")
        if battles is None or battles.is_empty():
            return []

        wars = {row["id"] for row in self.wars_for_country(state, country_tag)}
        rows = battles.to_dicts()
        if not wars:
            return rows
        return [row for row in rows if safe_text(row.get("id")) in wars or safe_text(row.get("status")).lower() == "active"]

    def strategic_inventory_for_country(self, state, country_tag: str) -> list[dict]:
        inventory = state.tables.get("strategic_weapons")
        if inventory is None or inventory.is_empty():
            return []
        if "country_id" not in inventory.columns:
            return inventory.to_dicts()
        return inventory.filter(pl.col("country_id") == country_tag).to_dicts()

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
