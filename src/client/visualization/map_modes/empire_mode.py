from typing import Dict, Tuple, Optional, Set

from src.server.state import GameState
from src.client.visualization.map_modes.base_map_mode import BaseMapMode


class EmpireMapMode(BaseMapMode):
    """
    Superpower 2 style diplomatic view centered on the selected country.
    Selected country is green, military allies are blue, wartime enemies are red,
    and neutral countries stay subdued so the military blocs remain readable.
    """

    SELECTED = (92, 210, 118, 240)
    NEUTRAL = (88, 94, 104, 96)
    UNKNOWN = (44, 46, 52, 72)

    ALLY = (118, 198, 236, 215)
    ENEMY = (212, 36, 55, 220)

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

        military_allies = self._build_military_allies(state)
        military_enemies = self._build_military_enemies(state)
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

            if owner in military_enemies:
                result[region_id] = self.ENEMY
            elif owner in military_allies:
                result[region_id] = self.ALLY
            else:
                result[region_id] = self.NEUTRAL

        return result

    def _build_military_allies(self, state: GameState) -> Set[str]:
        allies = self._countries_from_alliance_treaties(state)
        allies.discard(self.selected_country)
        return allies

    def _build_military_enemies(self, state: GameState) -> Set[str]:
        if self.selected_country is None or "countries_wars" not in state.tables:
            return set()

        enemies = set()
        wars = state.get_table("countries_wars")
        if "side_a" not in wars.columns or "side_b" not in wars.columns:
            return enemies

        for row in wars.select(["side_a", "side_b"]).iter_rows(named=True):
            side_a = self._normalize_side(row["side_a"])
            side_b = self._normalize_side(row["side_b"])
            if self.selected_country in side_a:
                enemies.update(side_b)
            elif self.selected_country in side_b:
                enemies.update(side_a)

        enemies.discard(self.selected_country)
        return enemies

    def _countries_from_alliance_treaties(self, state: GameState) -> Set[str]:
        if self.selected_country is None or "countries_treaties" not in state.tables:
            return set()

        treaties = state.get_table("countries_treaties")
        if treaties.is_empty():
            return set()

        allies = set()
        columns = set(treaties.columns)

        if {"members", "type"}.issubset(columns):
            for row in treaties.select(["members", "type"]).iter_rows(named=True):
                treaty_type = str(row["type"]).lower() if row["type"] is not None else ""
                if treaty_type not in {"alliance", "defensive_alliance", "military_alliance"}:
                    continue

                members = self._normalize_side(row["members"])
                if self.selected_country in members:
                    allies.update(members)

        if {"side_a", "side_b", "type"}.issubset(columns):
            for row in treaties.select(["side_a", "side_b", "type"]).iter_rows(named=True):
                treaty_type = str(row["type"]).lower() if row["type"] is not None else ""
                if treaty_type not in {"alliance", "defensive_alliance", "military_alliance"}:
                    continue

                side_a = self._normalize_side(row["side_a"])
                side_b = self._normalize_side(row["side_b"])
                if self.selected_country in side_a:
                    allies.update(side_b)
                elif self.selected_country in side_b:
                    allies.update(side_a)

        allies.discard(self.selected_country)
        return allies

    def _normalize_side(self, value) -> Set[str]:
        if value is None:
            return set()
        if isinstance(value, list):
            return {str(tag) for tag in value if tag is not None}
        if isinstance(value, tuple):
            return {str(tag) for tag in value if tag is not None}
        if isinstance(value, str):
            return {tag.strip() for tag in value.split(",") if tag.strip()}
        return set()
