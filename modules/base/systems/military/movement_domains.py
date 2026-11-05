"""Common terrain/domain checks for movement planning and invasion preflight."""
from modules.base.systems.military.capability_catalog import get_role_profile


def unit_domain(unit):
    domain = str(unit.get("unit_domain") or "").strip().lower()
    return domain if domain in {"land", "air", "naval", "strategic"} else get_role_profile(unit.get("unit_type") or "army").domain


def has_domain_metadata(regions):
    return any(any(key in row and row.get(key) is not None
                   for key in ("is_water", "region_type", "terrain", "is_port", "is_coastal"))
               for row in regions)


def region_is_water(region):
    if region.get("is_water") is not None:
        return bool(region.get("is_water"))
    return str(region.get("region_type") or region.get("terrain") or "").strip().lower() in {
        "sea", "ocean", "water", "international_waters", "naval_zone",
    }


def domain_route_compatible(domain, region, final, naval_invasion, regions, *, metadata_available=None):
    metadata = has_domain_metadata(regions) if metadata_available is None else bool(metadata_available)
    if not metadata:
        return True, ""
    water = region_is_water(region)
    port = bool(region.get("is_port")) or str(region.get("region_type") or region.get("terrain") or "").strip().lower() in {"port", "naval_base"}
    coastal = bool(region.get("is_coastal")) or port
    if domain == "land" and water:
        return False, "Ground units cannot enter a water region."
    if domain == "naval" and not water and not port and not (final and naval_invasion and coastal):
        return False, "Naval units require a sea zone, port, or eligible coastal landing region."
    if domain == "strategic":
        return False, "Strategic assets do not use conventional movement orders."
    return True, ""
