"""REFERENCE type presentation order and OpenPower role crosswalk for military UI."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from modules.base.systems.military.capability_catalog import canonical_role


@dataclass(frozen=True, slots=True)
class UnitTypeOption:
    role: str
    label: str
    source_string_id: int | None


REFERENCE_UNIT_TYPE_OPTIONS = (
    UnitTypeOption("infantry", "Infantry", 100262),
    UnitTypeOption("infantry_vehicles", "Infantry Vehicle", 100244),
    UnitTypeOption("air_defense", "Air Defense", 100245),
    UnitTypeOption("mobile_launchers", "Mobile Launcher", 100246),
    UnitTypeOption("tanks", "Tank", 100247),
    UnitTypeOption("artillery", "Artillery Gun", 100248),
    UnitTypeOption("attack_helicopters", "Attack Helicopter", 100249),
    UnitTypeOption("transport_helicopters", "Transport Helicopter", 100250),
    UnitTypeOption("anti_submarine_helicopters", "ASW Helicopter", 100251),
    UnitTypeOption("fighters", "Fighter Aircraft", 100252),
    UnitTypeOption("attack_aircraft", "Attack Aircraft", 100253),
    UnitTypeOption("bombers", "Bomber", 100254),
    UnitTypeOption("patrol_craft", "Patrol Craft", 100255),
    UnitTypeOption("corvettes", "Corvette", 100256),
    UnitTypeOption("frigates", "Frigate", 100257),
    UnitTypeOption("destroyers", "Destroyer", 100258),
    UnitTypeOption("attack_submarines", "Attack Submarine", 100259),
    UnitTypeOption("ballistic_missile_submarines", "Ballistic Missile Submarine", 100260),
    UnitTypeOption("aircraft_carriers", "Aircraft Carrier", 100261),
    UnitTypeOption("strategic_missiles", "Ballistic Missile", 100263),
)

# OpenPower's additional profile has no corresponding REFERENCE EUnitType/string ID.
OPENPOWER_UNIT_TYPE_EXTENSIONS = (
    UnitTypeOption("missile_defense", "Missile Defense (OpenPower)", None),
)

DESIGN_UNIT_TYPE_OPTIONS = REFERENCE_UNIT_TYPE_OPTIONS + OPENPOWER_UNIT_TYPE_EXTENSIONS
_OPTION_BY_ROLE = {option.role: option for option in DESIGN_UNIT_TYPE_OPTIONS}


def unit_type_options_for_roles(roles: Iterable[object]) -> tuple[UnitTypeOption, ...]:
    """Return available roles in REFERENCE order, followed by OpenPower extensions."""
    available = {canonical_role(role) for role in roles}
    available.discard("")

    options = [option for option in DESIGN_UNIT_TYPE_OPTIONS if option.role in available]
    known_roles = {option.role for option in options}
    for role in sorted(available - known_roles):
        label = role.replace("_", " ").title()
        options.append(UnitTypeOption(role, label, None))
    return tuple(options)


def source_unit_type_label(role: object) -> str:
    """Use the REFERENCE catalog label for mapped roles and preserve other OpenPower names."""
    option = _OPTION_BY_ROLE.get(canonical_role(role))
    return option.label if option is not None else str(role or "")
