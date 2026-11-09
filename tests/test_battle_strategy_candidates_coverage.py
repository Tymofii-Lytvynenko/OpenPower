import polars as pl

from modules.base.systems.world.ai.battle_strategy_candidates import (
    BattleForceGroupAggregator,
    BattleParticipantEligibilityResolver,
    BattleStrategyDataLoader,
    BattleStrategyInputs,
    _finite,
)
from src.core.ai_framework import AITableContext


def _context(tables=None, *, player_tag=""):
    return AITableContext(
        tables=tables or {},
        day_ordinal=1,
        total_minutes=1_440,
        date_text="2001-01-02",
        player_tag=player_tag,
    )


def _required_tables(*, participants=None, battles=None, units=None):
    return {
        "battles": (
            battles
            if battles is not None
            else pl.DataFrame({"id": ["battle-1"], "status": ["active"]})
        ),
        "battle_units": participants if participants is not None else pl.DataFrame(schema={
            "battle_id": pl.Utf8,
            "unit_id": pl.Utf8,
            "country_id": pl.Utf8,
            "side": pl.Utf8,
        }),
        "units": units if units is not None else pl.DataFrame(schema={
            "id": pl.Utf8,
            "owner": pl.Utf8,
            "strength": pl.Int64,
        }),
        "countries": pl.DataFrame({"id": ["USA"]}),
    }


def _inputs(*, participant_rows=None, unit_by_id=None, active_battles=None):
    return BattleStrategyInputs(
        controlled_countries={"USA"},
        active_battles=active_battles or {"battle-1"},
        participant_rows=participant_rows or [],
        unit_by_id=unit_by_id or {},
        safe_region_ids=set(),
        reserves_by_country={},
        active_unit_ids=set(),
        reorganization_cost=0.01,
        cohesion_threshold=0.4,
        retreat_ratio_threshold=0.35,
    )


def test_loader_rejects_missing_inputs_and_empty_ai_work_sets():
    loader = BattleStrategyDataLoader()
    assert loader.load(_context(), 1) is None

    required = _required_tables()
    assert loader.load(_context(required | {"countries": pl.DataFrame({"id": []})}), 1) is None

    no_unit_ids = pl.DataFrame({
        "battle_id": ["battle-1"],
        "unit_id": [None],
        "country_id": ["USA"],
        "side": ["A"],
    })
    assert loader.load(_context(_required_tables(participants=no_unit_ids)), 1) is None


def test_loader_validates_required_table_schemas():
    loader = BattleStrategyDataLoader()
    valid = _required_tables()
    assert loader._load_required_frames(_context()) is None

    invalid_battles = valid | {"battles": pl.DataFrame({"name": ["battle"]})}
    assert loader._load_required_frames(_context(invalid_battles)) is None

    invalid_participants = valid | {"battle_units": pl.DataFrame({"unit_id": ["u1"]})}
    assert loader._load_required_frames(_context(invalid_participants)) is None

    invalid_units = valid | {"units": pl.DataFrame({"id": ["u1"], "owner": ["USA"]})}
    assert loader._load_required_frames(_context(invalid_units)) is None


def test_loader_handles_optional_region_reserve_and_posture_tables():
    assert BattleStrategyDataLoader._load_safe_region_ids(
        _context({"regions": pl.DataFrame({"name": ["region"]})}),
        [{"current_region_id": 1}],
    ) == set()
    assert BattleStrategyDataLoader._load_safe_region_ids(
        _context({"regions": pl.DataFrame({"id": [1]})}), []
    ) == set()

    assert BattleStrategyDataLoader._load_reserves(_context(), {"USA"}) == {}
    assert BattleStrategyDataLoader._load_reserves(
        _context({"countries": pl.DataFrame({"id": ["USA"]})}), {"USA"}
    ) == {}

    assert BattleStrategyDataLoader._load_active_unit_ids(_context(), ["u1"]) == set()
    assert BattleStrategyDataLoader._load_active_unit_ids(
        _context({"battle_force_postures": pl.DataFrame({"unit_id": ["u1"]})}),
        ["u1"],
    ) == set()


def test_eligibility_resolver_rejects_each_unsupported_participant():
    resolver = BattleParticipantEligibilityResolver()
    unit = {"owner": "USA", "strength": 10, "is_moving": False}
    inputs = _inputs(unit_by_id={"u1": unit})
    participants = [
        ({"battle_id": "inactive", "unit_id": "u1", "country_id": "USA", "side": "A"}, inputs),
        ({"battle_id": "battle-1", "unit_id": "missing", "country_id": "USA", "side": "A"}, inputs),
        ({"battle_id": "battle-1", "unit_id": "u1", "country_id": "CAN", "side": "A"}, inputs),
        ({"battle_id": "battle-1", "unit_id": "u1", "country_id": "USA", "side": ""}, inputs),
        (
            {"battle_id": "battle-1", "unit_id": "u1", "country_id": "USA", "side": "A"},
            _inputs(unit_by_id={"u1": {**unit, "strength": 0}}),
        ),
        (
            {"battle_id": "battle-1", "unit_id": "u1", "country_id": "USA", "side": "A"},
            _inputs(unit_by_id={"u1": {**unit, "is_moving": True}}),
        ),
    ]

    assert all(resolver.resolve(participant, state) is None for participant, state in participants)


def test_aggregator_skips_ineligible_participants_and_finite_handles_bad_values():
    groups = BattleForceGroupAggregator().aggregate(_inputs(
        participant_rows=[{"battle_id": "battle-1", "unit_id": "missing"}],
    ))

    assert groups.units == {}
    assert groups.side_strengths == {}
    assert groups.blocked_groups == set()
    assert _finite(object()) == 0.0
