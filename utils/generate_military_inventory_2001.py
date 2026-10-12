from __future__ import annotations

import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COUNTRY_DIR = ROOT / "modules" / "base" / "data" / "countries"
MILITARY_PATH = COUNTRY_DIR / "countries_mil.tsv"
DEVELOPMENT_PATH = COUNTRY_DIR / "countries_dem.tsv"

UNIT_ROLES = (
    "infantry",
    "infantry_vehicles",
    "air_defense",
    "mobile_launchers",
    "tanks",
    "artillery",
    "attack_helicopters",
    "transport_helicopters",
    "anti_submarine_helicopters",
    "fighters",
    "attack_aircraft",
    "bombers",
    "patrol_craft",
    "corvettes",
    "frigates",
    "destroyers",
    "attack_submarines",
    "ballistic_missile_submarines",
    "aircraft_carriers",
    "strategic_missiles",
)

CREW_FACTORS = {
    "infantry_vehicles": 3.0,
    "air_defense": 5.0,
    "mobile_launchers": 6.0,
    "tanks": 4.0,
    "artillery": 6.0,
    "attack_helicopters": 8.0,
    "transport_helicopters": 8.0,
    "anti_submarine_helicopters": 8.0,
    "fighters": 12.0,
    "attack_aircraft": 15.0,
    "bombers": 20.0,
    "patrol_craft": 10.0,
    "corvettes": 30.0,
    "frigates": 80.0,
    "destroyers": 250.0,
    "attack_submarines": 100.0,
    "ballistic_missile_submarines": 150.0,
    "aircraft_carriers": 1500.0,
}

LANDLOCKED = frozenset(
    "AFG AND ARM AUT AZE BDI BFA BLR BOL BWA CAF CHE CZE ETH HUN KAZ KGZ LAO LIE LSO LUX MDA MKD MLI MNG NER NPL PRY RWA SRB SSD SVK SWZ TCD TJK TKM UGA UZB ZMB ZWE".split()
)
INLAND_PATROL_COUNTRIES = frozenset({"AZE", "BOL", "KAZ", "TKM", "UGA"})
MISSILE_LAUNCHER_COUNTRIES = frozenset(
    "CHN EGY IND IRN IRQ ISR KAZ LBY PAK PRK RUS SAU SYR UKR VNM".split()
)
HEAVY_BOMBER_COUNTRIES = frozenset({"CHN", "RUS", "USA"})

NUCLEAR_MISSILE_COUNTS = {
    "CHN": 24,
    "RUS": 700,
    "USA": 550,
}
BALLISTIC_SUBMARINE_COUNTS = {
    "CHN": 1,
    "FRA": 4,
    "GBR": 4,
    "RUS": 15,
    "USA": 18,
}
AIRCRAFT_CARRIER_COUNTS = {
    "BRA": 1,
    "ESP": 1,
    "FRA": 1,
    "GBR": 3,
    "IND": 1,
    "ITA": 1,
    "RUS": 1,
    "THA": 1,
    "USA": 12,
}

# Public IISS-derived 2000–2003 regional tables anchor these country totals.
# Role splits for combined categories follow the game classes and remain estimates.
DOCUMENTED_INVENTORY_OVERRIDES = {
    "BHR": {"tanks": 106, "infantry_vehicles": 365, "artillery": 98, "attack_helicopters": 40, "fighters": 22, "attack_aircraft": 12, "corvettes": 1},
    "KWT": {"tanks": 385, "infantry_vehicles": 495, "artillery": 59, "attack_helicopters": 20, "fighters": 54, "attack_aircraft": 28},
    "OMN": {"tanks": 117, "infantry_vehicles": 183, "artillery": 115, "fighters": 12, "attack_aircraft": 28},
    "QAT": {"tanks": 44, "infantry_vehicles": 212, "artillery": 40, "attack_helicopters": 19, "fighters": 12, "attack_aircraft": 6},
    "SAU": {"tanks": 1055, "infantry_vehicles": 2870, "artillery": 448, "attack_helicopters": 33, "fighters": 266, "attack_aircraft": 151, "frigates": 4},
    "ARE": {"tanks": 331, "infantry_vehicles": 1053, "artillery": 270, "attack_helicopters": 49, "fighters": 45, "attack_aircraft": 56, "corvettes": 2},
    "IRQ": {"tanks": 2600, "infantry_vehicles": 3400, "artillery": 2100, "attack_helicopters": 62, "fighters": 200, "attack_aircraft": 116, "patrol_craft": 0, "corvettes": 0, "frigates": 0, "destroyers": 0, "attack_submarines": 0},
    "IRN": {"tanks": 1565, "infantry_vehicles": 1455, "artillery": 2395, "attack_helicopters": 69, "fighters": 180, "attack_aircraft": 126, "corvettes": 3, "attack_submarines": 6},
}

