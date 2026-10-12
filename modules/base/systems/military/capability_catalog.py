"""Data-driven default military roles and bounded capability projections."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping


CAPABILITY_BOUNDS: dict[str, tuple[float, float]] = {
    "hit_points": (0.0, 10000.0),
    "gun_fire_rate": (-1.0, 100.0),
    "missile_fire_rate": (-1.0, 100.0),
    "missile_rearm_delay": (-1.0, 100000.0),
    "speed": (0.0, 2500.0),
    "maneuverability": (0.0, 100.0),
    "sensors": (0.0, 40000.0),
    "gun_range": (0.0, 1000.0),
    "gun_precision": (0.0, 1.0),
    "gun_damage": (0.0, 10000.0),
    "missile_payload": (0.0, 100000.0),
    "missile_range": (0.0, 40000.0),
    "missile_precision": (0.0, 1.0),
    "missile_damage": (0.0, 10000.0),
    "stealth": (0.0, 1.0),
    "countermeasures": (0.0, 100.0),
    "armor": (0.0, 2000.0),
}

FIXED_ROLE_CHARACTERISTICS: dict[str, str] = {
    "role": "Canonical force role; a national design cannot change its role identity.",
    "domain": "Deployment domain; a national design cannot move a role into another domain.",
    "valid_targets": "Configured target interaction matrix; a national design cannot add target categories.",
    "vulnerabilities": "Configured counter relationships; a national design cannot erase role vulnerabilities.",
}

_CAPABILITY_DESCRIPTIONS: dict[str, tuple[str, str, str]] = {
    "hit_points": ("Base hit points", "Represents the unit type's base hit-point pool.", "A design value is descriptive until the battle projection consumes unit hit points."),
    "gun_fire_rate": ("Gun rate", "Represents the unit type's gun firing rate; -1 means no gun weapon.", "This game-scale value is descriptive until the battle projection consumes firing rate."),
    "missile_fire_rate": ("Missile rate", "Represents the unit type's missile firing rate; -1 means no missile weapon.", "This game-scale value is descriptive until the battle projection consumes firing rate."),
    "missile_rearm_delay": ("Rearm delay", "Represents the unit type's missile rearm delay; -1 means no missile rearm cycle.", "This game-scale value is descriptive until the battle projection consumes rearm delay."),
    "speed": ("km/h", "Represents the role's movement speed.", "A design value by itself does not change movement routing."),
    "maneuverability": ("index (0–100)", "Represents ability to reposition or evade.", "A design value is bounded and does not change battle-round timing."),
    "sensors": ("km", "Represents detection and targeting reach.", "A design value does not reveal foreign units without authorized intelligence."),
    "gun_range": ("km", "Represents the configured gun engagement range.", "Range is descriptive until a scenario enables range-based targeting."),
    "gun_precision": ("fraction (0–1)", "Represents the share of gun firepower applied accurately.", "Precision contributes only where the battle projection consumes gun capability."),
    "gun_damage": ("damage points", "Represents role-specific gun damage potential.", "Damage contributes only where the battle projection consumes gun capability."),
    "missile_payload": ("kg", "Represents missile payload capacity.", "Payload is descriptive and does not create additional weapon inventory."),
    "missile_range": ("km", "Represents the configured missile engagement range.", "Range is descriptive until a scenario enables range-based targeting."),
    "missile_precision": ("fraction (0–1)", "Represents the share of missile firepower applied accurately.", "Precision contributes only where the battle projection consumes missile capability."),
    "missile_damage": ("damage points", "Represents role-specific missile damage potential.", "Damage contributes only where the battle projection consumes missile capability."),
    "stealth": ("fraction (0–1)", "Represents signature reduction against detection.", "Stealth is descriptive until a scenario enables detection or targeting effects."),
    "countermeasures": ("index (0–100)", "Represents defensive countermeasure capacity.", "A design value is descriptive until a scenario enables countermeasure resolution."),
    "armor": ("protection points", "Represents the role's protection against damage.", "Armor is descriptive until a scenario enables armor-specific mitigation."),
}

CAPABILITY_METADATA: dict[str, dict[str, Any]] = {
    name: {
        "unit": description[0],
        "adjustability": "design_variable",
        "minimum": CAPABILITY_BOUNDS[name][0],
        "maximum": CAPABILITY_BOUNDS[name][1],
        "prerequisite": "The design's configured research_requirements_json is validated by the production system; this characteristic adds no separate gate.",
        "production_effect": "Does not auto-price the design; explicit design cost and maintenance remain authoritative for production.",
        "interaction": description[1],
        "zero_semantics": "Zero means neutral or not applicable for this role; it is not an inferred advantage.",
        "effect_scope": description[2],
    }
    for name, description in _CAPABILITY_DESCRIPTIONS.items()
}

TRAINING_LEVELS = ("Recruit", "Regular", "Veteran", "Elite")
TRAINING_BONUS_DEFAULTS = {"Recruit": 0.0, "Regular": 0.05, "Veteran": 0.10, "Elite": 0.15}
TRAINING_AFFECTED_CAPABILITIES = frozenset({
    "speed", "maneuverability", "sensors", "gun_precision", "missile_precision", "stealth", "countermeasures",
})


@dataclass(frozen=True)
class UnitRoleProfile:
    role: str
    domain: str
    capabilities: Mapping[str, float]
    valid_targets: tuple[str, ...]
    vulnerabilities: tuple[str, ...]


def _profile(
    role: str,
    domain: str,
    speed: float,
    armor: float,
    gun_range: float,
    gun_damage: float,
    missile_range: float,
    missile_damage: float,
    targets: tuple[str, ...],
    vulnerabilities: tuple[str, ...],
    *,
    maneuverability: float = 20.0,
    sensors: float = 50.0,
    gun_precision: float = 0.5,
    missile_precision: float = 0.5,
    missile_payload: float = 0.0,
    stealth: float = 0.0,
    countermeasures: float = 0.0,
    hit_points: float = 100.0,
    gun_fire_rate: float = -1.0,
    missile_fire_rate: float = -1.0,
    missile_rearm_delay: float = -1.0,
) -> UnitRoleProfile:
    return UnitRoleProfile(
        role=role,
        domain=domain,
        capabilities={
            "hit_points": hit_points,
            "gun_fire_rate": gun_fire_rate,
            "missile_fire_rate": missile_fire_rate,
            "missile_rearm_delay": missile_rearm_delay,
            "speed": speed,
            "maneuverability": maneuverability,
            "sensors": sensors,
            "gun_range": gun_range,
            "gun_precision": gun_precision,
            "gun_damage": gun_damage,
            "missile_payload": missile_payload,
            "missile_range": missile_range,
            "missile_precision": missile_precision,
            "missile_damage": missile_damage,
            "stealth": stealth,
            "countermeasures": countermeasures,
            "armor": armor,
        },
        valid_targets=targets,
        vulnerabilities=vulnerabilities,
    )


DEFAULT_ROLE_PROFILES: dict[str, UnitRoleProfile] = {
    "infantry": _profile("infantry", "land", 8, 2, 2, 1, 0, 0, ("infantry", "artillery", "air_defense"), ("armor", "air"), maneuverability=35, sensors=10, stealth=0.1, hit_points=5, gun_fire_rate=3),
    "infantry_vehicles": _profile("infantry_vehicles", "land", 65, 12, 3, 3, 8, 2, ("infantry", "armor", "artillery"), ("air", "anti_armor"), maneuverability=40, sensors=25, countermeasures=5, hit_points=100, gun_fire_rate=5),
    "air_defense": _profile("air_defense", "land", 55, 15, 2, 2, 100, 3, ("air", "missile"), ("artillery", "armor"), maneuverability=25, sensors=180, hit_points=80, gun_fire_rate=4, missile_fire_rate=4, missile_rearm_delay=10),
    "mobile_launchers": _profile("mobile_launchers", "land", 45, 8, 0, 0, 12000, 10, ("strategic_target",), ("air", "reconnaissance"), maneuverability=20, sensors=50, stealth=0.2, hit_points=80, missile_fire_rate=3, missile_rearm_delay=10),
    "tanks": _profile("tanks", "land", 70, 80, 5, 8, 8, 4, ("infantry", "armor", "artillery"), ("air", "anti_armor"), maneuverability=30, sensors=35, hit_points=200, gun_fire_rate=0.1),
    "artillery": _profile("artillery", "land", 45, 10, 40, 6, 0, 0, ("infantry", "armor", "artillery", "infrastructure"), ("air", "armor"), maneuverability=15, sensors=20, hit_points=80, gun_fire_rate=0.05),
    "attack_helicopters": _profile("attack_helicopters", "air", 280, 12, 4, 4, 12, 5, ("infantry", "armor", "artillery", "ships"), ("air_defense", "fighters"), maneuverability=65, sensors=60, countermeasures=20, hit_points=160, gun_fire_rate=10, missile_fire_rate=3, missile_rearm_delay=40),
    "transport_helicopters": _profile("transport_helicopters", "air", 260, 5, 0, 0, 0, 0, ("transport",), ("air_defense", "fighters"), maneuverability=55, sensors=30, hit_points=120, gun_fire_rate=8),
    "anti_submarine_helicopters": _profile("anti_submarine_helicopters", "naval", 250, 6, 2, 1, 10, 3, ("submarines", "ships"), ("air_defense", "fighters"), maneuverability=60, sensors=200, hit_points=120, gun_fire_rate=8, missile_fire_rate=3, missile_rearm_delay=40),
    "fighters": _profile("fighters", "air", 2200, 15, 5, 3, 120, 5, ("air", "bombers", "missile"), ("air_defense", "fighters"), maneuverability=80, sensors=250, stealth=0.05, countermeasures=35, hit_points=40, gun_fire_rate=100, missile_fire_rate=5, missile_rearm_delay=60),
    "attack_aircraft": _profile("attack_aircraft", "air", 900, 18, 8, 5, 35, 6, ("infantry", "armor", "artillery", "ships"), ("air_defense", "fighters"), maneuverability=45, sensors=120, countermeasures=25, hit_points=50, gun_fire_rate=100, missile_fire_rate=5, missile_rearm_delay=60),
    "bombers": _profile("bombers", "air", 1000, 25, 5, 5, 8000, 8, ("infrastructure", "strategic_target", "ships"), ("fighters", "air_defense"), maneuverability=30, sensors=180, missile_payload=10000, countermeasures=30, hit_points=80, missile_fire_rate=4, missile_rearm_delay=120),
    "patrol_craft": _profile("patrol_craft", "naval", 55, 10, 20, 2, 30, 2, ("ships", "submarines"), ("air", "destroyers"), maneuverability=45, sensors=80, hit_points=400, gun_fire_rate=1, missile_fire_rate=5, missile_rearm_delay=1440),
    "corvettes": _profile("corvettes", "naval", 45, 25, 25, 4, 120, 4, ("ships", "submarines", "air"), ("air", "destroyers"), maneuverability=35, sensors=140, countermeasures=15, hit_points=800, gun_fire_rate=0.5, missile_fire_rate=10, missile_rearm_delay=1440),
    "frigates": _profile("frigates", "naval", 35, 45, 30, 5, 250, 5, ("ships", "submarines", "air", "missile"), ("submarines", "bombers"), maneuverability=30, sensors=250, countermeasures=25, hit_points=1000, gun_fire_rate=0.5, missile_fire_rate=10, missile_rearm_delay=1440),
    "destroyers": _profile("destroyers", "naval", 35, 70, 35, 7, 500, 8, ("ships", "submarines", "air", "missile"), ("submarines", "bombers"), maneuverability=25, sensors=400, countermeasures=35, hit_points=1500, gun_fire_rate=0.5, missile_fire_rate=10, missile_rearm_delay=1440),
    "attack_submarines": _profile("attack_submarines", "naval", 30, 40, 10, 2, 200, 8, ("ships", "submarines"), ("anti_submarine", "destroyers"), maneuverability=20, sensors=180, stealth=0.75, hit_points=500, missile_fire_rate=0.2, missile_rearm_delay=4320),
    "ballistic_missile_submarines": _profile("ballistic_missile_submarines", "naval", 25, 50, 0, 0, 12000, 10, ("strategic_target",), ("anti_submarine", "destroyers"), maneuverability=15, sensors=100, stealth=0.85, missile_payload=100000, hit_points=600, missile_rearm_delay=43200),
    "aircraft_carriers": _profile("aircraft_carriers", "naval", 30, 100, 5, 5, 300, 7, ("ships", "air"), ("submarines", "bombers"), maneuverability=15, sensors=300, countermeasures=30, hit_points=4000, missile_fire_rate=0.4, missile_rearm_delay=60),
    "strategic_missiles": _profile("strategic_missiles", "strategic", 24000, 0, 0, 0, 40000, 10, ("military", "civilian", "strategic_target"), ("missile_defense",), maneuverability=0, sensors=0, missile_precision=0.8, missile_payload=100000, hit_points=1),
    "missile_defense": _profile("missile_defense", "strategic", 0, 0, 0, 0, 5000, 1, ("missile",), ("saturation",), maneuverability=0, sensors=5000, missile_precision=0.8),
}

ROLE_ALIASES = {
    "army": "infantry",
    "infantry_vehicle": "infantry_vehicles",
    "infantry_vehicle_brigade": "infantry_vehicles",
    "artillery_gun": "artillery",
    "ifv": "infantry_vehicles",
    "apc": "infantry_vehicles",
    "air_defence": "air_defense",
    "mobile_launcher": "mobile_launchers",
    "tank": "tanks",
    "artillery_brigade": "artillery",
    "transport_helicopter": "transport_helicopters",
    "attack_helicopter": "attack_helicopters",
    "asw_helicopter": "anti_submarine_helicopters",
    "anti_submarine_helicopter": "anti_submarine_helicopters",
    "fighter_aircraft": "fighters",
    "fighter": "fighters",
    "bomber": "bombers",
    "patrol_boat": "patrol_craft",
    "corvette": "corvettes",
    "frigate": "frigates",
    "destroyer": "destroyers",
    "attack_submarine": "attack_submarines",
    "ballistic_missile_submarine": "ballistic_missile_submarines",
    "aircraft_carrier": "aircraft_carriers",
    "strategic_missile": "strategic_missiles",
    "ballistic_missile": "strategic_missiles",
}


def canonical_role(value: Any) -> str:
    role = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return ROLE_ALIASES.get(role, role)


def get_role_profile(role: Any, domain_hint: Any = "") -> UnitRoleProfile:
    canonical = canonical_role(role)
    known = DEFAULT_ROLE_PROFILES.get(canonical)
    if known is not None:
        return known
    domain = _normalize_domain(domain_hint)
    return _profile(
        canonical or "generic_unit",
        domain,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        ("generic",),
        ("generic",),
    )


def project_capabilities(profile: UnitRoleProfile, overrides: Mapping[str, Any] | None = None) -> dict[str, float]:
    """Apply bounded variable design values over the fixed role baseline."""

    requested = overrides or {}
    result: dict[str, float] = {}
    for key, (minimum, maximum) in CAPABILITY_BOUNDS.items():
        value = _finite(requested.get(key, profile.capabilities.get(key, minimum)))
        result[key] = min(maximum, max(minimum, value))
    return result


def training_bonus(level: Any, configured: Mapping[str, Any] | None = None) -> float:
    normalized = str(level or "Recruit").strip().title()
    if normalized not in TRAINING_LEVELS:
        normalized = "Recruit"
    source = configured or TRAINING_BONUS_DEFAULTS
    return min(0.5, max(0.0, _finite(source.get(normalized, TRAINING_BONUS_DEFAULTS[normalized]))))


def trained_capabilities(
    capabilities: Mapping[str, Any],
    level: Any,
    configured_bonus: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    bonus = training_bonus(level, configured_bonus)
    result = {key: _finite(value) for key, value in capabilities.items() if key in CAPABILITY_BOUNDS}
    for key in TRAINING_AFFECTED_CAPABILITIES:
        if key in result:
            minimum, maximum = CAPABILITY_BOUNDS[key]
            result[key] = min(maximum, max(minimum, result[key] * (1.0 + bonus)))
    return result


def researched_capabilities(
    capabilities: Mapping[str, Any],
    research_level: Any,
    configured_bonus: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """Apply optional per-level research improvements without changing role identity."""

    result = {key: _finite(value) for key, value in capabilities.items() if key in CAPABILITY_BOUNDS}
    levels = max(0, _integer(research_level))
    if levels == 0 or not isinstance(configured_bonus, Mapping):
        return result
    for key, raw_config in configured_bonus.items():
        if key not in result:
            continue
        if isinstance(raw_config, Mapping):
            per_level = max(0.0, _finite(raw_config.get("per_level")))
            maximum_bonus = min(2.0, max(0.0, _finite(raw_config.get("max_bonus", 0.5))))
        else:
            per_level = max(0.0, _finite(raw_config))
            maximum_bonus = 0.5
        bonus = min(maximum_bonus, levels * per_level)
        minimum, maximum = CAPABILITY_BOUNDS[key]
        result[key] = min(maximum, max(minimum, result[key] * (1.0 + bonus)))
    return result


def _normalize_domain(value: Any) -> str:
    normalized = str(value or "land").strip().lower()
    return normalized if normalized in {"land", "air", "naval", "strategic"} else "land"


def _finite(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
