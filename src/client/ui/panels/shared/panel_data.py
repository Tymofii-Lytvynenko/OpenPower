from __future__ import annotations

from typing import Any, Iterable

import polars as pl


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def as_ratio(value: Any, default: float = 0.0) -> float:
    ratio = safe_float(value, default)
    if ratio > 1.0:
        ratio /= 100.0
    return max(0.0, min(1.0, ratio))


def as_percent(value: Any, default: float = 0.0) -> float:
    return as_ratio(value, default / 100.0) * 100.0


def get_country_row(state, country_tag: str) -> dict[str, Any]:
    countries = state.tables.get("countries")
    if countries is None or countries.is_empty() or "id" not in countries.columns:
        return {}

    rows = countries.filter(pl.col("id") == country_tag)
    if rows.is_empty():
        return {}
    return rows.to_dicts()[0]


def resolve_country_name(state, owner_tag: str) -> str:
    owner_tag = safe_text(owner_tag, "Unknown")
    countries = state.tables.get("countries")
    if countries is None or countries.is_empty() or "id" not in countries.columns:
        return owner_tag

    if "name" in countries.columns:
        match = countries.filter(pl.col("id") == owner_tag).select("name")
        if not match.is_empty():
            return safe_text(match.item(0, 0), owner_tag)

    return owner_tag


def resolve_region_name(state, region_id: int) -> str:
    if region_id <= 0:
        return "Unknown"

    regions = state.tables.get("regions")
    if regions is None or regions.is_empty() or "id" not in regions.columns:
        return f"Region {region_id}"

    if "name" in regions.columns:
        match = regions.filter(pl.col("id") == region_id).select("name")
        if not match.is_empty():
            return safe_text(match.item(0, 0), f"Region {region_id}")

    return f"Region {region_id}"


def normalize_side(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(tag) for tag in value if tag is not None)
    if isinstance(value, tuple):
        return tuple(str(tag) for tag in value if tag is not None)
    if isinstance(value, str):
        return tuple(tag.strip() for tag in value.split(",") if tag.strip())
    return ()


def format_side_names(state, value: Any) -> str:
    members = [resolve_country_name(state, tag) for tag in normalize_side(value)]
    return ", ".join(members) if members else "None"


def is_playable_country(row: dict[str, Any]) -> bool:
    value = row.get("is_playable", True)
    if isinstance(value, bool):
        return value
    return safe_text(value).lower() == "true"


def top_rows(df: pl.DataFrame | None, count: int = 5) -> list[dict[str, Any]]:
    if df is None or df.is_empty():
        return []
    return df.head(count).to_dicts()


def format_members_count(value: Iterable[Any] | Any) -> int:
    if isinstance(value, (list, tuple)):
        return len([member for member in value if member is not None])
    if isinstance(value, str):
        return len([member for member in value.split(",") if member.strip()])
    return 0