MAJOR_FORCE_OVERRIDES = {
    "AUS": {"tanks": 90, "infantry_vehicles": 1600, "fighters": 100, "attack_aircraft": 100, "frigates": 8, "destroyers": 3, "attack_submarines": 6},
    "BRA": {"tanks": 350, "infantry_vehicles": 1200, "fighters": 100, "attack_aircraft": 80, "frigates": 8, "corvettes": 7, "attack_submarines": 5},
    "CAN": {"tanks": 114, "infantry_vehicles": 1800, "fighters": 120, "attack_aircraft": 90, "frigates": 12, "destroyers": 4, "attack_submarines": 4},
    "CHN": {"tanks": 7000, "infantry_vehicles": 5000, "air_defense": 2500, "mobile_launchers": 700, "artillery": 14000, "attack_helicopters": 100, "transport_helicopters": 200, "anti_submarine_helicopters": 80, "fighters": 2000, "attack_aircraft": 500, "bombers": 200, "patrol_craft": 100, "corvettes": 50, "frigates": 40, "destroyers": 20, "attack_submarines": 50},
    "DEU": {"tanks": 2500, "infantry_vehicles": 8000, "air_defense": 500, "artillery": 2000, "attack_helicopters": 100, "transport_helicopters": 220, "anti_submarine_helicopters": 40, "fighters": 450, "attack_aircraft": 200, "frigates": 13, "attack_submarines": 14},
    "EGY": {"tanks": 3500, "infantry_vehicles": 4000, "air_defense": 800, "artillery": 2500, "attack_helicopters": 100, "transport_helicopters": 150, "fighters": 250, "attack_aircraft": 300, "corvettes": 10, "frigates": 8, "attack_submarines": 4},
    "ESP": {"tanks": 500, "infantry_vehicles": 2000, "artillery": 600, "fighters": 150, "attack_aircraft": 100, "corvettes": 6, "frigates": 10, "destroyers": 7, "attack_submarines": 4},
    "FRA": {"tanks": 1300, "infantry_vehicles": 6500, "air_defense": 300, "artillery": 2000, "attack_helicopters": 70, "transport_helicopters": 150, "anti_submarine_helicopters": 100, "fighters": 400, "attack_aircraft": 300, "patrol_craft": 30, "corvettes": 20, "frigates": 15, "destroyers": 12, "attack_submarines": 5},
    "GBR": {"tanks": 400, "infantry_vehicles": 5000, "air_defense": 200, "artillery": 1500, "attack_helicopters": 60, "transport_helicopters": 100, "anti_submarine_helicopters": 170, "fighters": 250, "attack_aircraft": 300, "patrol_craft": 40, "corvettes": 10, "frigates": 20, "destroyers": 12, "attack_submarines": 12},
    "GRC": {"tanks": 1500, "infantry_vehicles": 2000, "air_defense": 500, "artillery": 1200, "attack_helicopters": 30, "fighters": 300, "attack_aircraft": 200, "corvettes": 8, "frigates": 10, "destroyers": 8, "attack_submarines": 8},
    "IND": {"tanks": 3500, "infantry_vehicles": 2500, "air_defense": 1200, "mobile_launchers": 100, "artillery": 4000, "attack_helicopters": 20, "transport_helicopters": 200, "anti_submarine_helicopters": 100, "fighters": 800, "attack_aircraft": 300, "patrol_craft": 60, "corvettes": 15, "frigates": 10, "destroyers": 8, "attack_submarines": 16},
    "ISR": {"tanks": 4000, "infantry_vehicles": 6000, "air_defense": 800, "artillery": 2000, "attack_helicopters": 70, "fighters": 400, "attack_aircraft": 250, "patrol_craft": 30, "corvettes": 5, "frigates": 3, "attack_submarines": 3},
    "ITA": {"tanks": 700, "infantry_vehicles": 3000, "air_defense": 250, "artillery": 1200, "attack_helicopters": 60, "transport_helicopters": 150, "anti_submarine_helicopters": 100, "fighters": 350, "attack_aircraft": 250, "patrol_craft": 40, "corvettes": 10, "frigates": 10, "destroyers": 4, "attack_submarines": 8},
    "JPN": {"tanks": 900, "infantry_vehicles": 7000, "air_defense": 1000, "artillery": 1500, "attack_helicopters": 100, "transport_helicopters": 100, "anti_submarine_helicopters": 200, "fighters": 300, "attack_aircraft": 150, "patrol_craft": 50, "corvettes": 15, "frigates": 10, "destroyers": 30, "attack_submarines": 16},
    "KOR": {"tanks": 2300, "infantry_vehicles": 2400, "air_defense": 600, "artillery": 2500, "attack_helicopters": 50, "transport_helicopters": 100, "anti_submarine_helicopters": 50, "fighters": 400, "attack_aircraft": 300, "patrol_craft": 50, "corvettes": 20, "frigates": 9, "destroyers": 5, "attack_submarines": 10},
    "NLD": {"tanks": 700, "infantry_vehicles": 2000, "air_defense": 250, "artillery": 500, "attack_helicopters": 25, "transport_helicopters": 60, "anti_submarine_helicopters": 40, "fighters": 100, "attack_aircraft": 100, "patrol_craft": 30, "corvettes": 5, "frigates": 8, "destroyers": 5, "attack_submarines": 4},
    "PAK": {"tanks": 2200, "infantry_vehicles": 2000, "air_defense": 500, "mobile_launchers": 150, "artillery": 2500, "attack_helicopters": 50, "transport_helicopters": 100, "anti_submarine_helicopters": 50, "fighters": 400, "attack_aircraft": 250, "patrol_craft": 30, "corvettes": 8, "frigates": 6, "attack_submarines": 5},
    "PRK": {"tanks": 3500, "infantry_vehicles": 2500, "air_defense": 1800, "mobile_launchers": 500, "artillery": 10000, "attack_helicopters": 20, "transport_helicopters": 40, "anti_submarine_helicopters": 10, "fighters": 600, "attack_aircraft": 300, "bombers": 80, "patrol_craft": 100, "corvettes": 40, "frigates": 10, "destroyers": 2, "attack_submarines": 20},
    "RUS": {"tanks": 9000, "infantry_vehicles": 14000, "air_defense": 3000, "mobile_launchers": 600, "artillery": 13000, "attack_helicopters": 450, "transport_helicopters": 800, "anti_submarine_helicopters": 250, "fighters": 1800, "attack_aircraft": 1000, "bombers": 250, "patrol_craft": 60, "corvettes": 25, "frigates": 15, "destroyers": 10, "attack_submarines": 40},
    "TUR": {"tanks": 4200, "infantry_vehicles": 3500, "air_defense": 600, "artillery": 2800, "attack_helicopters": 30, "transport_helicopters": 100, "anti_submarine_helicopters": 30, "fighters": 500, "attack_aircraft": 300, "patrol_craft": 40, "corvettes": 10, "frigates": 16, "attack_submarines": 13},
    "TWN": {"tanks": 1000, "infantry_vehicles": 3000, "air_defense": 1000, "artillery": 1000, "attack_helicopters": 40, "transport_helicopters": 60, "anti_submarine_helicopters": 70, "fighters": 500, "attack_aircraft": 200, "patrol_craft": 70, "corvettes": 10, "frigates": 6, "destroyers": 4, "attack_submarines": 4},
    "UKR": {"tanks": 4000, "infantry_vehicles": 6000, "air_defense": 1500, "mobile_launchers": 100, "artillery": 5000, "attack_helicopters": 100, "transport_helicopters": 200, "fighters": 300, "attack_aircraft": 300, "patrol_craft": 30, "corvettes": 5, "frigates": 2},
    "USA": {"tanks": 8000, "infantry_vehicles": 24000, "air_defense": 1500, "artillery": 5000, "attack_helicopters": 720, "transport_helicopters": 1100, "anti_submarine_helicopters": 700, "fighters": 2400, "attack_aircraft": 1200, "bombers": 190, "patrol_craft": 60, "frigates": 30, "destroyers": 55, "attack_submarines": 54},
}

