from typing import Dict, Tuple
from src.server.state import GameState
from src.client.map_modes.base_map_mode import BaseMapMode
from src.client.utils.color_generator import generate_political_colors

class PoliticalMapMode(BaseMapMode):
    @property
    def name(self) -> str:
        return "Political"

    def calculate_colors(self, state: GameState) -> Dict[int, Tuple[int, int, int]]:
        if "regions" not in state.tables:
            return {}

        df = state.get_table("regions")
        if "owner" not in df.columns:
            return {}

        # 1. Get unique owners to generate consistent palette
        unique_owners = df["owner"].unique().to_list()

        # 2. Generate Palette: {CountryTag: RGB}
        palette = generate_political_colors(unique_owners)

        # 3. Map Regions to Colors
        # Using Polars to map implies creating a join, but for simplicity/speed
        # with dictionaries in Python:

        # Pull only necessary columns
        rows = df.select(["id", "owner"]).to_dicts()

        result = {}
        for row in rows:
            rid = row["id"]
            owner = row["owner"]
            # Default to dark grey for unowned/None
            color = palette.get(owner, (50, 50, 50))
            result[rid] = color

        return result