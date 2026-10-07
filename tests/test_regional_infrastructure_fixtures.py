"""Deterministic world inputs shared by regional infrastructure tests."""

from __future__ import annotations

import polars as pl

from src.shared.state import GameState


def build_infrastructure_state() -> GameState:
    """Build a small world with owned, foreign, and uncontrolled regions."""

    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["USA", "CAN"],
                    "money_reserves": [1_000_000.0, 250_000.0],
                    "gdp": [2_000_000.0, 1_000_000.0],
                    "human_dev": [0.8, 0.7],
                }
            ),
            "regions": pl.DataFrame(
                {
                    "id": [101, 202, 303],
                    "owner": ["USA", "CAN", ""],
                    "population": [100_000, 50_000, 0],
                    "area_km2": [1_000.0, 500.0, 250.0],
                    "infrastructure": [0.4, 0.6, 0.0],
                    "infrastructure_health": [0.9, 0.8, 1.0],
                    "communications": [0.3, 0.5, 0.0],
                    "health_capacity": [0.7, 0.6, 0.0],
                }
            ),
        }
    )
    state.globals["player_country_map"] = {"player-1": "USA"}
    return state
