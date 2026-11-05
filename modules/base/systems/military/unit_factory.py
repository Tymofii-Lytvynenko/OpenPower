"""Build normalized unit records and allocate deterministic unit identifiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.base.systems.military.capability_catalog import get_role_profile
from modules.base.systems.military.movement_constants import NO_TARGET_REGION
from src.core.map.geo import GeoCoordinate


DEFAULT_UNIT_TYPE = "army"


@dataclass(frozen=True)
class UnitRecordSpec:
    unit_id: str
    owner: str
    unit_type: str
    strength: int
    region_id: int
    geo: GeoCoordinate
    current_minute: int
    design_id: str = ""
    training_level: str = "Recruit"
    equipment_quantity: int | None = None


class UnitFactory:
    """Create normalized unit records without coupling callers to table details."""

    def next_id(
        self,
        unit_rows: list[dict[str, Any]],
        country_tag: str,
        unit_type: str,
    ) -> str:
        clean_unit_type = unit_type or DEFAULT_UNIT_TYPE
        prefix = f"{country_tag}-{clean_unit_type}"
        existing_ids = {str(row["id"]) for row in unit_rows}
        index = 1
        while True:
            unit_id = f"{prefix}-{index:03d}"
            if unit_id not in existing_ids:
                return unit_id
            index += 1

    def create_from_spec(self, spec: UnitRecordSpec) -> dict[str, Any]:
        return self.create(
            unit_id=spec.unit_id,
            owner=spec.owner,
            unit_type=spec.unit_type,
            strength=spec.strength,
            region_id=spec.region_id,
            geo=spec.geo,
            current_minute=spec.current_minute,
            design_id=spec.design_id,
            training_level=spec.training_level,
            equipment_quantity=spec.equipment_quantity,
        )

    def create(
        self,
        unit_id: str,
        owner: str,
        unit_type: str,
        strength: int,
        region_id: int,
        geo: GeoCoordinate,
        current_minute: int,
        design_id: str = "",
        training_level: str = "Recruit",
        equipment_quantity: int | None = None,
    ) -> dict[str, Any]:
        safe_strength = max(1, int(strength))
        return {
            "id": unit_id,
            "owner": owner,
            "unit_type": unit_type or DEFAULT_UNIT_TYPE,
            "design_id": str(design_id or ""),
            "unit_domain": get_role_profile(unit_type or DEFAULT_UNIT_TYPE).domain,
            "strength": safe_strength,
            "equipment_quantity": max(
                0,
                int(safe_strength if equipment_quantity is None else equipment_quantity),
            ),
            "current_region_id": int(region_id),
            "latitude": float(geo.latitude),
            "longitude": float(geo.longitude),
            "source_region_id": int(region_id),
            "source_latitude": float(geo.latitude),
            "source_longitude": float(geo.longitude),
            "target_region_id": NO_TARGET_REGION,
            "target_latitude": float(geo.latitude),
            "target_longitude": float(geo.longitude),
            "departed_at_minute": int(current_minute),
            "arrival_at_minute": int(current_minute),
            "movement_progress": 0.0,
            "is_moving": False,
            "engagement_mode": "",
            "readiness_status": "parked",
            "readiness_transition_id": "",
            "readiness_progress": 0.0,
            "readiness_eta_minute": 0,
            "training_level": training_level,
            "training_state": "",
            "training_progress": 0.0,
            "training_facility_id": "",
            "training_location_region_id": 0,
            "combat_posture": "hold",
            "combat_strength_modifier": 1.0,
            "war_exhaustion_modifier": 1.0,
            "combat_casualty_modifier": 1.0,
            "combat_defense_modifier": 1.0,
            "combat_attack_risk_modifier": 1.0,
            "combat_readiness_modifier": 1.0,
            "combat_holding_modifier": 1.0,
            "combat_counterattack_modifier": 1.0,
            "cohesion": 1.0,
            "reorganization_until_minute": 0,
            "production_order_id": "",
            "foreign_order_id": "",
            "original_cost": 0.0,
            "unit_lifecycle": "available",
        }
