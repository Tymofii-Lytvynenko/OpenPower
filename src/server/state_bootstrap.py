from __future__ import annotations

from typing import Any

import polars as pl

from src.shared.state import GameState


TableSpec = dict[str, tuple[pl.DataType, Any]]


SUPPORT_TABLE_SPECS: dict[str, TableSpec] = {
    "country_governments": {
        "country_id": (pl.Utf8, ""),
        "government_type": (pl.Utf8, "Transitional republic"),
        "capital_region_id": (pl.Int32, 0),
        "next_election": (pl.Utf8, ""),
        "martial_law": (pl.Boolean, False),
        "election_risk": (pl.Float64, 0.0),
        "ideology_balance": (pl.Float64, 0.5),
    },
    "country_laws": {
        "country_id": (pl.Utf8, ""),
        "law_id": (pl.Utf8, ""),
        "group_name": (pl.Utf8, ""),
        "title": (pl.Utf8, ""),
        "status": (pl.Utf8, ""),
        "value": (pl.Utf8, ""),
        "notes": (pl.Utf8, ""),
    },
    "pending_treaties": {
        "id": (pl.Utf8, ""),
        "source_country_id": (pl.Utf8, ""),
        "target_country_id": (pl.Utf8, ""),
        "treaty_type": (pl.Utf8, ""),
        "title": (pl.Utf8, ""),
        "terms": (pl.Utf8, ""),
        "status": (pl.Utf8, "pending"),
        "created_at": (pl.Utf8, ""),
    },
    "messages": {
        "id": (pl.Utf8, ""),
        "country_id": (pl.Utf8, ""),
        "category": (pl.Utf8, ""),
        "subject": (pl.Utf8, ""),
        "body": (pl.Utf8, ""),
        "is_read": (pl.Boolean, False),
        "created_at": (pl.Utf8, ""),
    },
    "news_items": {
        "id": (pl.Utf8, ""),
        "headline": (pl.Utf8, ""),
        "body": (pl.Utf8, ""),
        "category": (pl.Utf8, ""),
        "severity": (pl.Utf8, "info"),
        "related_country_id": (pl.Utf8, ""),
        "created_at": (pl.Utf8, ""),
    },
    "objectives": {
        "id": (pl.Utf8, ""),
        "country_id": (pl.Utf8, ""),
        "title": (pl.Utf8, ""),
        "description": (pl.Utf8, ""),
        "status": (pl.Utf8, "active"),
        "progress": (pl.Float64, 0.0),
    },
    "research_tracks": {
        "id": (pl.Utf8, ""),
        "country_id": (pl.Utf8, ""),
        "branch": (pl.Utf8, ""),
        "funding_ratio": (pl.Float64, 0.0),
        "progress": (pl.Float64, 0.0),
        "priority": (pl.Int32, 1),
        "focus": (pl.Utf8, ""),
    },
    "unit_designs": {
        "id": (pl.Utf8, ""),
        "country_id": (pl.Utf8, ""),
        "branch": (pl.Utf8, ""),
        "class_name": (pl.Utf8, ""),
        "display_name": (pl.Utf8, ""),
        "quality": (pl.Float64, 0.0),
        "cost": (pl.Float64, 0.0),
        "speed": (pl.Float64, 0.0),
        "firepower": (pl.Float64, 0.0),
    },
    "production_orders": {
        "id": (pl.Utf8, ""),
        "country_id": (pl.Utf8, ""),
        "design_id": (pl.Utf8, ""),
        "quantity": (pl.Int32, 0),
        "progress": (pl.Float64, 0.0),
        "priority": (pl.Int32, 1),
        "status": (pl.Utf8, "queued"),
        "eta_days": (pl.Int32, 0),
    },
    "unit_market_listings": {
        "id": (pl.Utf8, ""),
        "seller_country_id": (pl.Utf8, ""),
        "design_id": (pl.Utf8, ""),
        "quantity": (pl.Int32, 0),
        "price": (pl.Float64, 0.0),
        "eligibility": (pl.Utf8, "open"),
    },
    "covert_cells": {
        "id": (pl.Utf8, ""),
        "country_id": (pl.Utf8, ""),
        "target_country_id": (pl.Utf8, ""),
        "cell_name": (pl.Utf8, ""),
        "readiness": (pl.Float64, 0.0),
        "mission_type": (pl.Utf8, ""),
        "status": (pl.Utf8, "idle"),
    },
    "battles": {
        "id": (pl.Utf8, ""),
        "region_id": (pl.Int32, 0),
        "attacker_side": (pl.Utf8, ""),
        "defender_side": (pl.Utf8, ""),
        "balance": (pl.Float64, 0.0),
        "status": (pl.Utf8, "inactive"),
    },
    "battle_units": {
        "battle_id": (pl.Utf8, ""),
        "unit_id": (pl.Utf8, ""),
        "side": (pl.Utf8, ""),
        "strength_share": (pl.Float64, 0.0),
    },
    "strategic_weapons": {
        "id": (pl.Utf8, ""),
        "country_id": (pl.Utf8, ""),
        "weapon_type": (pl.Utf8, ""),
        "quantity": (pl.Int32, 0),
        "ready": (pl.Int32, 0),
        "defense_rating": (pl.Float64, 0.0),
    },
}


