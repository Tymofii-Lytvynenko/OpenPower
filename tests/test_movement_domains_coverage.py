from modules.base.systems.military.movement_domains import (
    domain_route_compatible,
    region_is_water,
)


def test_region_water_classification_falls_back_to_region_type_and_terrain() -> None:
    assert region_is_water({"region_type": "  OCEAN  "})
    assert region_is_water({"terrain": "naval_zone"})
    assert not region_is_water({"region_type": "land", "terrain": "plains"})


def test_naval_units_are_rejected_from_inland_non_port_regions() -> None:
    region = {"region_type": "land", "is_port": False, "is_coastal": False}

    compatible, reason = domain_route_compatible(
        "naval", region, False, False, [region]
    )

    assert not compatible
    assert "sea zone, port" in reason


def test_strategic_assets_cannot_use_conventional_movement() -> None:
    region = {"is_water": False}

    compatible, reason = domain_route_compatible(
        "strategic", region, False, False, [region]
    )

    assert not compatible
    assert "conventional movement orders" in reason
