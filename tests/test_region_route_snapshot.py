from unittest.mock import patch

import polars as pl

from modules.base.systems.military.region_route_snapshot import RegionRouteSnapshot
from modules.base.systems.military.route_policy import MilitaryRoutePlanner


def test_home_region_prefers_owned_capital_then_smallest_region() -> None:
    regions = pl.DataFrame({"id": [5, 1, 3], "owner": ["USA", "USA", "CAN"]})
    snapshot = RegionRouteSnapshot(regions, None)
    assert snapshot.home_region("usa", 5)["id"] == 5
    assert snapshot.home_region("USA", 3)["id"] == 1
    assert snapshot.home_region("USA", 99)["id"] == 1
    assert snapshot.home_region("MEX") is None


def test_map_rows_and_graph_are_materialized_once_and_new_snapshot_sees_changes() -> None:
    regions = pl.DataFrame({"id": [1, 2], "owner": ["USA", "CAN"]})
    adjacency = pl.DataFrame({"region_id": [1], "neighbor_region_id": [2]})
    original_rows = pl.DataFrame.to_dicts
    original_graph = MilitaryRoutePlanner._adjacency
    with (
        patch.object(pl.DataFrame, "to_dicts", autospec=True, side_effect=original_rows) as read_rows,
        patch.object(MilitaryRoutePlanner, "_adjacency", autospec=True, side_effect=original_graph) as build_graph,
    ):
        snapshot = RegionRouteSnapshot(regions, adjacency)
        assert read_rows.call_count == 0
        assert snapshot.home_region("USA")["id"] == 1
        assert snapshot.region_by_id[2]["owner"] == "CAN"
        assert snapshot.prepared_graph.adjacency == {1: {2}, 2: {1}}
        assert snapshot.prepared_graph is snapshot.prepared_graph
        assert read_rows.call_count == 1
        assert build_graph.call_count == 1

        changed = RegionRouteSnapshot(
            regions.with_columns(pl.lit("CAN").alias("owner")),
            adjacency.head(0),
        )
        assert changed.home_region("USA") is None
        assert changed.prepared_graph.adjacency == {}


def test_missing_map_retains_empty_index_behavior() -> None:
    snapshot = RegionRouteSnapshot(None, None)
    assert snapshot.home_region("USA") is None
    assert snapshot.rows == []
    assert snapshot.prepared_graph.region_by_id == {}