def ensure_ui_support_tables(state: GameState) -> None:
    """Creates compatibility tables expected by the expanded client panels."""

    for table_name, spec in SUPPORT_TABLE_SPECS.items():
        existing = state.tables.get(table_name)
        if existing is None or existing.is_empty():
            rows = _seed_rows(table_name, state)
            state.update_table(table_name, _frame_from_rows(spec, rows))
            continue

        state.update_table(table_name, _normalize_table(existing, spec))


def _frame_from_rows(spec: TableSpec, rows: list[dict[str, Any]] | None) -> pl.DataFrame:
    if not rows:
        schema = {column: dtype for column, (dtype, _) in spec.items()}
        return pl.DataFrame(schema=schema)

    return _normalize_table(pl.DataFrame(rows), spec)


def _normalize_table(df: pl.DataFrame, spec: TableSpec) -> pl.DataFrame:
    for column, (_, default_value) in spec.items():
        if column not in df.columns:
            df = df.with_columns(pl.lit(default_value).alias(column))

    return df.select([pl.col(column).cast(dtype).alias(column) for column, (dtype, _) in spec.items()])


def _seed_rows(table_name: str, state: GameState) -> list[dict[str, Any]] | None:
    builders = {
        "country_governments": _build_country_governments,
        "country_laws": _build_country_laws,
        "messages": _build_messages,
        "news_items": _build_news_items,
        "objectives": _build_objectives,
        "research_tracks": _build_research_tracks,
        "unit_designs": _build_unit_designs,
        "strategic_weapons": _build_strategic_weapons,
    }
    builder = builders.get(table_name)
    if builder is None:
        return None
    return builder(state)


def _build_country_governments(state: GameState) -> list[dict[str, Any]]:
    countries = state.tables.get("countries")
    if countries is None or countries.is_empty() or "id" not in countries.columns:
        return []

    home_regions = _home_regions_by_country(state.tables.get("regions"))
    rows: list[dict[str, Any]] = []
    for row in countries.iter_rows(named=True):
        country_id = str(row["id"])
        approval = _as_ratio(row.get("gvt_approval"), 0.5)
        stability = _as_ratio(row.get("gvt_stability"), 0.5)
        corruption = _as_ratio(row.get("gvt_corruption"), 0.4)
        development = _as_ratio(row.get("human_dev"), 0.45)

        government_type = _classify_government(approval, stability, corruption, development)
        rows.append(
            {
                "country_id": country_id,
                "government_type": government_type,
                "capital_region_id": home_regions.get(country_id, 0),
                "next_election": _estimate_next_election(approval, development),
                "martial_law": stability < 0.30,
                "election_risk": max(0.0, min(1.0, 1.0 - ((approval * 0.55) + (stability * 0.45)))),
                "ideology_balance": max(
                    0.0,
                    min(1.0, 1.0 - (_as_ratio(row.get("global_tax_rate"), 0.2) * 1.5)),
                ),
            }
        )

    return rows


