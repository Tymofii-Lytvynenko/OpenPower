"""Geographic eligibility checks shared by treaty lifecycle operations."""

from __future__ import annotations

import math
from typing import Any

from src.shared.state import GameState


class TreatyGeography:
    """Derives stable country centroids from the regions available in a game state."""

    @classmethod
    def within_limit(cls, state: GameState, first_country: str, second_country: str, limit_km: Any) -> bool:
        """Return whether both countries are within the optional great-circle distance limit."""
        try:
            maximum = float(limit_km or 0.0)
        except (TypeError, ValueError):
            maximum = 0.0
        if maximum <= 0.0:
            return True
        first = cls._country_centroid(state, first_country)
        second = cls._country_centroid(state, second_country)
        if first is None or second is None:
            return False
        return cls._great_circle_distance_km(first, second) <= maximum

    @staticmethod
    def _country_centroid(state: GameState, country_id: str) -> tuple[float, float] | None:
        regions = state.tables.get("regions")
        if regions is None or regions.is_empty() or not {"owner", "latitude", "longitude"}.issubset(regions.columns):
            return None
        target = str(country_id or "").strip().upper()
        vectors: list[tuple[float, float, float]] = []
        for region in regions.iter_rows(named=True):
            if str(region.get("owner") or "").strip().upper() != target:
                continue
            latitude, longitude = region.get("latitude"), region.get("longitude")
            if latitude is None or longitude is None:
                continue
            lat_radians, lon_radians = math.radians(float(latitude)), math.radians(float(longitude))
            vectors.append((
                math.cos(lat_radians) * math.cos(lon_radians),
                math.cos(lat_radians) * math.sin(lon_radians),
                math.sin(lat_radians),
            ))
        if not vectors:
            return None
        x, y, z = (sum(vector[index] for vector in vectors) for index in range(3))
        magnitude = math.sqrt(x * x + y * y + z * z)
        if magnitude <= 1e-12:
            return None
        return math.degrees(math.asin(z / magnitude)), math.degrees(math.atan2(y, x))

    @staticmethod
    def _great_circle_distance_km(first: tuple[float, float], second: tuple[float, float]) -> float:
        first_latitude, first_longitude = (math.radians(value) for value in first)
        second_latitude, second_longitude = (math.radians(value) for value in second)
        latitude_delta = second_latitude - first_latitude
        longitude_delta = second_longitude - first_longitude
        haversine = (
            math.sin(latitude_delta / 2.0) ** 2
            + math.cos(first_latitude) * math.cos(second_latitude) * math.sin(longitude_delta / 2.0) ** 2
        )
        return 2.0 * 6371.0 * math.asin(min(1.0, math.sqrt(haversine)))
