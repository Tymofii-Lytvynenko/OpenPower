import polars as pl
from typing import Dict, Tuple, Optional

from src.server.state import GameState
from src.client.visualization.map_modes.base_map_mode import BaseMapMode


class EmpireMapMode(BaseMapMode):
    """
    Superpower 2 style diplomatic view centered on the selected country.
    Selected country is green, allies are blue, enemies are red, and neutral
    countries stay subdued so the diplomatic extremes remain readable.
    """

    ALLY_THRESHOLD = 40
    ENEMY_THRESHOLD = -40

    SELECTED = (92, 210, 118, 240)
    NEUTRAL = (88, 94, 104, 96)
    UNKNOWN = (44, 46, 52, 72)

    ALLY_SOFT = (82, 150, 190)
    ALLY_STRONG = (130, 220, 240)
    ENEMY_SOFT = (150, 48, 62)
    ENEMY_STRONG = (225, 34, 54)

    def __init__(self):
        self.selected_country: Optional[str] = None

    @property
    def name(self) -> str:
        return "Empire"

    @property
    def opacity(self) -> float:
        return 0.82

    def set_selected_country(self, country_tag: Optional[str]) -> None:
        self.selected_country = country_tag if country_tag and country_tag != "None" else None

    def calculate_colors(self, state: GameState) -> Dict[int, Tuple[int, ...]]:
        if "regions" not in state.tables:
            return {}

        regions = state.get_table("regions")
        if "id" not in regions.columns or "owner" not in regions.columns:
            return {}

        relation_lookup = self._build_relation_lookup(state)
        result: Dict[int, Tuple[int, ...]] = {}

        for row in regions.select(["id", "owner"]).iter_rows(named=True):
            region_id = row["id"]
            owner = row["owner"]

            if not owner or owner == "None":
                result[region_id] = self.UNKNOWN
                continue

            if self.selected_country is None:
                result[region_id] = self.NEUTRAL
                continue

            if owner == self.selected_country:
                result[region_id] = self.SELECTED
                continue

            score = relation_lookup.get(owner)
            if score is None:
                result[region_id] = self.UNKNOWN
            elif score >= self.ALLY_THRESHOLD:
                result[region_id] = self._relation_color(score, self.ALLY_THRESHOLD, 100, self.ALLY_SOFT, self.ALLY_STRONG, 215)
            elif score <= self.ENEMY_THRESHOLD:
                result[region_id] = self._relation_color(abs(score), abs(self.ENEMY_THRESHOLD), 100, self.ENEMY_SOFT, self.ENEMY_STRONG, 220)
            else:
                result[region_id] = self.NEUTRAL

        return result

    def _build_relation_lookup(self, state: GameState) -> Dict[str, int]:
        if self.selected_country is None or "countries_relations" not in state.tables:
            return {}

        rels = state.get_table("countries_relations")
        required = {"source", "target", "value"}
        if not required.issubset(set(rels.columns)):
            return {}

        rows = rels.filter(pl.col("source") == self.selected_country).select(["target", "value"])
        return {
            str(target): int(value)
            for target, value in rows.iter_rows()
            if target is not None and value is not None
        }

    def _relation_color(
        self,
        value: int,
        min_value: int,
        max_value: int,
        soft: Tuple[int, int, int],
        strong: Tuple[int, int, int],
        alpha: int,
    ) -> Tuple[int, int, int, int]:
        t = (float(value) - float(min_value)) / max(float(max_value - min_value), 1.0)
        t = max(0.0, min(1.0, t))
        return (
            int(soft[0] + (strong[0] - soft[0]) * t),
            int(soft[1] + (strong[1] - soft[1]) * t),
            int(soft[2] + (strong[2] - soft[2]) * t),
            alpha,
        )
