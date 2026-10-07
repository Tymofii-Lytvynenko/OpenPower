"""Deterministic geographic anchors for authoritative battle rows.

The policy deliberately lives beside the combat system so it can use the
simulation's stopped-unit contact coordinates without coupling the client to
unit billboards.  It is pure data transformation: no combat outcome or mode
decision is made here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping


ANCHOR_SOURCES = frozenset({"contact", "region_center"})


@dataclass(frozen=True, slots=True)
class BattleAnchor:
    """A validated, persisted geographic battle anchor."""

    latitude: float
    longitude: float
    source: str

    def as_row_fields(self) -> dict[str, float | str]:
        return {
            "anchor_latitude": self.latitude,
            "anchor_longitude": self.longitude,
            "anchor_source": self.source,
        }


def is_valid_coordinate(latitude: Any, longitude: Any) -> bool:
    """Return whether a coordinate is finite and within the globe bounds."""

    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return False
    return math.isfinite(lat) and math.isfinite(lon) and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def is_valid_anchor_source(source: Any) -> bool:
    return str(source or "").strip().lower() in ANCHOR_SOURCES


def normalize_longitude(longitude: float) -> float:
    """Keep longitude in the map's canonical ``[-180, 180)`` range."""

    normalized = float(longitude)
    while normalized >= 180.0:
        normalized -= 360.0
    while normalized < -180.0:
        normalized += 360.0
    return normalized


def anchor_from_row(row: Mapping[str, Any] | None) -> BattleAnchor | None:
    """Read an existing row anchor without treating ``0,0`` as missing.

    Old rows can contain coordinates but no source column.  Their coordinates
    are still authoritative, so they are retained and diagnosed as contact
    coordinates rather than silently replaced by a region center.
    """

    if not row:
        return None
    latitude = row.get("anchor_latitude")
    longitude = row.get("anchor_longitude")
    if not is_valid_coordinate(latitude, longitude):
        return None
    source = str(row.get("anchor_source") or "").strip().lower()
    if source not in ANCHOR_SOURCES:
        source = "contact"
    return BattleAnchor(float(latitude), normalize_longitude(float(longitude)), source)


def build_contact_anchor(contact_units: Iterable[Mapping[str, Any]]) -> BattleAnchor | None:
    """Return the spherical mean of valid stopped contact coordinates.

    Sorting by unit ID makes the floating-point reduction replay-stable and
    prevents snapshot/table order from changing the visual anchor.
    """

    points: list[tuple[float, float]] = []
    for unit in sorted(contact_units, key=lambda item: str(item.get("id") or "")):
        latitude = unit.get("latitude")
        longitude = unit.get("longitude")
        if is_valid_coordinate(latitude, longitude):
            points.append((float(latitude), float(longitude)))
    if not points:
        return None

    x_total = y_total = z_total = 0.0
    for latitude, longitude in points:
        lat_radians = math.radians(latitude)
        lon_radians = math.radians(longitude)
        cos_latitude = math.cos(lat_radians)
        x_total += cos_latitude * math.cos(lon_radians)
        y_total += cos_latitude * math.sin(lon_radians)
        z_total += math.sin(lat_radians)

    magnitude = math.sqrt(x_total * x_total + y_total * y_total + z_total * z_total)
    if magnitude <= 1.0e-12 or not math.isfinite(magnitude):
        return None

    latitude = math.degrees(math.asin(max(-1.0, min(1.0, z_total / magnitude))))
    longitude = normalize_longitude(math.degrees(math.atan2(y_total, x_total)))
    return BattleAnchor(latitude, longitude, "contact")


def resolve_battle_anchor(
    contact_units: Iterable[Mapping[str, Any]],
    region_row: Mapping[str, Any] | None,
    prior_row: Mapping[str, Any] | None = None,
) -> BattleAnchor | None:
    """Preserve an established anchor, then use contact or region fallback."""

    previous = anchor_from_row(prior_row)
    if previous is not None:
        return previous

    contact = build_contact_anchor(contact_units)
    if contact is not None:
        return contact

    if region_row and is_valid_coordinate(region_row.get("latitude"), region_row.get("longitude")):
        return BattleAnchor(
            float(region_row["latitude"]),
            normalize_longitude(float(region_row["longitude"])),
            "region_center",
        )
    return None
