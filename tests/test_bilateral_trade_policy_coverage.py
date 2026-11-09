import json

import polars as pl
import pytest

from modules.base.systems.world import bilateral_trade_policy as policy


def world_rows(*, occupied=(), regions=None, tracks=None):
    countries = [
        {"id": "UKR", "money_reserves": 1000.0, "gdp": 10000.0},
        {"id": "POL", "money_reserves": 500.0, "gdp": 5000.0},
    ]
    regions = regions or [
        {"id": 1, "owner": "UKR"},
        {"id": 2, "owner": "UKR"},
        {"id": 3, "owner": "POL"},
        {"id": 4, "owner": "POL"},
    ]
    governments = [
        {"country_id": "UKR", "capital_region_id": 1},
        {"country_id": "POL", "capital_region_id": 3},
    ]
    tracks = tracks or [
        {"id": "ukr-military", "country_id": "UKR", "branch": "military", "research_level": 4,
         "funding_ratio": 0.5, "progress": 0.2, "priority": 2, "focus": "armor",
         "blocking_reason": "", "unlocks_json": '["tanks"]'},
        {"id": "pol-military", "country_id": "POL", "branch": "military", "research_level": 2,
         "funding_ratio": 0.4, "progress": 0.1, "priority": 1, "focus": "",
         "blocking_reason": "", "unlocks_json": '["artillery"]'},
    ]
    occupations = [{"region_id": region_id} for region_id in occupied]
    return countries, regions, governments, tracks, occupations


def frame_world(*, occupied=(), regions=None, tracks=None):
    countries, regions, governments, tracks, occupations = world_rows(
        occupied=occupied, regions=regions, tracks=tracks,
    )
    return (
        pl.DataFrame(countries), pl.DataFrame(regions), pl.DataFrame(governments),
        pl.DataFrame(tracks), pl.DataFrame(occupations, schema={"region_id": pl.Int64}),
    )


def validate_rows(offered, requested=None, *, occupied=(), regions=None, tracks=None,
                  countries=None, governments=None):
    default_countries, default_regions, default_governments, default_tracks, occupations = world_rows(
        occupied=occupied, regions=regions, tracks=tracks,
    )
    return policy.validate_trade_packages(
        "UKR", "POL", offered, requested or [], countries or default_countries,
        default_regions, governments if governments is not None else default_governments,
        default_tracks, occupations,
    )


def validate_frames(offered, requested=None, *, occupied=(), regions=None, tracks=None,
                    countries=None, governments=None):
    default_countries, default_regions, default_governments, default_tracks, default_occupations = frame_world(
        occupied=occupied, regions=regions, tracks=tracks,
    )
    country_frame = pl.DataFrame(countries) if countries is not None else default_countries
    government_frame = pl.DataFrame(governments) if governments is not None else default_governments
    return policy.validate_trade_package_frames(
        "UKR", "POL", offered, requested or [], country_frame, default_regions,
        government_frame, default_tracks, default_occupations,
    )


def test_normalize_trade_assets_canonicalizes_and_combines_cash():
    assets, error = policy.normalize_trade_assets([
        {"type": " CASH ", "amount": 10.126},
        {"type": "territory", "region_id": "2"},
        {"type": "technology", "branch": " Military ", "level": "4"},
        {"type": "cash", "amount": 2.004},
    ])

    assert error == ""
    assert assets == [
        {"type": "territory", "region_id": 2},
        {"type": "technology", "branch": "military", "level": 4},
        {"type": "cash", "amount": 12.13},
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "Each side can contain at most 16 assets."),
        ({"type": "cash", "amount": 1}, "Each side can contain at most 16 assets."),
        ([None], "Trade assets must be structured values."),
        ([{"type": "cash", "amount": 0}], "Cash amounts must be finite, positive, and within the supported limit."),
        ([{"type": "cash", "amount": float("nan")}], "Cash amounts must be finite, positive, and within the supported limit."),
        ([{"type": "cash", "amount": policy.MAX_CASH_AMOUNT * 2}], "Cash amounts must be finite, positive, and within the supported limit."),
        ([{"type": "territory", "region_id": "bad"}], "Territory assets need a valid region id."),
        ([{"type": "territory", "region_id": 0}], "Territory assets need a positive region id."),
        ([{"type": "technology", "branch": "military", "level": "bad"}], "Technology assets need a valid research level."),
        ([{"type": "technology", "branch": " ", "level": 1}], "Technology assets need a branch and a positive research level."),
        ([{"type": "technology", "branch": "military", "level": 0}], "Technology assets need a branch and a positive research level."),
        ([{"type": "unknown"}], "Supported assets are cash, territory, and technology."),
        ([{"type": "territory", "region_id": 2}, {"type": "territory", "region_id": 2}], "A package cannot offer the same territory or technology branch twice."),
        ([{"type": "technology", "branch": "military", "level": 1}, {"type": "technology", "branch": "MILITARY", "level": 2}], "A package cannot offer the same territory or technology branch twice."),
        ([{"type": "cash", "amount": policy.MAX_CASH_AMOUNT}, {"type": "cash", "amount": policy.MAX_CASH_AMOUNT}], "The combined cash amount is outside the supported limit."),
    ],
)
def test_normalize_trade_assets_rejects_invalid_shapes_and_values(raw, expected):
    assets, error = policy.normalize_trade_assets(raw)
    assert assets == []
    assert error == expected


