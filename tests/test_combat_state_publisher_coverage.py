import polars as pl

from modules.base.systems.military.combat_state_publisher import (
    BATTLE_PARTICIPANTS_TABLE,
    BATTLE_TABLE,
    BATTLE_UNITS_TABLE,
    OCCUPATIONS_TABLE,
    CombatStatePublisher,
)
from src.shared.state import GameState


def test_reset_battle_tables_initializes_empty_projection_tables():
    publisher = CombatStatePublisher(
        battle_schema={"id": pl.String},
        battle_units_schema={"battle_id": pl.String},
        participants_schema={"battle_id": pl.String},
        occupation_schema={"region_id": pl.Int64},
    )
    state = GameState()

    publisher.reset_battle_tables(state)

    for table_name in (
        BATTLE_TABLE,
        BATTLE_UNITS_TABLE,
        BATTLE_PARTICIPANTS_TABLE,
        OCCUPATIONS_TABLE,
    ):
        assert state.get_table(table_name).is_empty()


def test_country_strength_sync_handles_missing_identifier_and_count_column():
    missing_identifier = pl.DataFrame({"name": ["USA"]})
    assert CombatStatePublisher._sync_country_strengths(missing_identifier, []) is missing_identifier

    countries = pl.DataFrame({"id": ["USA", "CAN"]})
    updated = CombatStatePublisher._sync_country_strengths(
        countries,
        [{"owner": "USA", "strength": 7}],
    )

    assert updated["military_count"].to_list() == [7, 0]
