from typing import Dict, Tuple

from src.client.utils.color_generator import generate_political_colors
from src.client.visualization.map_modes.base_map_mode import BaseMapMode
from src.shared.state import GameState


class PoliticalMapMode(BaseMapMode):
    OCCUPATION_HIGHLIGHT_ALPHA = 255

    @property
    def name(self) -> str:
        return "Political"

    def calculate_colors(self, state: GameState) -> Dict[int, Tuple[int, ...]]:
        if "regions" not in state.tables:
            return {}

        df = state.get_table("regions")
        authority_col = self._authority_column(df)
        if authority_col is None:
            return {}

        # Occupation needs both sides' canonical colors, not only the current
        # controller's color. Keeping this palette deterministic preserves the
        # existing political-map color assignment for non-occupied regions.
        palette_tags = []
        for column in ("owner", authority_col):
            if column not in df.columns:
                continue
            palette_tags.extend(
                self._clean_tag(value)
                for value in df[column].drop_nulls().to_list()
                if self._clean_tag(value)
            )
        palette = generate_political_colors(list(dict.fromkeys(palette_tags)))

        selected_columns = ["id", authority_col]
        if "owner" in df.columns and "owner" not in selected_columns:
            selected_columns.append("owner")
        rows = df.select(selected_columns).to_dicts()

        result: Dict[int, Tuple[int, ...]] = {}
        for row in rows:
            rid = row["id"]
            authority_tag = row[authority_col]
            controller_tag = self._clean_tag(authority_tag)
            owner_tag = self._clean_tag(row.get("owner"))
            controller_color = palette.get(controller_tag, (50, 50, 50))

            if self._is_occupied(owner_tag, controller_tag):
                owner_color = palette.get(owner_tag, (50, 50, 50))
                mixed_color = tuple(
                    round((owner_color[index] + controller_color[index]) / 2)
                    for index in range(3)
                )
                # Alpha 255 activates the existing shader highlight path for
                # occupied regions while leaving ordinary political colors at
                # their normal overlay alpha.
                result[rid] = (*mixed_color, self.OCCUPATION_HIGHLIGHT_ALPHA)
            else:
                result[rid] = controller_color

        return result

    @staticmethod
    def _clean_tag(value: object) -> str:
        tag = str(value or "").strip()
        return "" if tag.lower() == "none" else tag

    @staticmethod
    def _is_occupied(owner_tag: str, controller_tag: str) -> bool:
        return bool(owner_tag and controller_tag and owner_tag != controller_tag)

    def _authority_column(self, df):
        if "controller" in df.columns:
            return "controller"
        if "owner" in df.columns:
            return "owner"
        return None
