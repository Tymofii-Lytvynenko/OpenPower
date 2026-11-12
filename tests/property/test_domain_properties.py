import math

import polars as pl
from hypothesis import given, strategies as st

from modules.base.systems.economy.budget_system import BudgetSystem
from modules.base.systems.military.unit_factory import UnitFactory
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionUpdateBudget
from src.shared.numeric import stable_group_sums
from src.shared.state import GameState


@given(st.lists(st.tuples(st.sampled_from(('A', 'B', 'C')), st.floats(-1e9, 1e9, allow_nan=False, allow_infinity=False, width=32)), min_size=1, max_size=30))
def test_economic_group_totals_are_stable_and_match_fsum(rows):
    frame = pl.DataFrame(rows, schema=['country', 'amount'], orient='row')
    def aggregate(data):
        return stable_group_sums(data, ['country'], {'amount': 'total'}).sort('country')
    result = aggregate(frame)
    assert result.equals(aggregate(frame.reverse()))
    for row in result.iter_rows(named=True):
        expected = math.fsum(value for country, value in rows if country == row['country'])
        assert row['total'] == expected
        assert math.isfinite(row['total'])


@given(st.floats(-10, 10, allow_nan=False, allow_infinity=False, width=32))
def test_budget_policy_clamps_known_rate(value):
    from modules.base.schema import build_base_schema_registry
    state = GameState(tables={'countries': pl.DataFrame({'id': ['A']})})
    state.update_table('countries', build_base_schema_registry().normalize('countries', state.tables['countries']))
    action = ActionUpdateBudget('player', 'A', {'personal_income_tax_rate': value})
    BudgetSystem()._handle_update_budget(state, action)
    assert state.tables['countries']['personal_income_tax_rate'][0] == max(0.0, min(1.0, value))


@given(st.integers(1, 30), st.integers(1, 10000))
def test_unit_factory_allocates_unique_ids_and_preserves_ownership(count, strength):
    factory = UnitFactory()
    rows = []
    for _ in range(count):
        unit_id = factory.next_id(rows, 'A', 'army')
        rows.append(factory.create(unit_id, 'A', 'army', strength, 1, GeoCoordinate(0, 0), 0))
    assert len({row['id'] for row in rows}) == count
    assert all(row['owner'] == 'A' and row['current_region_id'] == 1 for row in rows)
    assert all(row['readiness_status'] == 'parked' and row['strength'] == strength for row in rows)

@given(st.one_of(st.floats(-10000, 10000, allow_nan=False, width=32), st.sampled_from((float('nan'), float('inf'), float('-inf')))))
def test_political_indicators_are_finite_and_bounded(value):
    from modules.base.systems.politics.political_policy import normalize_political_indicators
    frame = pl.DataFrame({'gvt_approval': [value], 'gvt_stability': [value], 'gvt_corruption': [value]})
    result = normalize_political_indicators(frame)
    assert all(math.isfinite(number) and 0 <= number <= 100 for number in result.row(0))


@given(st.sampled_from(('parked', 'ready', 'fortified')), st.sampled_from(('parked', 'ready', 'fortified')), st.integers(-10000, 10000))
def test_readiness_transitions_follow_supported_statuses(source, target, now):
    from modules.base.systems.military.readiness_policy import ReadinessPolicy
    policy = ReadinessPolicy()
    transition = policy.transition(source, target)
    if source == target:
        assert transition is None
    else:
        assert transition.from_status == source and transition.target_status == target
        assert transition.duration_minutes >= 0
        assert 0 <= policy.progress(0, transition.duration_minutes, now) <= 1