STRATEGIC_OVERRIDES = {
    "CHN": {"ballistic_missile_submarines": 1, "strategic_missiles": 24},
    "FRA": {"ballistic_missile_submarines": 4},
    "GBR": {"ballistic_missile_submarines": 4},
    "RUS": {"ballistic_missile_submarines": 15, "aircraft_carriers": 1, "strategic_missiles": 700},
    "USA": {"ballistic_missile_submarines": 18, "aircraft_carriers": 12, "strategic_missiles": 550},
}

# These forces had no conventional heavy inventory in the 2001 scenario. Keeping
# their personnel as infantry prevents the generic manpower model from inventing armor or air fleets.
LIGHT_FORCE_OVERRIDES = {
    "HTI": {role: 0 for role in UNIT_ROLES if role != "infantry"},
    "KOS": {role: 0 for role in UNIT_ROLES if role != "infantry"},
    "LBR": {
        "infantry_vehicles": 0,
        "air_defense": 0,
        "mobile_launchers": 0,
        "tanks": 0,
        "artillery": 20,
        "attack_helicopters": 0,
        "transport_helicopters": 0,
        "anti_submarine_helicopters": 0,
        "fighters": 0,
        "attack_aircraft": 0,
        "bombers": 0,
        "patrol_craft": 0,
        "corvettes": 0,
        "frigates": 0,
        "destroyers": 0,
        "attack_submarines": 0,
    },
    "PSE": {role: 0 for role in UNIT_ROLES if role != "infantry"},
    "SLE": {
        "infantry_vehicles": 0,
        "air_defense": 0,
        "mobile_launchers": 0,
        "tanks": 0,
        "artillery": 10,
        "attack_helicopters": 0,
        "transport_helicopters": 0,
        "anti_submarine_helicopters": 0,
        "fighters": 0,
        "attack_aircraft": 0,
        "bombers": 0,
        "patrol_craft": 0,
        "corvettes": 0,
        "frigates": 0,
        "destroyers": 0,
        "attack_submarines": 0,
    },
    "SOM": {role: 0 for role in UNIT_ROLES if role != "infantry"},
    "SSD": {role: 0 for role in UNIT_ROLES if role != "infantry"},
}


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def _round_count(value: float) -> int:
    return max(0, int(math.floor(value + 0.5)))


