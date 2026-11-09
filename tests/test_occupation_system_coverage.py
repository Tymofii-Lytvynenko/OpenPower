import polars as pl

from modules.base.systems.military.occupation_system import (
    OCCUPATION_SCHEMA,
    OccupationSystem,
)
from src.shared.events import EventNewHour
from src.shared.state import GameState


def _empty_units() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "is_moving": pl.Boolean,
            "current_region_id": pl.Int32,
            "owner": pl.Utf8,
            "strength": pl.Int64,
        }
    )


def test_occupation_system_metadata_and_missing_world_tables() -> None:
    system = OccupationSystem()
    state = GameState()

    assert system.id == "base.occupation"
    assert system.dependencies == ["base.combat"]

    system.update(state, 0)

    assert state.get_table("occupations").is_empty()
    assert state.get_table("occupations").schema == OCCUPATION_SCHEMA
    assert state.table_revisions["occupations"] == 1


def test_existing_occupations_are_skipped_without_a_new_hour_event() -> None:
    occupations = pl.DataFrame(schema=OCCUPATION_SCHEMA)
    state = GameState(
        tables={
            "regions": pl.DataFrame(
                schema={"id": pl.Int32, "owner": pl.Utf8, "controller": pl.Utf8}
            ),
            "units": _empty_units(),
            "occupations": occupations,
        }
    )

    OccupationSystem().update(state, 0)

    assert state.get_table("occupations") is occupations
    assert state.table_revisions["occupations"] == 1


def test_update_adds_missing_columns_to_legacy_occupation_table() -> None:
    state = GameState(
        tables={
            "regions": pl.DataFrame(
                {"id": [7], "owner": ["AAA"], "controller": ["BBB"]}
            ),
            "units": _empty_units(),
            "occupations": pl.DataFrame({"region_id": [7]}),
        }
    )
    state.events.append(EventNewHour(1, 60))

    OccupationSystem().update(state, 0)

    occupations = state.get_table("occupations")
    assert occupations.schema == OCCUPATION_SCHEMA
    row = occupations.to_dicts()[0]
    assert row["region_id"] == 7
    assert row["controller_country_id"] == "BBB"
    assert row["occupation_status"] == "contested"
    assert row["contested"] is True
