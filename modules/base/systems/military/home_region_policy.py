"""Choose a stable home region for each country's military units."""

from __future__ import annotations

from typing import Any

import polars as pl


class MilitaryHomeRegionPolicy:
    """Resolve each owner to the region with the strongest home-region score."""

    def home_regions_by_country(self, regions: pl.DataFrame) -> dict[str, int]:
        required = {"id", "owner"}
        if regions.is_empty() or not required.issubset(set(regions.columns)):
            return {}

        score_columns = [col for col in ("pop_15_64", "area_km2") if col in regions.columns]
        selected: dict[str, tuple[int, float]] = {}
        for row in regions.iter_rows(named=True):
            self._consider_region(selected, row, score_columns)
        return {owner: region_id for owner, (region_id, _) in selected.items()}

    def _consider_region(
        self,
        selected: dict[str, tuple[int, float]],
        row: dict[str, Any],
        score_columns: list[str],
    ) -> None:
        owner = row.get("owner")
        region_id = row.get("id")
        if not owner or owner == "None" or region_id is None:
            return

        owner_key = str(owner)
        score = self._region_score(row, score_columns)
        current = selected.get(owner_key)
        if current is None or score > current[1]:
            selected[owner_key] = (int(region_id), score)

    def _region_score(self, row: dict[str, Any], score_columns: list[str]) -> float:
        score = 0.0
        for column in score_columns:
            value = row.get(column)
            if value is not None:
                score += float(value)
        return score
