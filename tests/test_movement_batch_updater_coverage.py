from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

from modules.base.systems.military import movement_batch_updater as updater_module
from modules.base.systems.military.movement_batch_updater import MovementBatchUpdater
from modules.base.systems.military.movement_constants import NO_TARGET_REGION


class _AccessPolicy:
    def __init__(self, can_station=True):
        self.station_allowed = can_station
        self.calls = []

    def for_country(self, state, unit_owner):
        self.calls.append((state, unit_owner))
        return SimpleNamespace(can_station=lambda _region: self.station_allowed)


def _units(**changes):
    row = {
        "id": "unit-1",
        "owner": "UKR",
        "unit_domain": "land",
        "unit_type": "infantry",
        "is_moving": True,
        "engagement_mode": "",
        "target_region_id": 2,
        "target_latitude": 20.0,
        "target_longitude": 30.0,
        "current_region_id": 1,
        "latitude": 10.0,
        "longitude": 15.0,
        "source_region_id": 1,
        "source_latitude": 10.0,
        "source_longitude": 15.0,
        "departed_at_minute": 0,
        "arrival_at_minute": 200,
        "movement_progress": 0.0,
    }
    row.update(changes)
    return pl.DataFrame([row])


def _routes(**changes):
    row = {
        "unit_id": "unit-1",
        "owner_country_id": "UKR",
        "destination_region_id": 2,
        "route_region_ids": [1, 2],
        "route_index": 1,
        "has_custom_destination": False,
        "is_naval_invasion": False,
        "status": "in_transit",
        "rejection_reason": "",
        "updated_at_minute": 100,
    }
    row.update(changes)
    return pl.DataFrame([row])


def _state(regions=None):
    tables = {} if regions is None else {"regions": regions}
    return SimpleNamespace(tables=tables, update_table=Mock())


def _updater(can_station=True):
    access_policy = _AccessPolicy(can_station)
    return MovementBatchUpdater(access_policy), access_policy


def _allow_domain_route(monkeypatch, allowed=True):
    monkeypatch.setattr(updater_module, "unit_domain", lambda profile: profile["unit_domain"])
    monkeypatch.setattr(
        updater_module,
        "domain_route_compatible",
        lambda *_args: (allowed, "blocked" if not allowed else ""),
    )


def test_uncontested_path_updates_numpy_progress_and_mixed_rows():
    updater, _access_policy = _updater()
    active_units = pl.DataFrame(
        {
            "id": ["unit-1", "unit-2"],
            "is_moving": [True, True],
            "target_region_id": [2, 3],
            "departed_at_minute": [0, 10],
            "arrival_at_minute": [200, 210],
            "movement_progress": [0.0, 0.0],
        }
    )

    active = updater.try_update_uncontested(_state(), active_units, 100, Mock())

    assert active.get_column("movement_progress").to_list() == [0.5, 0.45]

    mixed_units = pl.DataFrame(
        {
            "id": ["active", "idle", "untargeted"],
            "is_moving": [True, False, True],
            "target_region_id": [2, 0, 0],
            "departed_at_minute": [0, 0, 0],
            "arrival_at_minute": [200, 0, 300],
            "movement_progress": [0.0, 0.2, 0.3],
        }
    )
    mixed = updater.try_update_uncontested(_state(), mixed_units, 100, Mock())

    assert mixed.get_column("movement_progress").to_list() == [0.5, 0.0, 0.0]
    assert mixed.get_column("is_moving").to_list() == [True, False, False]


def test_uncontested_path_rejects_missing_columns_war_contact_and_arrivals(monkeypatch):
    updater, _access_policy = _updater()
    callback = Mock()
    assert updater.try_update_uncontested(
        _state(), pl.DataFrame({"id": ["unit-1"]}), 100, callback
    ) is None
    callback.assert_not_called()

    valid = pl.DataFrame(
        {
            "id": ["unit-1"],
            "is_moving": [True],
            "target_region_id": [2],
            "departed_at_minute": [0],
            "arrival_at_minute": [200],
            "movement_progress": [0.0],
        }
    )
    wars = pl.DataFrame({"id": ["war"]})
    monkeypatch.setattr(updater_module, "hostile_country_pairs", lambda _rows: {("UKR", "POL")})
    assert updater.try_update_uncontested(
        SimpleNamespace(tables={"countries_wars": wars}), valid, 100, callback
    ) is None

    monkeypatch.setattr(updater_module, "hostile_country_pairs", lambda _rows: set())
    arriving = valid.with_columns(pl.lit(100).alias("arrival_at_minute"))
    assert updater.try_update_uncontested(_state(), arriving, 100, callback) is None


