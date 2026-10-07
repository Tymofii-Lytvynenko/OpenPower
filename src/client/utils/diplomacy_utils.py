from typing import Set, Optional
from src.shared.state import GameState


MILITARY_ALLIANCE_TYPES = {
    "alliance",
    "defensive_alliance",
    "military_alliance",
    "defensive_pact",
    "military_pact",
}

def normalize_side(value) -> Set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(tag) for tag in value if tag is not None}
    if isinstance(value, tuple):
        return {str(tag) for tag in value if tag is not None}
    if isinstance(value, str):
        return {tag.strip() for tag in value.split(",") if tag.strip()}
    return set()

def get_military_allies(state: GameState, country_tag: Optional[str]) -> Set[str]:
    if not country_tag or "countries_treaties" not in state.tables:
        return set()

    treaties = state.get_table("countries_treaties")
    if treaties.is_empty():
        return set()

    selected_tag = str(country_tag).strip().upper()
    current_minute = int(state.time.total_minutes)
    allies = set()
    columns = set(treaties.columns)

    if {"members", "type"}.issubset(columns):
        for row in treaties.to_dicts():
            treaty_type = str(row["type"]).lower() if row["type"] is not None else ""
            if treaty_type not in MILITARY_ALLIANCE_TYPES or not _is_active_treaty(row, current_minute):
                continue

            suspended = normalize_side(row.get("suspended_members"))
            members = normalize_side(row["members"]) - suspended
            if selected_tag in members:
                allies.update(members)

    if {"side_a", "side_b", "type"}.issubset(columns):
        for row in treaties.to_dicts():
            treaty_type = str(row["type"]).lower() if row["type"] is not None else ""
            if treaty_type not in MILITARY_ALLIANCE_TYPES or not _is_active_treaty(row, current_minute):
                continue

            suspended = normalize_side(row.get("suspended_members"))
            side_a = normalize_side(row["side_a"]) - suspended
            side_b = normalize_side(row["side_b"]) - suspended
            if selected_tag in side_a:
                allies.update(side_b)
            elif selected_tag in side_b:
                allies.update(side_a)

    allies.discard(selected_tag)
    return allies

def get_military_enemies(state: GameState, country_tag: Optional[str]) -> Set[str]:
    if not country_tag or "countries_wars" not in state.tables:
        return set()

    enemies = set()
    wars = state.get_table("countries_wars")
    if "side_a" not in wars.columns or "side_b" not in wars.columns:
        return enemies

    for row in wars.to_dicts():
        status = str(row.get("status") or "active").strip().lower()
        if status != "active":
            continue
        side_a = normalize_side(row["side_a"])
        side_b = normalize_side(row["side_b"])
        selected_tag = str(country_tag).strip().upper()
        if selected_tag in side_a:
            enemies.update(side_b)
        elif selected_tag in side_b:
            enemies.update(side_a)

    enemies.discard(str(country_tag).strip().upper())
    return enemies


def _is_active_treaty(row: dict, current_minute: int) -> bool:
    status = str(row.get("status") or "active").strip().lower()
    if status != "active":
        return False
    try:
        expires_at = int(row.get("expires_at_minute") or 0)
    except (TypeError, ValueError):
        return True
    return expires_at <= 0 or expires_at > current_minute
