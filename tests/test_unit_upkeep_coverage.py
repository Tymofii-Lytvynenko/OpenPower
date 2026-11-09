from __future__ import annotations

import polars as pl

from modules.base.systems.economy.unit_upkeep import (
    readiness_upkeep_by_country,
    readiness_upkeep_factors,
    unit_upkeep_by_id,
)
from src.shared.state import GameState


def test_readiness_aggregation_without_designs_uses_zero_maintenance():
    state = GameState(
        tables={"units": pl.DataFrame({"owner": ["USA"], "strength": [0.0]})}
    )

    rows = readiness_upkeep_by_country(state, {}).to_dicts()

    assert rows == [
        {
            "id": "USA",
            "_readiness_upkeep_factor": 1.0,
            "_design_maintenance": 0.0,
        }
    ]


def test_readiness_factors_ignore_invalid_configuration_and_values():
    state = GameState()
    state.globals["military_readiness_upkeep_factors"] = ["ready", 2.0]
    assert readiness_upkeep_factors(state) == {}

    state.globals["military_readiness_upkeep_factors"] = {
        "parked": None,
        "ready": "not-a-number",
        "fortified": float("inf"),
    }
    assert readiness_upkeep_factors(state) == {}


def test_unit_breakdown_skips_unknown_owners_and_zeroes_unusable_strength():
    state = GameState(
        tables={
            "units": pl.DataFrame(
                {
                    "id": ["USA-invalid", "MEX-unknown"],
                    "owner": ["USA", "MEX"],
                    "strength": ["not-a-number", "10"],
                }
            ),
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [10]}),
        }
    )
    incomplete_state = GameState(
        tables={
            "units": pl.DataFrame({"id": ["U1"], "strength": [10]}),
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [10]}),
        }
    )

    assert unit_upkeep_by_id(incomplete_state) == {}
    assert unit_upkeep_by_id(state) == {"USA-invalid": 0.0}
