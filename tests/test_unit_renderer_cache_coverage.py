from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

from src.client.renderers.unit_renderer import UnitDragPreview, UnitRenderer


def renderer_for_caches():
    renderer = UnitRenderer.__new__(UnitRenderer)
    renderer._filtered_units_cache_key = None
    renderer._filtered_units_cache = None
    renderer._last_state_id = None
    renderer._last_units_signature = None
    renderer._last_units_revision = None
    renderer._last_owners_hash = None
    renderer._flag_units_signature = None
    renderer._flag_owners = frozenset()
    renderer._prepared_units_key = None
    renderer._prepared_units = None
    renderer._region_lookup = {}
    renderer._region_count = -1
    return renderer


def test_filter_units_applies_owner_and_lifecycle_visibility_then_reuses_cache():
    renderer = renderer_for_caches()
    units = pl.DataFrame({
        "id": ["own", "ally", "queued", "training"],
        "owner": ["USA", "CAN", "USA", "USA"],
        "unit_lifecycle": ["ready", "ready", "deployment_queued", "training"],
    })
    state = SimpleNamespace(tables={"units": units}, table_revisions={"units": 7})

    filtered = renderer._get_filtered_units(state, {"USA", "CAN"})

    assert filtered["id"].to_list() == ["own", "ally"]
    assert renderer._get_filtered_units(state, {"CAN", "USA"}) is filtered
    state.table_revisions["units"] = 8
    refreshed = renderer._get_filtered_units(state, {"USA", "CAN"})
    assert refreshed["id"].to_list() == ["own", "ally"]
    assert refreshed is not filtered


def test_filter_units_handles_missing_empty_and_schema_without_filter_columns():
    renderer = renderer_for_caches()
    assert renderer._get_filtered_units(None, None) is None
    assert renderer._get_filtered_units(SimpleNamespace(tables={}), None) is None

    empty = pl.DataFrame(schema={"id": pl.String, "owner": pl.String})
    state = SimpleNamespace(tables={"units": empty})
    assert renderer._get_filtered_units(state, {"USA"}) is empty

    unfilterable = pl.DataFrame({"id": ["one", "two"]})
    state = SimpleNamespace(tables={"units": unfilterable})
    assert renderer._get_filtered_units(state, {"USA"}) is unfilterable


def test_unit_signature_uses_revisions_for_snapshot_stability_and_empty_marker():
    renderer = renderer_for_caches()
    units = pl.DataFrame({"id": ["one"], "owner": ["USA"], "strength": [4]})
    first_state = SimpleNamespace(
        table_revisions={"units": 3},
        globals={},
    )

    first_signature = renderer._get_units_signature(first_state, units, {"USA"})
    replacement_state = SimpleNamespace(table_revisions={"units": 3}, globals={})
    assert renderer._get_units_signature(replacement_state, units, {"USA"}) == first_signature
    assert renderer._last_state_id == id(first_state)

    changed_state = SimpleNamespace(table_revisions={"units": 4}, globals={})
    changed_units = pl.DataFrame({"id": ["two"], "owner": ["USA"], "strength": [4]})
    changed_signature = renderer._get_units_signature(changed_state, changed_units, {"USA"})
    assert changed_signature != first_signature

    empty_signature = renderer._get_units_signature(
        changed_state,
        pl.DataFrame(schema={"id": pl.String}),
        None,
    )
    assert empty_signature == ("empty", 0)
    assert renderer._get_units_signature(None, changed_units, None) is None
    assert renderer._last_state_id is None
    assert renderer._last_units_signature is None


def test_unit_signature_falls_back_to_tick_when_row_hashing_fails():
    class BrokenFrame:
        columns = ["id"]
        height = 1

        @staticmethod
        def is_empty():
            return False

        @staticmethod
        def select(columns):
            raise RuntimeError("unavailable hash backend")

    renderer = renderer_for_caches()
    state = SimpleNamespace(table_revisions=None, globals={"tick": 18})

    signature = renderer._get_units_signature(state, BrokenFrame(), None)

    assert signature == (1, ("id",), (18, 18, 18))