def test_trade_asset_json_round_trip_and_invalid_input_fall_back_to_empty_list():
    assets = [{"type": "cash", "amount": 3.5}, {"type": "territory", "region_id": 4}]
    encoded = policy.encode_trade_assets(assets)
    assert json.loads(encoded) == assets
    assert policy.decode_trade_assets(encoded) == [assets[1], assets[0]]
    assert policy.decode_trade_assets("not json") == []
    assert policy.decode_trade_assets(json.dumps([{"type": "unknown"}])) == []


@pytest.mark.parametrize(
    ("offered", "options", "expected"),
    [
        ([], {}, "A trade package must contain at least one asset."),
        ([{"type": "cash", "amount": 1001}], {}, "UKR does not have enough available cash"),
        ([{"type": "territory", "region_id": 1}, {"type": "territory", "region_id": 2}], {}, "UKR must keep at least one region."),
        ([{"type": "territory", "region_id": 3}], {}, "UKR no longer owns territory 3."),
        ([{"type": "territory", "region_id": 2}], {"occupied": (2,)}, "Occupied territory 2 cannot be transferred"),
        ([{"type": "technology", "branch": "naval", "level": 2}], {}, "Technology offers must transfer UKR's current naval level in full."),
        ([{"type": "technology", "branch": "military", "level": 3}], {}, "Technology offers must transfer UKR's current military level in full."),
        ([{"type": "technology", "branch": "military", "level": 4}], {
            "tracks": [
                {"country_id": "UKR", "branch": "military", "research_level": 4},
                {"country_id": "POL", "branch": "military", "research_level": 4},
            ],
        }, "The receiving country already has military at level 4 or higher."),
    ],
)
def test_list_and_frame_validation_agree_on_package_rejections(offered, options, expected):
    row_error = validate_rows(offered, **options)
    frame_error = validate_frames(offered, **options)
    assert expected in row_error
    assert frame_error == row_error


def test_list_and_frame_validation_accept_a_valid_package_and_reject_missing_countries():
    offered = [{"type": "territory", "region_id": 2}, {"type": "technology", "branch": "military", "level": 4}]
    assert validate_rows(offered) == ""
    assert validate_frames(offered) == ""
    assert validate_rows(offered, countries=[{"id": "UKR", "money_reserves": 10}]) == "Both countries must exist in the current world."
    assert validate_frames(offered, countries=[{"id": "UKR", "money_reserves": 10}]) == "Both countries must exist in the current world."


def test_list_application_transfers_assets_merges_unlocks_and_repairs_capital():
    countries, regions, governments, tracks, _ = world_rows()
    regions[0]["owner"] = "UKR"
    offered = [
        {"type": "cash", "amount": 50},
        {"type": "territory", "region_id": 1},
        {"type": "technology", "branch": "military", "level": 4},
    ]

    updated_countries, updated_regions, updated_governments, updated_tracks = policy.apply_trade_packages(
        "UKR", "POL", offered, [], countries, regions, governments, tracks,
    )

    by_country = {row["id"]: row for row in updated_countries}
    by_region = {row["id"]: row for row in updated_regions}
    by_government = {row["country_id"]: row for row in updated_governments}
    by_track = {(row["country_id"], row["branch"]): row for row in updated_tracks}
    assert by_country["UKR"]["money_reserves"] == 950
    assert by_country["POL"]["money_reserves"] == 550
    assert by_region[1]["owner"] == "POL"
    assert by_government["UKR"]["capital_region_id"] == 2
    assert by_track[("POL", "military")]["research_level"] == 4
    assert json.loads(by_track[("POL", "military")]["unlocks_json"]) == ["artillery", "tanks"]


