"""Validation and application for authoritative capital-region changes."""

from __future__ import annotations

import polars as pl

from modules.base.systems.world.authority_policy import player_controls_country
from src.shared.actions import ActionSetCountryCapital
from src.shared.determinism import DeterministicRuntime
from src.shared.events import EventGovernmentCapitalChanged
from src.shared.region_control import region_controlled_by_country
from src.shared.state import GameState


def process_country_capital_change(
    state: GameState,
    action: ActionSetCountryCapital,
    now: int,
) -> None:
    country = _tag(action.country_tag)
    reason = _validate_capital_change(state, action, country)
    rejected = bool(reason)
    event = None
    previous_region_id = 0

    if not reason:
        governments = state.tables["country_governments"].to_dicts()
        government = next(
            (row for row in governments if _tag(row.get("country_id")) == country),
            None,
        )
        previous_region_id = _integer(government.get("capital_region_id"))
        if previous_region_id != action.target_region_id:
            government.update(
                capital_region_id=action.target_region_id,
                updated_at_minute=now,
            )
            government_table = state.tables["country_governments"]
            state.update_table(
                "country_governments",
                pl.DataFrame(
                    governments,
                    schema=government_table.schema,
                    strict=False,
                ),
            )
            reason = "The country's capital region changed."
            event = EventGovernmentCapitalChanged(
                country,
                previous_region_id,
                action.target_region_id,
                now,
                reason,
            )
        else:
            reason = "The selected region is already the country's capital."
        previous_region_id = _integer(government.get("capital_region_id")) if event is None else event.previous_region_id

    state.journal.append_command_result(
        {
            "result_id": DeterministicRuntime(state.determinism).next_id(
                "political-command", int(state.globals.get("tick", 0))
            ),
            "action_type": type(action).__name__,
            "player_id": str(action.player_id),
            "status": "rejected" if rejected else "applied",
            "reason": reason,
            "game_minute": now,
            "country_id": country,
            "from_region_id": previous_region_id,
            "to_region_id": int(action.target_region_id),
        }
    )
    if event is not None:
        state.events.append(event)


def _validate_capital_change(
    state: GameState,
    action: ActionSetCountryCapital,
    country: str,
) -> str:
    if not country:
        return "Select a country before changing its capital."
    countries = state.tables.get("countries")
    if countries is None or "id" not in countries.columns or not any(
        _tag(value) == country for value in countries["id"].to_list()
    ):
        return "The selected country is unavailable."
    if not player_controls_country(state, action.player_id, country):
        return "The issuer does not control this country's government."

    governments = state.tables.get("country_governments")
    if governments is None or "country_id" not in governments.columns:
        return "The country's government record is unavailable."
    government = next(
        (row for row in governments.iter_rows(named=True) if _tag(row.get("country_id")) == country),
        None,
    )
    if government is None:
        return "The country's government record is unavailable."

    current_region_id = _integer(government.get("capital_region_id"))
    if type(action.expected_capital_region_id) is not int or action.expected_capital_region_id != current_region_id:
        return "The capital changed after this selection was opened. Review it and try again."
    if type(action.target_region_id) is not int or action.target_region_id <= 0:
        return "Select a valid capital region."

    regions = state.tables.get("regions")
    if regions is None or not {"id", "owner"}.issubset(regions.columns):
        return "Regional control data is unavailable."
    region = next(
        (row for row in regions.iter_rows(named=True) if _integer(row.get("id")) == action.target_region_id),
        None,
    )
    if region is None:
        return "The selected capital region is unavailable."

    if not region_controlled_by_country(state, region, country):
        return "The capital must be in a region currently controlled by this country."
    return ""


def _tag(value) -> str:
    return str(value or "").strip().upper()


def _integer(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
