from types import SimpleNamespace

import polars as pl
import pytest

from src.shared.covert_mission_options import country_resource_ids, mission_profile_type


@pytest.mark.parametrize("category,sector", [("espionage", ""), ("sabotage", "strategic")])
def test_mission_profile_requires_a_supported_sector(category, sector):
    with pytest.raises(ValueError, match="require a valid target sector"):
        mission_profile_type(category, sector)


def test_unknown_mission_categories_are_rejected():
    with pytest.raises(ValueError, match="Unknown covert mission category"):
        mission_profile_type("unknown", "civilian")


def test_resource_table_without_country_rows_does_not_use_global_fallback():
    state = SimpleNamespace(
        tables={
            "resource_ledger": pl.DataFrame(
                schema={"country_id": pl.String, "game_resource_id": pl.String}
            )
        }
    )

    assert country_resource_ids(state, "USA") == ()