def _base_inventory(country_id: str, personnel: int, development: float) -> dict[str, int]:
    counts = {role: 0 for role in UNIT_ROLES}
    if personnel <= 0:
        return counts

    scale = 0.78 + (0.34 * development)
    if personnel >= 2500:
        counts["infantry_vehicles"] = _round_count(personnel * 0.0060 * scale)
    if personnel >= 5000:
        counts["air_defense"] = _round_count(personnel * 0.0008 * scale)
        counts["tanks"] = _round_count(personnel * 0.0018 * scale)
        counts["artillery"] = _round_count(personnel * 0.0025 * scale)
    if personnel >= 20000:
        counts["mobile_launchers"] = _round_count(personnel * 0.00012 * scale)
        counts["attack_helicopters"] = _round_count(personnel * 0.00018 * scale)
        counts["transport_helicopters"] = _round_count(personnel * 0.00028 * scale)
        counts["fighters"] = _round_count(personnel * 0.00050 * scale)
        counts["attack_aircraft"] = _round_count(personnel * 0.00030 * scale)
    if country_id in HEAVY_BOMBER_COUNTRIES:
        counts["bombers"] = _round_count(personnel * 0.00015 * scale)

    if country_id not in LANDLOCKED or country_id in INLAND_PATROL_COUNTRIES:
        if personnel >= 1000:
            counts["patrol_craft"] = max(1, _round_count(personnel * 0.00015 * scale))
        if personnel >= 20000:
            counts["corvettes"] = _round_count(personnel * 0.00002 * scale)
        if personnel >= 50000 and development >= 0.55:
            counts["frigates"] = _round_count(personnel * 0.000015 * scale)
        if personnel >= 120000 and development >= 0.70:
            counts["destroyers"] = _round_count(personnel * 0.00001 * scale)
        if personnel >= 100000 and development >= 0.70:
            counts["attack_submarines"] = _round_count(personnel * 0.000008 * scale)
        if personnel >= 50000 and development >= 0.55:
            counts["anti_submarine_helicopters"] = _round_count(personnel * 0.00005 * scale)

    if country_id in MISSILE_LAUNCHER_COUNTRIES and counts["mobile_launchers"] == 0:
        counts["mobile_launchers"] = max(1, _round_count(personnel * 0.00010))
    counts["ballistic_missile_submarines"] = BALLISTIC_SUBMARINE_COUNTS.get(country_id, 0)
    counts["aircraft_carriers"] = AIRCRAFT_CARRIER_COUNTS.get(country_id, 0)
    counts["strategic_missiles"] = NUCLEAR_MISSILE_COUNTS.get(country_id, 0)
    return counts


