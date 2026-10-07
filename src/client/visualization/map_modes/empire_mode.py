from typing import Dict, Optional, Set, Tuple

import polars as pl

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
        self._region_groups_cache = None

    @property
    def name(self) -> str:
        return "Empire"

    @property
    def opacity(self) -> float:
        return 0.82

    def set_selected_country(self, country_tag: Optional[str]) -> None:
        normalized = str(country_tag or "").strip().upper()
        self.selected_country = normalized if normalized and normalized != "NONE" else None

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

        has_owner = "owner" in regions.columns
        authority_values, owner_values, region_id_groups = self._region_groups(
            regions, authority_col, has_owner
        )
        # Region tables have thousands of repeated country tags, so normalize each distinct source value once.
        normalized_tags = {
            value: self._clean_tag(value)
            for value in {*authority_values, *owner_values}
        }

        for authority_value, owner_value, region_ids in zip(
            authority_values, owner_values, region_id_groups
        ):
            owner_tag = normalized_tags[owner_value]
            controller_tag = normalized_tags[authority_value]

            if not controller_tag:
                result.update(dict.fromkeys(region_ids, self.UNKNOWN))
                continue

            if self._is_occupied(owner_tag, controller_tag):
                if pending_annexations:
                    for region_id in region_ids:
                        claim_key = (int(region_id), owner_tag, controller_tag)
                        result[region_id] = (
                            self.ANNEXATION_PENDING
                            if claim_key in pending_annexations
                            else self.OCCUPIED
                        )
                else:
                    result.update(dict.fromkeys(region_ids, self.OCCUPIED))
                continue

            if self.selected_country is None:
                result.update(dict.fromkeys(region_ids, self.NEUTRAL))
                continue

            if controller_tag == self.selected_country:
                result.update(dict.fromkeys(region_ids, self.SELECTED))
                continue

            if controller_tag in military_enemies:
                result.update(dict.fromkeys(region_ids, self.ENEMY))
            elif controller_tag in military_allies:
                result.update(dict.fromkeys(region_ids, self.ALLY))
            else:
                result.update(dict.fromkeys(region_ids, self.NEUTRAL))

        return result

    def _region_groups(self, regions, authority_col: str, has_owner: bool):
        region_ids = regions.get_column("id")
        authority_values = regions.get_column(authority_col)
        owner_values = regions.get_column("owner") if has_owner else authority_values
        cached = self._region_groups_cache
        if (
            cached is not None
            and cached[0] == authority_col
            and cached[1] == has_owner
            and cached[2].equals(region_ids)
            and cached[3].equals(authority_values)
            and cached[4].equals(owner_values)
        ):
            return cached[5], cached[6], cached[7]

        # Population ticks replace the region frame often while political identifiers stay unchanged.
        group_columns = [authority_col]
        if has_owner and "owner" not in group_columns:
            group_columns.append("owner")
        region_groups = (
            regions.select(["id", *group_columns])
            .group_by(group_columns, maintain_order=True)
            .agg(pl.col("id").alias("_region_ids"))
            .to_dict(as_series=False)
        )
        normalized_authorities = region_groups[authority_col]
        normalized_owners = region_groups["owner"] if has_owner else normalized_authorities
        region_id_groups = region_groups["_region_ids"]
        self._region_groups_cache = (
            authority_col,
            has_owner,
            region_ids,
            authority_values,
            owner_values,
            normalized_authorities,
            normalized_owners,
            region_id_groups,
        )
        return normalized_authorities, normalized_owners, region_id_groups

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
