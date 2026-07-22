from __future__ import annotations

from typing import Any

import polars as pl

from src.shared.schema import ColumnSpec, TableSchema, WorldSchemaRegistry
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
        "side_a": (pl.List(pl.Utf8), []),
        "side_b": (pl.List(pl.Utf8), []),
        "members": (pl.List(pl.Utf8), []),
        "required_responses": (pl.List(pl.Utf8), []),
        "accepted_members": (pl.List(pl.Utf8), []),
        "conditions_json": (pl.Utf8, ""),
        "open_to_new_members": (pl.Boolean, False),
        "created_at": (pl.Utf8, ""),
    },
    "treaty_effects": {
        "treaty_id": (pl.Utf8, ""),
        "country_id": (pl.Utf8, ""),
        "effect": (pl.Utf8, ""),
        "value": (pl.Float64, 0.0),
        "detail": (pl.Utf8, ""),
    },
    "annexation_claims": {
        "id": (pl.Utf8, ""),
        "treaty_id": (pl.Utf8, ""),
        "region_id": (pl.Int32, 0),
        "annexing_country_id": (pl.Utf8, ""),
        "political_owner_id": (pl.Utf8, ""),
        "controller_at_start": (pl.Utf8, ""),
        "due_at_minute": (pl.Int64, 0),
        "status": (pl.Utf8, "pending"),
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
        "description": (pl.Utf8, "active"),
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
        "mode": (pl.Utf8, "positional"),
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

TABLE_KEYS: dict[str, tuple[str, ...]] = {
    "country_governments": ("country_id",),
    "country_laws": ("country_id", "law_id"),
    "pending_treaties": ("id",),
    "treaty_effects": ("treaty_id", "country_id", "effect"),
    "annexation_claims": ("id",),
    "messages": ("id",),
    "news_items": ("id",),
    "objectives": ("id",),
    "research_tracks": ("id",),
    "unit_designs": ("id",),
    "production_orders": ("id",),
    "unit_market_listings": ("id",),
    "covert_cells": ("id",),
    "battles": ("id",),
    "battle_units": ("battle_id", "unit_id"),
    "strategic_weapons": ("id",),
}

COUNTRY_RUNTIME_SCHEMA = TableSchema(
    name="countries",
    columns={
        "id": ColumnSpec(pl.Utf8, ""),
        "gdp": ColumnSpec(pl.Float64, 10_000_000.0),
        "human_dev": ColumnSpec(pl.Float64, 0.5),
        "personal_income_tax_rate": ColumnSpec(pl.Float64, 0.2),
        "money_reserves": ColumnSpec(pl.Float64, 0.0),
        "total_annual_revenue": ColumnSpec(pl.Float64, 0.0),
        "total_annual_expense": ColumnSpec(pl.Float64, 0.0),
        "trait_threat_perception": ColumnSpec(pl.Float64, 1.0),
        "military_count": ColumnSpec(pl.Int64, 0),
        "trade_income": ColumnSpec(pl.Float64, 0.0),
        "trade_expense": ColumnSpec(pl.Float64, 0.0),
        "budget_imf_ratio": ColumnSpec(pl.Float64, 0.0),
        "budget_edu_ratio": ColumnSpec(pl.Float64, 0.5),
        "budget_health_ratio": ColumnSpec(pl.Float64, 0.5),
        "budget_social_ratio": ColumnSpec(pl.Float64, 0.5),
        "budget_env_ratio": ColumnSpec(pl.Float64, 0.5),
        "budget_infra_ratio": ColumnSpec(pl.Float64, 0.5),
        "budget_telecom_ratio": ColumnSpec(pl.Float64, 0.5),
        "budget_gov_ratio": ColumnSpec(pl.Float64, 0.5),
        "budget_propaganda_ratio": ColumnSpec(pl.Float64, 0.5),
        "budget_tourism_promo_ratio": ColumnSpec(pl.Float64, 0.5),
        "budget_research_ratio": ColumnSpec(pl.Float64, 0.5),
        "security_upkeep": ColumnSpec(pl.Float64, 0.0),
        "diplomacy_upkeep": ColumnSpec(pl.Float64, 0.0),
        "treaty_maintenance": ColumnSpec(pl.Float64, 0.0),
        "diplomatic_aid_expense": ColumnSpec(pl.Float64, 0.0),
        "corruption_index": ColumnSpec(pl.Float64, 0.1),
    },
    key_columns=("id",),
    owner="base",
    preserve_extra_columns=True,
)


BASE_TABLE_SCHEMAS: tuple[TableSchema, ...] = (COUNTRY_RUNTIME_SCHEMA,) + tuple(
    TableSchema(
        name=table_name,
        columns={
            column_name: ColumnSpec(dtype=dtype, default=default)
            for column_name, (dtype, default) in columns.items()
        },
        key_columns=TABLE_KEYS.get(table_name, ()),
        owner="base",
        preserve_extra_columns=False,
    )
    for table_name, columns in SUPPORT_TABLE_SPECS.items()
)


def build_base_schema_registry() -> WorldSchemaRegistry:
    return WorldSchemaRegistry(BASE_TABLE_SCHEMAS)


def ensure_base_tables(
    state: GameState,
    registry: WorldSchemaRegistry | None = None,
) -> WorldSchemaRegistry:
    resolved = registry or build_base_schema_registry()
    resolved.ensure_state(state)
    return resolved
