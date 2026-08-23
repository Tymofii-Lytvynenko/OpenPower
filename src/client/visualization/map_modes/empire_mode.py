from typing import Dict, Optional, Set, Tuple

from src.client.utils.diplomacy_utils import get_military_allies, get_military_enemies
from src.client.visualization.map_modes.base_map_mode import BaseMapMode
from src.shared.state import GameState


class EmpireMapMode(BaseMapMode):
    """
    Styled diplomatic view centered on the selected country.
    Selected country is green, military allies are blue, wartime enemies are red,
    and neutral countries stay subdued so the military blocs remain readable.
    """

    SELECTED = (92, 210, 118, 240)
    NEUTRAL = (88, 94, 104, 96)
    UNKNOWN = (44, 46, 52, 72)

    ALLY = (118, 198, 236, 215)
    ENEMY = (212, 36, 55, 220)
    OCCUPIED = (232, 146, 42, 235)
    ANNEXATION_PENDING = (35, 102, 53, 235)

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
        authority_col = self._authority_column(regions)
        if "id" not in regions.columns or authority_col is None:
            return {}

        military_allies = get_military_allies(state, self.selected_country)
        military_enemies = get_military_enemies(state, self.selected_country)
        pending_annexations = self._pending_annexations(state)
        result: Dict[int, Tuple[int, ...]] = {}

        selected_columns = ["id", authority_col]
        if "owner" in regions.columns and "owner" not in selected_columns:
            selected_columns.append("owner")

        for row in regions.select(selected_columns).iter_rows(named=True):
            region_id = row["id"]
            authority_tag = row[authority_col]
            owner_tag = self._clean_tag(row.get("owner"))
            controller_tag = self._clean_tag(authority_tag)

            if not authority_tag or authority_tag == "None":
                result[region_id] = self.UNKNOWN
                continue

            if self._is_occupied(owner_tag, controller_tag):
                claim_key = (int(region_id), owner_tag, controller_tag)
                result[region_id] = (
                    self.ANNEXATION_PENDING
                    if claim_key in pending_annexations
                    else self.OCCUPIED
                )
                continue

            if self.selected_country is None:
                result[region_id] = self.NEUTRAL
                continue

            if authority_tag == self.selected_country:
                result[region_id] = self.SELECTED
                continue

            if authority_tag in military_enemies:
                result[region_id] = self.ENEMY
            elif authority_tag in military_allies:
                result[region_id] = self.ALLY
            else:
                result[region_id] = self.NEUTRAL

        return result

    def _pending_annexations(self, state: GameState) -> set[tuple[int, str, str]]:
        claims = state.tables.get("annexation_claims")
        if claims is None or claims.is_empty():
            return set()

        return {
            (
                int(row.get("region_id") or 0),
                self._clean_tag(row.get("political_owner_id")),
                self._clean_tag(row.get("annexing_country_id")),
            )
            for row in claims.iter_rows(named=True)
            if str(row.get("status") or "").strip().lower() == "pending"
        }

    @staticmethod
    def _clean_tag(value: object) -> str:
        tag = str(value or "").strip()
        return "" if tag.lower() == "none" else tag.upper()

    @staticmethod
    def _is_occupied(owner_tag: str, controller_tag: str) -> bool:
        return bool(owner_tag and controller_tag and owner_tag != controller_tag)

    def _authority_column(self, regions) -> str | None:
        if "controller" in regions.columns:
            return "controller"
        if "owner" in regions.columns:
            return "owner"
        return None
