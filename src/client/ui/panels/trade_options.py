"""Build bilateral trade choices from the current world snapshot."""

from typing import Any


def country_tag(value: Any) -> str:
    return str(value or "").strip().upper()


def nonnegative_integer(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def table_rows(state, table: str) -> list[dict[str, Any]]:
    frame = state.tables.get(table)
    return [] if frame is None else frame.to_dicts()


def country_options(state, exclude_tag: str) -> list[tuple[str, str]]:
    countries = state.tables.get("countries")
    if countries is None or "id" not in countries.columns:
        return []
    result = []
    for row in countries.iter_rows(named=True):
        tag = country_tag(row.get("id"))
        if not tag or tag == exclude_tag:
            continue
        label = row.get("name") or row.get("display_name") or row.get("country_name") or tag
        result.append((tag, f"{label} ({tag})"))
    return sorted(result, key=lambda item: item[1])


def regions_for_owner(state, owner_tag: str) -> list[tuple[int, str]]:
    regions = state.tables.get("regions")
    if regions is None or not {"id", "owner"}.issubset(regions.columns):
        return []
    government = next(
        (row for row in table_rows(state, "country_governments")
         if country_tag(row.get("country_id")) == owner_tag), {},
    )
    capital_id = nonnegative_integer(government.get("capital_region_id"))
    owned = [row for row in regions.iter_rows(named=True) if country_tag(row.get("owner")) == owner_tag]
    result = []
    for row in owned:
        region_id = nonnegative_integer(row.get("id"))
        if region_id == capital_id and len(owned) <= 1:
            continue
        name = row.get("name") or row.get("region_name") or row.get("display_name") or row.get("province") or "Region"
        result.append((region_id, f"{name} ({region_id})"))
    return sorted(result, key=lambda item: item[1])


def technology_options(state, giver: str, receiver: str) -> list[tuple[str, int, int]]:
    levels = {
        (country_tag(row.get("country_id")), str(row.get("branch") or "").casefold()):
            nonnegative_integer(row.get("research_level"))
        for row in table_rows(state, "research_tracks")
    }
    options = []
    for (country, branch), level in levels.items():
        receiver_level = levels.get((receiver, branch), 0)
        if country == giver and level > receiver_level:
            options.append((branch, level, receiver_level))
    return sorted(options, key=lambda item: item[0])
