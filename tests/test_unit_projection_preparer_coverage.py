from src.client.renderers.unit_projection_data import (
    RegionAnchor,
    UnitProjectionRegionIds,
)
from src.client.renderers.unit_projection_preparer import (
    UnitGeographyResolver,
    UnitProjectionDataPreparer,
    UnitProjectionRowNormalizer,
    UnitReadinessResolver,
    PreparedUnitProjectionBatchBuilder,
)
from src.core.map.geo import EquirectangularProjection, GeoCoordinate


def test_anchor_geography_prefers_primary_then_uses_fallback() -> None:
    primary_geo = GeoCoordinate(10.0, 20.0)
    fallback_geo = GeoCoordinate(-5.0, 40.0)
    lookup = {
        1: RegionAnchor(1, primary_geo, "AAA"),
        2: RegionAnchor(2, fallback_geo, "BBB"),
    }

    assert UnitGeographyResolver.anchor_geo(lookup, 1, 2) == primary_geo
    assert UnitGeographyResolver.anchor_geo(lookup, 9, 2) == fallback_geo
    assert UnitGeographyResolver.anchor_geo({}, 9, 2) is None


def test_vector_resolution_uses_target_anchor_and_rejects_missing_source() -> None:
    resolver = UnitGeographyResolver(EquirectangularProjection(360.0, 180.0))
    target = RegionAnchor(2, GeoCoordinate(0.0, 90.0), "AAA")
    vectors = resolver.resolve_vectors(
        {"latitude": 0.0, "longitude": 0.0},
        {2: target},
        UnitProjectionRegionIds(current=1, source=1, target=2),
    )

    assert vectors is not None
    assert vectors[0].tolist() != vectors[1].tolist()
    assert (
        resolver.resolve_vectors(
            {},
            {},
            UnitProjectionRegionIds(current=0, source=0, target=-1),
        )
        is None
    )


def test_projection_builders_return_empty_data_for_empty_or_unresolvable_rows() -> None:
    geography = UnitGeographyResolver(EquirectangularProjection(360.0, 180.0))
    normalizer = UnitProjectionRowNormalizer(geography, UnitReadinessResolver())
    preparer = UnitProjectionDataPreparer(geography)

    assert normalizer.normalize({"id": "unit-1"}, {}, None) is None
    assert preparer.prepare([], {}).count == 0
    assert PreparedUnitProjectionBatchBuilder().build().count == 0