def _build_country_laws(state: GameState) -> list[dict[str, Any]]:
    countries = state.tables.get("countries")
    if countries is None or countries.is_empty() or "id" not in countries.columns:
        return []

    rows: list[dict[str, Any]] = []
    for row in countries.iter_rows(named=True):
        country_id = str(row["id"])
        approval = _as_ratio(row.get("gvt_approval"), 0.5)
        stability = _as_ratio(row.get("gvt_stability"), 0.5)
        corruption = _as_ratio(row.get("gvt_corruption"), 0.4)
        development = _as_ratio(row.get("human_dev"), 0.45)
        reserves = float(row.get("money_reserves") or 0.0)

        law_rows = (
            {
                "law_id": "religion_policy",
                "group_name": "Society",
                "title": "Religion Policy",
                "status": "Open recognition" if development >= 0.45 else "State supervision",
                "value": "Plural framework" if approval >= 0.45 else "Monitored practice",
                "notes": "Derived from development and approval indicators.",
            },
            {
                "law_id": "language_policy",
                "group_name": "Society",
                "title": "Language Policy",
                "status": "Multilingual support" if development >= 0.60 else "Single official channel",
                "value": "Minority protection" if development >= 0.60 else "State-first administration",
                "notes": "Derived from development indicators.",
            },
            {
                "law_id": "party_system",
                "group_name": "Parties",
                "title": "Party Registration",
                "status": "Open registration" if approval >= 0.50 else "Restricted funding",
                "value": "Competitive" if approval >= 0.50 else "Managed competition",
                "notes": "Derived from approval levels.",
            },
            {
                "law_id": "civil_rights",
                "group_name": "Rights",
                "title": "Civil Rights",
                "status": "Protected" if corruption <= 0.35 else "Under pressure",
                "value": "Judicial review" if corruption <= 0.35 else "Administrative controls",
                "notes": "Derived from corruption indicators.",
            },
            {
                "law_id": "migration_policy",
                "group_name": "Borders",
                "title": "Migration Policy",
                "status": "Managed entry" if reserves >= 0 else "Emergency limits",
                "value": "Quota system" if reserves >= 0 else "Tight restrictions",
                "notes": "Derived from reserve balance.",
            },
            {
                "law_id": "border_policy",
                "group_name": "Borders",
                "title": "Border Policy",
                "status": "Screened access" if stability >= 0.35 else "Security lockdown",
                "value": "Trade corridors open" if stability >= 0.35 else "Priority checkpoints",
                "notes": "Derived from stability indicators.",
            },
        )

        for law in law_rows:
            rows.append({"country_id": country_id, **law})

    return rows


def _build_messages(state: GameState) -> list[dict[str, Any]]:
    countries = state.tables.get("countries")
    if countries is None or countries.is_empty() or "id" not in countries.columns:
        return []

    created_at = state.time.date_str
    rows: list[dict[str, Any]] = []
    for row in countries.iter_rows(named=True):
        country_id = str(row["id"])
        if not _is_playable(row):
            continue

        rows.append(
            {
                "id": f"brief-{country_id}",
                "country_id": country_id,
                "category": "briefing",
                "subject": "Cabinet brief ready",
                "body": "The current cabinet packet includes diplomacy, budget, and force posture summaries.",
                "is_read": False,
                "created_at": created_at,
            }
        )

    return rows


