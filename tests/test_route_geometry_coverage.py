import math

import polars as pl

from modules.base.systems.military.route_geometry import edge_distance_index


def test_edge_distance_index_returns_empty_for_only_reverse_edges():
    regions = pl.DataFrame(
        {"id": [1, 2], "latitude": [0.0, 10.0], "longitude": [0.0, 10.0]}
    )

    assert edge_distance_index(regions, {2: {1}}) == {}


def test_edge_distance_index_maps_pixel_centers_to_geographic_coordinates():
    regions = pl.DataFrame(
        {"id": [1, 2], "center_x": [0.0, 2.0], "center_y": [0.0, 1.0]}
    )

    distances = edge_distance_index(regions, {1: {2}, 2: {1}})

    assert set(distances) == {(1, 2)}
    assert math.isfinite(distances[(1, 2)])
    assert distances[(1, 2)] > 0.0
