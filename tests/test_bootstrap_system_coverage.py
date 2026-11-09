from __future__ import annotations

from types import SimpleNamespace

import polars as pl

from modules.base.systems.world.bootstrap_system import BootstrapSystem


def test_country_builders_return_empty_without_country_rows():
    system = BootstrapSystem()
    state = SimpleNamespace(tables={})

    builders = (
        system._build_country_governments,
        system._build_country_laws,
        system._build_messages,
        system._build_objectives,
        system._build_research_tracks,
        system._build_unit_designs,
        system._build_strategic_weapons,
    )

    assert all(builder(state) == [] for builder in builders)


def test_seed_helpers_skip_unavailable_or_duplicate_records():
    system = BootstrapSystem()
    already_seeded = SimpleNamespace(
        globals={"country_identity_groups_seeded": True},
        tables={},
    )
    system._seed_country_identity_groups(already_seeded)

    identity = {
        "country_id": "USA",
        "identity_type": "ethnic",
        "identity_id": "group-1",
        "share": 0.4,
    }
    state = SimpleNamespace(
        globals={},
        tables={
            "country_identity_distribution": pl.DataFrame([identity]),
            "country_identity_groups": pl.DataFrame([identity]),
        },
        time=SimpleNamespace(total_minutes=0),
    )

    system._seed_country_identity_groups(state)
    system._seed_migration_policies(SimpleNamespace(tables={}))

    assert state.globals["country_identity_groups_seeded"] is True
    assert state.tables["country_identity_groups"].height == 1


def test_strategic_weapon_builder_skips_invalid_profiles_and_disabled_classes():
    system = BootstrapSystem()
    state = SimpleNamespace(
        globals={
            "strategic_weapon_production_profiles": [],
            "strategic_weapon_profiles": {
                "unknown": {},
                "slbm": [],
                "icbm": {"enabled": False},
            },
        },
        tables={"countries": pl.DataFrame({"id": ["USA"]})},
    )

    assert system._strategic_weapon_profiles(state) == {"icbm": {"enabled": False}}
    assert system._build_strategic_weapons(state) == []


def test_home_region_and_value_helpers_handle_invalid_inputs():
    system = BootstrapSystem()
    regions = pl.DataFrame({"id": [None, 2], "owner": [None, "None"]})

    assert system._home_regions_by_country(regions) == {}
    assert system._normalize_side(None) == ()
    assert system._normalize_side(["USA", None]) == ("USA",)
    assert system._normalize_side(("CAN", None)) == ("CAN",)
    assert system._normalize_side("USA, CAN,,") == ("USA", "CAN")
    assert system._normalize_side(17) == ()
    assert system._as_ratio(75, 0.5) == 0.75
    assert system._is_playable({"is_playable": "false"}) is False
