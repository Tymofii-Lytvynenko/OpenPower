from typing import Dict, Tuple

from src.client.utils.color_generator import generate_political_colors
from src.client.visualization.map_modes.base_map_mode import BaseMapMode
from src.shared.state import GameState


class PoliticalMapMode(BaseMapMode):
    @property
    def name(self) -> str:
        return "Political"

    def calculate_colors(self, state: GameState) -> Dict[int, Tuple[int, int, int]]:
        if "regions" not in state.tables:
            return {}

        df = state.get_table("regions")
        authority_col = self._authority_column(df)
        if authority_col is None:
            return {}

        unique_owners = df[authority_col].unique().to_list()
        palette = generate_political_colors(unique_owners)
        rows = df.select(["id", authority_col]).to_dicts()

        result = {}
        for row in rows:
            rid = row["id"]
            authority_tag = row[authority_col]
            result[rid] = palette.get(authority_tag, (50, 50, 50))

        return result

    def _authority_column(self, df):
        if "controller" in df.columns:
            return "controller"
        if "owner" in df.columns:
            return "owner"
        return None
