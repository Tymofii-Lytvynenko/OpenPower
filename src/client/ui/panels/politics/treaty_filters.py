"""Build and apply treaty browser filters against a world snapshot."""

from src.client.ui.panels.shared.panel_data import resolve_country_name
from src.shared.treaties import TREATY_DEFINITIONS, normalize_country_tags, normalize_treaty_type


def treaty_member_tags(row: dict) -> tuple[str, ...]:
    members = normalize_country_tags(row.get("members"))
    if members:
        return members
    side_a = normalize_country_tags(row.get("side_a"))
    side_b = normalize_country_tags(row.get("side_b"))
    if side_a or side_b:
        return tuple(sorted(set(side_a) | set(side_b)))
    return normalize_country_tags((row.get("source_country_id"), row.get("target_country_id")))


def treaty_filter_options(state, rows: list[dict]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    country_tags = set()
    countries = state.tables.get("countries")
    if countries is not None and "id" in countries.columns:
        for row in countries.iter_rows(named=True):
            if row.get("active") is False:
                continue
            tag = str(row.get("id") or "").strip().upper()
            if tag:
                country_tags.add(tag)
    for row in rows:
        country_tags.update(treaty_member_tags(row))

    member_options = [
        (tag, f"{resolve_country_name(state, tag)} ({tag})")
        for tag in sorted(country_tags)
    ]
    type_keys = set(TREATY_DEFINITIONS)
    type_keys.update(normalize_treaty_type(row.get("type") or row.get("treaty_type")) for row in rows)
    type_keys.discard("")
    type_options = [
        (key, TREATY_DEFINITIONS[key].label if key in TREATY_DEFINITIONS else key.replace("_", " ").title())
        for key in sorted(
            type_keys,
            key=lambda item: (
                (TREATY_DEFINITIONS[item].label if item in TREATY_DEFINITIONS else item).casefold(), item,
            ),
        )
    ]
    return member_options, type_options


def matches_treaty_filter(row: dict, member_tag: str, treaty_type: str) -> bool:
    if member_tag and member_tag not in treaty_member_tags(row):
        return False
    row_type = normalize_treaty_type(row.get("type") or row.get("treaty_type"))
    return not treaty_type or row_type == treaty_type