def test_list_application_updates_existing_tracks_and_tolerates_malformed_unlocks():
    countries, regions, governments, tracks, _ = world_rows()
    tracks[0]["unlocks_json"] = "bad json"
    tracks[1]["unlocks_json"] = "bad json"
    result = policy.apply_trade_packages(
        "UKR", "POL", [{"type": "technology", "branch": "military", "level": 4}],
        [], countries, regions, governments, tracks,
    )
    recipient = next(row for row in result[3] if row["country_id"] == "POL")
    assert recipient["research_level"] == 4
    assert json.loads(recipient["unlocks_json"]) == []

    result_without_governments = policy.apply_trade_packages(
        "UKR", "POL", [], [], countries, regions, [], tracks,
    )
    assert result_without_governments[2] == []

    seller_only = [tracks[0]]
    result_with_new_recipient = policy.apply_trade_packages(
        "UKR", "POL", [{"type": "technology", "branch": "military", "level": 4}],
        [], countries, regions, governments, seller_only,
    )
    new_track = next(row for row in result_with_new_recipient[3] if row["country_id"] == "POL")
    assert new_track["research_level"] == 4
    assert new_track["funding_ratio"] == 0
    assert json.loads(new_track["unlocks_json"]) == []


def test_list_package_value_accounts_for_cash_territory_and_research_gap():
    countries, regions, _, tracks, _ = world_rows()
    assets = [
        {"type": "cash", "amount": 25},
        {"type": "territory", "region_id": 2},
        {"type": "technology", "branch": "military", "level": 4},
    ]
    assert policy.trade_package_value(assets, "UKR", "POL", countries, regions, tracks) == 5225
    assert policy.trade_package_value([], "missing", "missing", [], [], []) == 0


def test_frame_application_transfers_cash_territory_research_and_capital():
    countries, regions, governments, tracks, _ = frame_world()
    seller_only = tracks.filter(pl.col("country_id") == "UKR")
    offered = [
        {"type": "cash", "amount": 50},
        {"type": "territory", "region_id": 1},
        {"type": "technology", "branch": "military", "level": 4},
    ]

    result = policy.apply_trade_package_frames(
        "UKR", "POL", offered, [], countries, regions, governments, seller_only,
    )
    updated_countries, updated_regions, updated_governments, updated_tracks = result

    assert updated_countries.filter(pl.col("id") == "UKR")["money_reserves"][0] == 950
    assert updated_countries.filter(pl.col("id") == "POL")["money_reserves"][0] == 550
    assert updated_regions.filter(pl.col("id") == 1)["owner"][0] == "POL"
    assert updated_governments.filter(pl.col("country_id") == "UKR")["capital_region_id"][0] == 2
    recipient = updated_tracks.filter((pl.col("country_id") == "POL") & (pl.col("branch") == "military")).row(0, named=True)
    assert recipient["research_level"] == 4
    assert json.loads(recipient["unlocks_json"]) == ["tanks"]