def _build_news_items(state: GameState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    created_at = state.time.date_str

    treaties = state.tables.get("countries_treaties")
    if treaties is not None and not treaties.is_empty():
        for row in treaties.head(8).iter_rows(named=True):
            treaty_name = str(row.get("name") or row.get("id") or "Treaty")
            rows.append(
                {
                    "id": f"news-treaty-{row.get('id', treaty_name)}",
                    "headline": f"{treaty_name} remains active",
                    "body": "Member coordination and obligations remain in force.",
                    "category": "diplomacy",
                    "severity": "info",
                    "related_country_id": "",
                    "created_at": created_at,
                }
            )

    wars = state.tables.get("countries_wars")
    if wars is not None and not wars.is_empty():
        for index, row in enumerate(wars.head(8).iter_rows(named=True), start=1):
            attacker = ", ".join(_normalize_side(row.get("side_a"))) or "Unknown"
            defender = ", ".join(_normalize_side(row.get("side_b"))) or "Unknown"
            rows.append(
                {
                    "id": f"news-war-{index}",
                    "headline": f"Conflict watch: {attacker} vs {defender}",
                    "body": "The operations board is monitoring active military commitments.",
                    "category": "war",
                    "severity": "warning",
                    "related_country_id": "",
                    "created_at": created_at,
                }
            )

    if not rows:
        rows.append(
            {
                "id": "news-bootstrap",
                "headline": "Operations center online",
                "body": "Live news feeds are ready for new world events.",
                "category": "system",
                "severity": "info",
                "related_country_id": "",
                "created_at": created_at,
            }
        )

    return rows


def _build_objectives(state: GameState) -> list[dict[str, Any]]:
    countries = state.tables.get("countries")
    if countries is None or countries.is_empty() or "id" not in countries.columns:
        return []

    rows: list[dict[str, Any]] = []
    for row in countries.iter_rows(named=True):
        if not _is_playable(row):
            continue

        country_id = str(row["id"])
        stability = _as_ratio(row.get("gvt_stability"), 0.5)
        reserves = float(row.get("money_reserves") or 0.0)
        readiness = min(1.0, max(0.0, float(row.get("military_count") or 0.0) / 500_000.0))

        rows.extend(
            [
                {
                    "id": f"obj-stability-{country_id}",
                    "country_id": country_id,
                    "title": "Steady government approval",
                    "description": "Keep government stability above fifty percent.",
                    "status": "active",
                    "progress": stability,
                },
                {
                    "id": f"obj-reserves-{country_id}",
                    "country_id": country_id,
                    "title": "Maintain positive reserves",
                    "description": "Avoid a negative reserve balance while funding core services.",
                    "status": "active",
                    "progress": 1.0 if reserves >= 0 else 0.0,
                },
                {
                    "id": f"obj-readiness-{country_id}",
                    "country_id": country_id,
                    "title": "Keep armed forces ready",
                    "description": "Sustain a deployable force posture and avoid hollow readiness.",
                    "status": "active",
                    "progress": readiness,
                },
            ]
        )

    return rows


def _build_research_tracks(state: GameState) -> list[dict[str, Any]]:
    countries = state.tables.get("countries")
    if countries is None or countries.is_empty() or "id" not in countries.columns:
        return []

    rows: list[dict[str, Any]] = []
    branches = (
        ("ground", "Land modernization"),
        ("air", "Air superiority"),
        ("naval", "Fleet sustainment"),
        ("strategic", "Strategic deterrence"),
    )
    for row in countries.iter_rows(named=True):
        country_id = str(row["id"])
        if not _is_playable(row):
            continue

        research_ratio = _as_ratio(row.get("budget_research_ratio"), 0.12)
        development = _as_ratio(row.get("human_dev"), 0.45)
        for index, (branch, focus) in enumerate(branches, start=1):
            rows.append(
                {
                    "id": f"{country_id}-{branch}",
                    "country_id": country_id,
                    "branch": branch,
                    "funding_ratio": research_ratio,
                    "progress": max(0.05, min(0.95, development * (0.60 + (index * 0.05)))),
                    "priority": index,
                    "focus": focus,
                }
            )

    return rows


def _build_unit_designs(state: GameState) -> list[dict[str, Any]]:
    countries = state.tables.get("countries")
    if countries is None or countries.is_empty() or "id" not in countries.columns:
        return []

    design_templates = (
        ("ground", "Army", "Standard Corps", 0.55, 12_000_000.0, 0.45, 0.60),
        ("air", "Air Wing", "Interceptor Wing", 0.58, 48_000_000.0, 0.82, 0.72),
        ("naval", "Fleet", "Escort Squadron", 0.52, 95_000_000.0, 0.38, 0.68),
        ("strategic", "Command", "Deterrence Wing", 0.60, 140_000_000.0, 0.30, 0.80),
    )

    rows: list[dict[str, Any]] = []
    for row in countries.iter_rows(named=True):
        country_id = str(row["id"])
        if not _is_playable(row):
            continue

        development = _as_ratio(row.get("human_dev"), 0.45)
        for branch, class_name, display_name, quality, cost, speed, firepower in design_templates:
            rows.append(
                {
                    "id": f"{country_id}-{branch}-standard",
                    "country_id": country_id,
                    "branch": branch,
                    "class_name": class_name,
                    "display_name": display_name,
                    "quality": max(0.20, min(0.95, quality + (development * 0.20))),
                    "cost": cost,
                    "speed": speed,
                    "firepower": firepower,
                }
            )

    return rows


def _build_strategic_weapons(state: GameState) -> list[dict[str, Any]]:
    countries = state.tables.get("countries")
    if countries is None or countries.is_empty() or "id" not in countries.columns:
        return []

    rows: list[dict[str, Any]] = []
    for row in countries.iter_rows(named=True):
        country_id = str(row["id"])
        if not _is_playable(row):
            continue

        military_count = float(row.get("military_count") or 0.0)
        reserves = float(row.get("money_reserves") or 0.0)
        quantity = 0
        if military_count >= 700_000 and reserves >= 20_000_000_000:
            quantity = 12
        elif military_count >= 350_000 and reserves >= 5_000_000_000:
            quantity = 4

        rows.append(
            {
                "id": f"{country_id}-strategic",
                "country_id": country_id,
                "weapon_type": "Ballistic missiles",
                "quantity": quantity,
                "ready": int(quantity * 0.75),
                "defense_rating": max(0.05, min(0.95, _as_ratio(row.get("budget_research_ratio"), 0.1) * 1.8)),
            }
        )

    return rows


def _home_regions_by_country(regions: pl.DataFrame | None) -> dict[str, int]:
    if regions is None or regions.is_empty() or not {"id", "owner"}.issubset(set(regions.columns)):
        return {}

    score_columns = [column for column in ("pop_15_64", "area_km2") if column in regions.columns]
    selected: dict[str, tuple[int, float]] = {}
    for row in regions.iter_rows(named=True):
        owner = row.get("owner")
        region_id = row.get("id")
        if not owner or owner == "None" or region_id is None:
            continue

        score = 0.0
        for column in score_columns:
            score += float(row.get(column) or 0.0)

        owner_key = str(owner)
        current = selected.get(owner_key)
        if current is None or score > current[1]:
            selected[owner_key] = (int(region_id), score)

    return {country_id: region_id for country_id, (region_id, _) in selected.items()}


def _classify_government(approval: float, stability: float, corruption: float, development: float) -> str:
    if stability < 0.25:
        return "Emergency administration"
    if development >= 0.75 and approval >= 0.45:
        return "Multi-party democracy"
    if corruption >= 0.60 and approval < 0.40:
        return "Military-led state"
    if development >= 0.55:
        return "Centralized republic"
    return "Transitional republic"


def _estimate_next_election(approval: float, development: float) -> str:
    year = 2002 + int(round((approval + development) * 3))
    return f"{year:04d}-06-01"


def _normalize_side(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(tag) for tag in value if tag is not None)
    if isinstance(value, tuple):
        return tuple(str(tag) for tag in value if tag is not None)
    if isinstance(value, str):
        return tuple(tag.strip() for tag in value.split(",") if tag.strip())
    return ()


def _as_ratio(value: Any, default: float) -> float:
    if value is None:
        return default
    number = float(value)
    if number > 1.0:
        number /= 100.0
    return max(0.0, min(1.0, number))


def _is_playable(row: dict[str, Any]) -> bool:
    value = row.get("is_playable", True)
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"
