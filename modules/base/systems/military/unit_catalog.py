from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MilitaryUnitType:
    role: str
    display_name: str
    quantity_column: str
    crew_factor: float
    unit_cost: float
    maintenance_cost: float


MILITARY_UNIT_TYPES = (
    MilitaryUnitType("infantry", "Infantry", "military_infantry_quantity_2001", 0.0, 1_500.0, 300.0),
    MilitaryUnitType("infantry_vehicles", "Infantry Vehicle", "military_infantry_vehicles_quantity_2001", 3.0, 1_500_000.0, 90_000.0),
    MilitaryUnitType("air_defense", "Air Defense", "military_air_defense_quantity_2001", 5.0, 2_000_000.0, 120_000.0),
    MilitaryUnitType("mobile_launchers", "Mobile Launcher", "military_mobile_launchers_quantity_2001", 6.0, 5_000_000.0, 250_000.0),
    MilitaryUnitType("tanks", "Tank", "military_tanks_quantity_2001", 4.0, 3_000_000.0, 180_000.0),
    MilitaryUnitType("artillery", "Artillery Gun", "military_artillery_quantity_2001", 6.0, 800_000.0, 55_000.0),
    MilitaryUnitType("attack_helicopters", "Attack Helicopter", "military_attack_helicopters_quantity_2001", 8.0, 18_000_000.0, 1_200_000.0),
    MilitaryUnitType("transport_helicopters", "Transport Helicopter", "military_transport_helicopters_quantity_2001", 8.0, 12_000_000.0, 800_000.0),
    MilitaryUnitType("anti_submarine_helicopters", "ASW Helicopter", "military_anti_submarine_helicopters_quantity_2001", 8.0, 22_000_000.0, 1_500_000.0),
    MilitaryUnitType("fighters", "Fighter Aircraft", "military_fighters_quantity_2001", 12.0, 35_000_000.0, 2_500_000.0),
    MilitaryUnitType("attack_aircraft", "Attack Aircraft", "military_attack_aircraft_quantity_2001", 15.0, 30_000_000.0, 2_200_000.0),
    MilitaryUnitType("bombers", "Bomber", "military_bombers_quantity_2001", 20.0, 100_000_000.0, 7_000_000.0),
    MilitaryUnitType("patrol_craft", "Patrol Craft", "military_patrol_craft_quantity_2001", 10.0, 10_000_000.0, 600_000.0),
    MilitaryUnitType("corvettes", "Corvette", "military_corvettes_quantity_2001", 30.0, 100_000_000.0, 6_000_000.0),
    MilitaryUnitType("frigates", "Frigate", "military_frigates_quantity_2001", 80.0, 250_000_000.0, 15_000_000.0),
    MilitaryUnitType("destroyers", "Destroyer", "military_destroyers_quantity_2001", 250.0, 750_000_000.0, 45_000_000.0),
    MilitaryUnitType("attack_submarines", "Attack Submarine", "military_attack_submarines_quantity_2001", 100.0, 1_000_000_000.0, 60_000_000.0),
    MilitaryUnitType("ballistic_missile_submarines", "Ballistic Missile Submarine", "military_ballistic_missile_submarines_quantity_2001", 150.0, 2_000_000_000.0, 120_000_000.0),
    MilitaryUnitType("aircraft_carriers", "Aircraft Carrier", "military_aircraft_carriers_quantity_2001", 1_500.0, 4_000_000_000.0, 240_000_000.0),
    MilitaryUnitType("strategic_missiles", "Ballistic Missile", "military_strategic_missiles_quantity_2001", 0.0, 50_000_000.0, 1_000_000.0),
)


MILITARY_UNIT_TYPE_BY_ROLE = {unit_type.role: unit_type for unit_type in MILITARY_UNIT_TYPES}
