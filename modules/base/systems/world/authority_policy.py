"""Shared authority rules for commands that target a national government."""

from __future__ import annotations

from typing import Any

from src.shared.diplomacy import countries_at_war
from src.shared.region_control import country_region_control_proportion


TRUSTED_SYSTEM_ACTORS = frozenset({"SERVER", "AI", "AI_SYSTEM"})
LOCAL_CLIENT_ACTORS = frozenset({"LOCAL_ADMIN", "LOCAL_PLAYER"})
FOREIGN_GOVERNMENT_CONTROL_THRESHOLD = 0.75


def player_controls_country(state: Any, player_id: Any, country_id: Any) -> bool:
    actor = str(player_id or "").strip()
    country = _tag(country_id)
    mapping = state.globals.get("player_country_map", {})
    if isinstance(mapping, dict) and _tag(mapping.get(actor)) == country:
        return True
    if _tag(actor) in LOCAL_CLIENT_ACTORS and _tag(state.globals.get("player_tag")) == country:
        return True
    return _tag(actor) == country or _tag(actor) in TRUSTED_SYSTEM_ACTORS


def foreign_government_change_restriction(
    state: Any, player_id: Any, country_id: Any
) -> str:
    """Describe why a foreign government form cannot be changed by this actor."""
    actor_country = _player_country(state, player_id)
    country = _tag(country_id)
    countries = getattr(state, "tables", {}).get("countries")
    known_countries = (
        {_tag(value) for value in countries["id"].to_list()}
        if countries is not None and "id" in countries.columns
        else set()
    )
    if (
        not actor_country
        or actor_country == country
        or actor_country not in known_countries
        or not player_controls_country(state, player_id, actor_country)
    ):
        return "The issuer does not control a country that can change this government."
    if countries_at_war(state, actor_country, country):
        return "Government-form changes are unavailable while the country is hostile."
    proportion = country_region_control_proportion(state, actor_country, country)
    if proportion is None:
        return "Regional control data is unavailable for this country."
    if proportion < FOREIGN_GOVERNMENT_CONTROL_THRESHOLD:
        return "At least 75% of the country's political regions must be under your military control."
    return ""


def can_change_foreign_government(
    state: Any,
    player_id: Any,
    country_id: Any,
    confirmed: bool,
) -> bool:
    """Allow a confirmed form change after the actor controls 75% of a non-hostile country."""

    return bool(confirmed and not foreign_government_change_restriction(state, player_id, country_id))


def _player_country(state: Any, player_id: Any) -> str:
    actor = str(player_id or "").strip()
    mapping = state.globals.get("player_country_map", {})
    if isinstance(mapping, dict):
        mapped = _tag(mapping.get(actor))
        if mapped:
            return mapped
    actor_tag = _tag(actor)
    if actor_tag in LOCAL_CLIENT_ACTORS:
        return _tag(state.globals.get("player_tag"))
    if actor_tag in TRUSTED_SYSTEM_ACTORS:
        return ""
    return actor_tag


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()