def test_prepared_unit_cache_enriches_transition_and_keys_by_display_minute():
    renderer = renderer_for_caches()
    renderer._region_count = 2
    renderer._region_lookup = {1: object()}
    prepared = object()
    projection = SimpleNamespace(prepare_units=Mock(return_value=prepared))
    renderer._projection = projection
    units = pl.DataFrame([{
        "id": "U1",
        "readiness_status": "ready",
        "readiness_eta_minute": 0,
        "readiness_transition_id": "",
    }])
    transitions = [{
        "unit_id": "U1",
        "id": "TR1",
        "target_status": "trained",
        "completes_at_minute": 120,
        "progress": 0.25,
    }]

    first = renderer._get_prepared_units(units, ("sig",), transitions, 12.9)
    assert first is prepared
    rows = projection.prepare_units.call_args.args[0]
    assert rows[0]["readiness_target"] == "trained"
    assert rows[0]["readiness_eta_minute"] == 120
    assert rows[0]["readiness_transition_id"] == "TR1"
    assert rows[0]["current_game_minute"] == 12
    assert projection.prepare_units.call_args.kwargs["current_game_minute"] == 12

    assert renderer._get_prepared_units(units, ("sig",), transitions, 12.1) is prepared
    assert projection.prepare_units.call_count == 1
    renderer._get_prepared_units(units, ("sig",), transitions, 13.0)
    assert projection.prepare_units.call_count == 2


def test_flag_atlas_tracks_visible_owners_and_drag_preview_owner():
    renderer = renderer_for_caches()
    owners_seen = []
    renderer._flags = SimpleNamespace(ensure_owners=lambda owners: owners_seen.append(set(owners)))
    units = pl.DataFrame({"owner": ["USA", "CAN", "USA"]})

    renderer._prepare_flag_atlas_for_state(
        units,
        UnitDragPreview("U1", "MEX", 1, 2, 3, 4),
        ("signature",),
    )
    renderer._prepare_flag_atlas_for_state(units, None, ("signature",))

    assert owners_seen == [{"USA", "CAN", "MEX"}, {"USA", "CAN"}]
    assert renderer._flag_owners == frozenset({"USA", "CAN"})


def test_region_lookup_uses_geo_columns_and_reuses_same_sized_region_table():
    renderer = renderer_for_caches()
    state = SimpleNamespace(tables={"regions": pl.DataFrame({
        "id": [1, 2],
        "owner": ["USA", "CAN"],
        "latitude": [10.5, -5.0],
        "longitude": [179.0, -120.0],
    })})

    renderer._refresh_region_lookup(state)

    assert renderer._region_count == 2
    assert renderer._region_lookup[1].geo.latitude == pytest.approx(10.5)
    assert renderer._region_lookup[1].geo.longitude == pytest.approx(179.0)
    assert renderer._region_lookup[2].owner == "CAN"
    cached_lookup = renderer._region_lookup
    renderer._refresh_region_lookup(SimpleNamespace(tables={
        "regions": pl.DataFrame({"id": [10, 11], "latitude": [0.0, 1.0], "longitude": [1.0, 2.0]})
    }))
    assert renderer._region_lookup is cached_lookup


def test_region_lookup_clears_when_region_table_is_missing_or_invalid():
    renderer = renderer_for_caches()
    renderer._region_lookup = {1: object()}
    renderer._region_count = 1

    renderer._refresh_region_lookup(SimpleNamespace(tables={}))
    assert renderer._region_lookup == {}
    assert renderer._region_count == -1

    renderer._refresh_region_lookup(SimpleNamespace(tables={
        "regions": pl.DataFrame({"name": ["region"]}),
    }))
    assert renderer._region_lookup == {}
    assert renderer._region_count == -1