def test_uncontested_path_delegates_when_routes_exist():
    updater, _access_policy = _updater()
    units = pl.DataFrame(
        {
            "id": ["unit-1"],
            "is_moving": [True],
            "target_region_id": [2],
            "departed_at_minute": [0],
            "arrival_at_minute": [200],
            "movement_progress": [0.0],
        }
    )
    routes = pl.DataFrame({"unit_id": ["unit-1"]})
    state = SimpleNamespace(tables={"unit_movement_routes": routes})
    final_leg_updater = Mock(return_value=units)

    assert updater.try_update_uncontested(state, units, 100, final_leg_updater) is units
    final_leg_updater.assert_called_once_with(state, units, 100, routes)


def test_final_leg_shape_checks_required_columns_motion_and_route_identity():
    updater, _access_policy = _updater()
    units = _units()
    routes = _routes()

    assert not updater._has_final_leg_batch_shape(pl.DataFrame({"id": ["unit-1"]}), routes)
    assert not updater._has_final_leg_batch_shape(units.with_columns(pl.lit(False).alias("is_moving")), routes)
    assert not updater._has_final_leg_batch_shape(units, _routes(unit_id="other"))
    assert updater._has_final_leg_batch_shape(units, routes)

    duplicate_units = pl.DataFrame({"id": ["unit-1", "unit-1"]})
    duplicate_routes = pl.DataFrame({"unit_id": ["unit-1", "unit-2"]})
    assert not updater._route_ids_match_units(duplicate_units, duplicate_routes)
    assert not updater._route_ids_match_units(
        pl.DataFrame({"id": ["unit-1", "unit-2"]}),
        pl.DataFrame({"unit_id": ["unit-1", "unit-1"]}),
    )


def test_final_leg_profiles_reject_mixed_route_and_unit_groups():
    updater, _access_policy = _updater()
    mixed_routes = pl.concat([_routes(), _routes(route_index=0)])
    assert updater._final_route_profile(mixed_routes) is None

    mixed_units = pl.concat([_units(), _units(owner="POL")])
    assert updater._final_leg_profile(mixed_units, _routes()) is None
    assert updater._final_unit_profile(
        _units(owner="POL"), _routes().row(0, named=True)
    ) is None


def test_final_leg_requires_region_stationing_and_compatible_domain(monkeypatch):
    updater, _access_policy = _updater(can_station=False)
    units = _units()
    routes = _routes()
    _allow_domain_route(monkeypatch, allowed=True)

    assert updater.try_update_final_leg(_state(), units, 100, routes) is None
    assert updater.try_update_final_leg(
        _state(pl.DataFrame({"name": ["missing-id"]})), units, 100, routes
    ) is None
    assert updater.try_update_final_leg(
        _state(pl.DataFrame({"id": [99]})), units, 100, routes
    ) is None

    state = _state(pl.DataFrame({"id": [2]}))
    assert updater.try_update_final_leg(state, units, 100, routes) is None

    updater, _access_policy = _updater(can_station=True)
    _allow_domain_route(monkeypatch, allowed=False)
    assert updater.try_update_final_leg(state, units, 100, routes) is None


def test_final_leg_updates_progress_and_arrival_state(monkeypatch):
    updater, access_policy = _updater()
    _allow_domain_route(monkeypatch)
    state = _state(pl.DataFrame({"id": [2]}))

    in_transit = updater.try_update_final_leg(state, _units(), 100, _routes())
    assert in_transit is not None
    assert in_transit.item(0, "movement_progress") == 0.5
    assert in_transit.item(0, "is_moving")
    assert access_policy.calls[-1][1] == "UKR"
    state.update_table.assert_not_called()

    arriving_units = _units(
        arrival_at_minute=50,
        unit_lifecycle="battle_retreating",
        engagement_mode="retreat",
    )
    arriving_routes = _routes(rejection_reason="stale")
    updated = updater._apply_final_leg_progress(arriving_units, arriving_routes, 100, state)

    assert updated.item(0, "current_region_id") == 2
    assert updated.item(0, "target_region_id") == NO_TARGET_REGION
    assert updated.item(0, "movement_progress") == 0.0
    assert not updated.item(0, "is_moving")
    assert updated.item(0, "unit_lifecycle") == "battle_regrouping"
    assert updated.item(0, "engagement_mode") == ""
    state.update_table.assert_called_once()
    assert state.update_table.call_args.args[0] == "unit_movement_routes"
