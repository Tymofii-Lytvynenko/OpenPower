from typing import Set, Optional
from src.shared.state import GameState

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

    allies = set()
    columns = set(treaties.columns)

    if {"members", "type"}.issubset(columns):
        for row in treaties.select(["members", "type"]).iter_rows(named=True):
            treaty_type = str(row["type"]).lower() if row["type"] is not None else ""
            if treaty_type not in {"alliance", "defensive_alliance", "military_alliance"}:
                continue

            members = normalize_side(row["members"])
            if country_tag in members:
                allies.update(members)

    if {"side_a", "side_b", "type"}.issubset(columns):
        for row in treaties.select(["side_a", "side_b", "type"]).iter_rows(named=True):
            treaty_type = str(row["type"]).lower() if row["type"] is not None else ""
            if treaty_type not in {"alliance", "defensive_alliance", "military_alliance"}:
                continue

            side_a = normalize_side(row["side_a"])
            side_b = normalize_side(row["side_b"])
            if country_tag in side_a:
                allies.update(side_b)
            elif country_tag in side_b:
                allies.update(side_a)

    allies.discard(country_tag)
    return allies

def get_military_enemies(state: GameState, country_tag: Optional[str]) -> Set[str]:
    if not country_tag or "countries_wars" not in state.tables:
        return set()

    enemies = set()
    wars = state.get_table("countries_wars")
    if "side_a" not in wars.columns or "side_b" not in wars.columns:
        return enemies

    for row in wars.select(["side_a", "side_b"]).iter_rows(named=True):
        side_a = normalize_side(row["side_a"])
        side_b = normalize_side(row["side_b"])
        if country_tag in side_a:
            enemies.update(side_b)
        elif country_tag in side_b:
            enemies.update(side_a)

    enemies.discard(country_tag)
    return enemies
