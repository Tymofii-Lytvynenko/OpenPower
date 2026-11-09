import polars as pl

from modules.base.systems.military.home_region_policy import MilitaryHomeRegionPolicy


def test_home_region_policy_rejects_empty_or_incomplete_region_tables():
    policy = MilitaryHomeRegionPolicy()

    assert policy.home_regions_by_country(pl.DataFrame()) == {}
    assert policy.home_regions_by_country(pl.DataFrame({"id": [1]})) == {}


def test_home_region_policy_ignores_rows_without_owner_or_region_id():
    regions = pl.DataFrame(
        {
            "id": [None, 2],
            "owner": ["UKR", None],
            "pop_15_64": [100, 200],
        }
    )

    assert MilitaryHomeRegionPolicy().home_regions_by_country(regions) == {}
