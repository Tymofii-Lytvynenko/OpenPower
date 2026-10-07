"""Data-oriented policy values shared by covert lifecycle and resolution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True, slots=True)
class CovertSkillProfile:
    max_mission_risk: float
    success_bonus: float
    preparation_multiplier: float
    concealment: float
    upkeep_multiplier: float


SKILL_PROFILES: dict[str, CovertSkillProfile] = {
    "Recruit": CovertSkillProfile(0.0, 0.0, 1.20, 0.25, 0.75),
    "Regular": CovertSkillProfile(0.50, 0.12, 1.00, 0.43, 1.00),
    "Veteran": CovertSkillProfile(0.75, 0.24, 0.90, 0.61, 1.25),
    "Elite": CovertSkillProfile(1.00, 0.36, 0.80, 0.79, 1.50),
}
SKILL_LEVELS = tuple(SKILL_PROFILES)


def skill_profile(skill_level: Any) -> CovertSkillProfile:
    return SKILL_PROFILES.get(str(skill_level or ""), SKILL_PROFILES["Recruit"])


def domestic_security_coverage(
    active_cell_count: int,
    population: float,
    scenario: Mapping[str, Any],
) -> float:
    """Return bounded, diminishing coverage using scenario-overridable parameters."""

    population_floor = max(1.0, _finite(scenario.get("covert_security_population_floor"), 10_000.0))
    population_log_divisor = max(1.0, _finite(scenario.get("covert_security_population_log_divisor"), 7.0))
    scale_min = max(0.0, _finite(scenario.get("covert_security_population_scale_min"), 0.65))
    scale_max = max(scale_min, _finite(scenario.get("covert_security_population_scale_max"), 1.25))
    base_coverage = min(0.8, max(0.0, _finite(scenario.get("covert_security_base_coverage"), 0.45)))
    diminishing_retention = min(0.99, max(0.0, _finite(scenario.get("covert_security_diminishing_retention"), 0.72)))
    population_scale = min(
        scale_max,
        max(scale_min, math.log10(max(population_floor, _finite(population))) / population_log_divisor),
    )
    count = max(0, int(active_cell_count))
    return min(0.85, base_coverage * (1.0 - diminishing_retention**count) * population_scale)


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default
