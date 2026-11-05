"""REFERENCE-compatible covert mission choices shared by UI and simulation actions."""

from __future__ import annotations

from src.shared.economy_meta import RESOURCE_MAPPING


MISSION_CATEGORY_OPTIONS = (
    ("espionage", "Espionage"),
    ("sabotage", "Sabotage"),
    ("assassination", "Assassination"),
    ("terrorism", "Terrorism"),
    ("coup_attempt", "Coup d'Etat"),
)

TARGET_SECTOR_OPTIONS = (
    ("civilian", "Civilian"),
    ("military", "Military"),
)

MISSION_COMPLEXITIES = ("low", "medium", "high")
_MISSION_COMPLEXITY_SUCCESS_MODIFIERS = {
    "low": 2.0,
    "medium": 1.0,
    "high": 0.5,
}
_MISSION_COMPLEXITY_EFFECT_MODIFIERS = {
    "low": 0.25,
    "medium": 1.0,
    "high": 2.0,
}
_SPECIFIC_TARGET_MISSION_TYPES = frozenset({
    "civilian_espionage",
    "military_espionage",
    "civilian_sabotage",
    "military_sabotage",
})
_SPECIFIC_TARGET_SUCCESS_MODIFIER = 0.75
UNIT_CATEGORY_OPTIONS = (
    ("ground", "Ground"),
    ("air", "Air"),
    ("naval", "Naval"),
    ("strategic", "Strategic"),
)


def mission_profile_type(category: str, sector: str) -> str:
    """Map the source's mission and sector controls to OpenPower's profile key."""
    mission_category = str(category or "").strip().lower()
    target_sector = str(sector or "").strip().lower()
    if mission_category in {"espionage", "sabotage"}:
        if target_sector not in {"civilian", "military"}:
            raise ValueError("Espionage and sabotage require a valid target sector.")
        return f"{target_sector}_{mission_category}"
    if mission_category in {"assassination", "terrorism", "coup_attempt"}:
        return mission_category
    raise ValueError("Unknown covert mission category.")


def mission_sector(profile_type: str) -> str:
    """Return the source target sector represented by a canonical profile key."""
    value = str(profile_type or "").strip().lower()
    for sector in ("civilian", "military"):
        if value.startswith(f"{sector}_"):
            return sector
    return ""


def allowed_complexities(profile_type: str, sector: str | None = None) -> tuple[str, ...]:
    """Return complexity choices that the REFERENCE form permits for this mission."""
    value = str(profile_type or "").strip().lower()
    target_sector = str(sector or mission_sector(value)).strip().lower()
    if value == "coup_attempt":
        return ("high",)
    if value == "military_sabotage" or (value == "sabotage" and target_sector == "military"):
        return ("medium", "high")
    return MISSION_COMPLEXITIES


def default_complexity(profile_type: str) -> str:
    return "high" if str(profile_type or "").strip().lower() == "coup_attempt" else "medium"


def mission_success_modifier(
    mission_type: str,
    complexity: str,
    *,
    has_specific_target: bool,
) -> float:
    """Return source-defined difficulty and specific-target success modifiers."""
    normalized_complexity = str(complexity or "medium").strip().lower()
    complexity_modifier = _MISSION_COMPLEXITY_SUCCESS_MODIFIERS.get(normalized_complexity, 1.0)
    mission = str(mission_type or "").strip().lower()
    target_modifier = (
        _SPECIFIC_TARGET_SUCCESS_MODIFIER
        if has_specific_target and mission in _SPECIFIC_TARGET_MISSION_TYPES
        else 1.0
    )
    return complexity_modifier * target_modifier


def mission_effect_modifier(complexity: str, *, partial: bool) -> float:
    """Scale the resolved OpenPower effect by source complexity and outcome quality."""
    normalized_complexity = str(complexity or "medium").strip().lower()
    complexity_modifier = _MISSION_COMPLEXITY_EFFECT_MODIFIERS.get(normalized_complexity, 1.0)
    return complexity_modifier * (0.5 if partial else 1.0)


def country_resource_ids(state, country_tag: str) -> tuple[str, ...]:
    """Use the country's OpenPower resource rows, falling back only when no ledger exists."""
    country = str(country_tag or "").strip().upper()
    has_resource_table = False
    for table_name in ("resource_ledger", "regional_production", "domestic_production"):
        table = state.tables.get(table_name)
        if table is None or not {"country_id", "game_resource_id"}.issubset(table.columns):
            continue
        has_resource_table = True
        values = {
            str(row.get("game_resource_id") or "").strip().lower()
            for row in table.select("country_id", "game_resource_id").iter_rows(named=True)
            if str(row.get("country_id") or "").strip().upper() == country
            and str(row.get("game_resource_id") or "").strip().lower() in RESOURCE_MAPPING
        }
        if values:
            return tuple(sorted(values))
    if has_resource_table:
        return ()
    return tuple(sorted(RESOURCE_MAPPING))


def resource_label(resource_id: str) -> str:
    return str(resource_id or "").replace("_", " ").title()