def test_frame_application_updates_existing_track_and_skips_missing_seller_or_columns():
    countries, regions, governments, tracks, _ = frame_world()
    updated = policy.apply_trade_package_frames(
        "UKR", "POL", [{"type": "technology", "branch": "military", "level": 5}],
        [], countries, regions, governments, tracks,
    )
    recipient = updated[3].filter((pl.col("country_id") == "POL") & (pl.col("branch") == "military")).row(0, named=True)
    assert recipient["research_level"] == 5

    no_seller = tracks.filter(pl.col("country_id") == "POL")
    unchanged_tracks = policy.apply_trade_package_frames(
        "UKR", "POL", [{"type": "technology", "branch": "military", "level": 4}],
        [], countries, regions, governments, no_seller,
    )[3]
    assert unchanged_tracks.height == no_seller.height

    no_cash = countries.drop("money_reserves")
    no_owner = regions.drop("owner")
    unchanged = policy.apply_trade_package_frames(
        "UKR", "POL", [
            {"type": "cash", "amount": 10}, {"type": "territory", "region_id": 1},
        ], [], no_cash, no_owner, None, None,
    )
    assert unchanged[0].columns == no_cash.columns
    assert unchanged[1].columns == no_owner.columns
    assert unchanged[2:] == (None, None)

    no_owner_governments = pl.DataFrame({"country_id": ["SWE"], "capital_region_id": [99]})
    result_without_matching_government = policy.apply_trade_package_frames(
        "UKR", "POL", [], [], countries, regions, no_owner_governments, None,
    )
    assert result_without_matching_government[2].equals(no_owner_governments)


def test_frame_package_value_handles_all_assets_and_missing_optional_frames():
    countries, regions, _, tracks, _ = frame_world()
    assets = [
        {"type": "cash", "amount": 25},
        {"type": "territory", "region_id": 2},
        {"type": "technology", "branch": "military", "level": 4},
    ]
    assert policy.trade_package_value_frames(assets, "UKR", "POL", countries, regions, tracks) == 5225
    assert policy.trade_package_value_frames(assets, "missing", "missing", None, None, None) == 26.08


def test_frame_lookups_handle_missing_keys_duplicates_and_normalized_values():
    frame = pl.DataFrame({"id": [" ukr ", "UKR"], "value": [1, 2]})
    assert policy._frame_row_by_tag(frame, "id", "ukr")["value"] == 2
    assert policy._frame_row_by_tag(None, "id", "UKR") is None
    assert policy._frame_row_by_tag(frame, "missing", "UKR") is None
    integer_frame = pl.DataFrame({"id": [1, 2], "value": [10, 20]})
    assert policy._frame_row_by_integer(integer_frame, "id", 2)["value"] == 20
    assert policy._frame_row_by_integer(integer_frame, "id", 3) is None
    assert policy._frame_row_by_integer(None, "id", 2) is None
    assert policy._frame_row_by_integer(integer_frame, "missing", 2) is None
    tracks = pl.DataFrame({"country_id": [" ukr "], "branch": ["Military"], "research_level": [4]})
    assert policy._frame_track_row(tracks, "UKR", "military")["research_level"] == 4
    assert policy._frame_track_row(tracks.drop("branch"), "UKR", "military") is None


def test_scalar_and_json_helpers_normalize_invalid_values():
    assert policy._tag(None) == ""
    assert policy._tag(" ukr ") == "UKR"
    assert policy._branch(" Military ") == "military"
    assert policy._integer("3") == 3
    assert policy._integer(-2) == 0
    assert policy._integer("bad") == 0
    assert policy._finite("4.5") == 4.5
    assert policy._finite(float("inf")) == 0
    assert policy._finite("bad") == 0
    assert policy._json_string_list('[1,"x"]') == ["1", "x"]
    assert policy._json_string_list("{}") == []
    assert policy._json_string_list("bad json") == []


def test_frame_value_uses_safe_defaults_when_columns_are_unavailable():
    assert policy.trade_package_value_frames(
        [{"type": "territory", "region_id": 1}, {"type": "technology", "branch": "military", "level": 4}],
        "UKR", "POL", pl.DataFrame({"id": ["UKR"]}), pl.DataFrame({"owner": ["UKR"]}),
        pl.DataFrame({"country_id": ["POL"], "branch": ["military"]}),
    ) == 1.08


def test_encoded_assets_use_stable_key_order_and_unicode():
    encoded = policy.encode_trade_assets([{"type": "technology", "branch": "café", "level": 2}])
    assert encoded == '[{"branch":"café","level":2,"type":"technology"}]'


def test_row_and_frame_validators_reject_transfer_of_a_country_only_region():
    regions = [
        {"id": 1, "owner": "UKR"},
        {"id": 3, "owner": "POL"},
        {"id": 4, "owner": "POL"},
    ]
    offered = [{"type": "territory", "region_id": 1}]
    expected = "UKR must keep at least one region."

    assert validate_rows(offered, regions=regions) == expected
    assert validate_frames(offered, regions=regions) == expected