def _support_staff(personnel: int, counts: dict[str, int]) -> int:
    active_roles = [role for role, factor in CREW_FACTORS.items() if counts.get(role, 0) > 0 and factor > 0]
    raw_staff = sum(counts[role] * CREW_FACTORS[role] for role in active_roles)
    support_limit = _round_count(personnel * 0.40)
    support_staff = min(support_limit, _round_count(raw_staff))
    if active_roles and personnel >= len(active_roles):
        support_staff = max(support_staff, min(support_limit, len(active_roles)))
    return support_staff


def main() -> None:
    military_rows = _read_tsv(MILITARY_PATH)
    development_by_country = {
        row["id"].strip().upper(): float(row.get("human_dev") or 0.45)
        for row in _read_tsv(DEVELOPMENT_PATH)
    }
    field_names = ["id", "military_count"] + [
        f"military_{role}_quantity_2001" for role in UNIT_ROLES
    ]

    output_rows = []
    for source in military_rows:
        country_id = source["id"].strip().upper()
        personnel = max(0, int(float(source.get("military_count") or 0)))
        counts = _base_inventory(country_id, personnel, development_by_country.get(country_id, 0.45))
        for profile in (
            DOCUMENTED_INVENTORY_OVERRIDES,
            MAJOR_FORCE_OVERRIDES,
            STRATEGIC_OVERRIDES,
            LIGHT_FORCE_OVERRIDES,
        ):
            for role, count in profile.get(country_id, {}).items():
                counts[role] = max(0, int(count))
        counts["infantry"] = max(0, personnel - _support_staff(personnel, counts))
        output_rows.append(
            {
                "id": country_id,
                "military_count": personnel,
                **{
                    f"military_{role}_quantity_2001": counts[role]
                    for role in UNIT_ROLES
                },
            }
        )

    with MILITARY_PATH.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=field_names, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Wrote 2001 military inventories for {len(output_rows)} country roster entries.")


if __name__ == "__main__":
    main()
